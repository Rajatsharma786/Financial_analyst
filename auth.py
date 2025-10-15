"""
Lightweight authentication module for Financial Analyst Streamlit app.
This module handles user authentication without loading heavy dependencies.
"""

import os
import hashlib
import secrets
import streamlit as st
from typing import Optional, Dict, Any
import psycopg2   #type: ignore
from psycopg2.extras import RealDictCursor   #type: ignore
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Handles database connections and operations for user authentication."""
    
    def __init__(self):
        self.connection_params = {
            'host': os.getenv('AZURE_POSTGRES_HOST', 'financialdb.postgres.database.azure.com'),
            'database': os.getenv('AZURE_POSTGRES_DB', 'postgres'),
            'user': os.getenv('AZURE_POSTGRES_USER', 'tony_123'),
            'password': os.getenv('AZURE_POSTGRES_PASSWORD'),
            'port': os.getenv('AZURE_POSTGRES_PORT', '5432'),
            'sslmode': 'require'
        }
    
    def get_connection(self):
        """Get database connection."""
        try:
            conn = psycopg2.connect(**self.connection_params)
            return conn
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            st.error("Database connection failed. Please check your configuration.")
            return None
    
    def create_users_table(self):
        """Create users table if it doesn't exist."""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            salt VARCHAR(32) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            profile_data JSONB DEFAULT '{}',
            signed_up_for_newsletter BOOLEAN DEFAULT FALSE,
            fav_stocks TEXT[] DEFAULT '{}'
        );
        
        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        """
        
        try:
            conn = self.get_connection()
            if conn is None:
                logger.error("Cannot create users table: Database connection is None")
                return
            
            with conn:
                with conn.cursor() as cursor:
                    cursor.execute(create_table_query)
                    conn.commit()
                    logger.info("Users table created successfully")
        except Exception as e:
            logger.error(f"Failed to create users table: {e}")

class PasswordManager:
    """Handles password hashing and verification."""
    
    @staticmethod
    def generate_salt() -> str:
        """Generate a random salt."""
        return secrets.token_hex(16)
    
    @staticmethod
    def hash_password(password: str, salt: str) -> str:
        """Hash password with salt using SHA-256."""
        return hashlib.sha256((password + salt).encode()).hexdigest()
    
    @staticmethod
    def verify_password(password: str, hash_str: str, salt: str) -> bool:
        """Verify password against hash."""
        return PasswordManager.hash_password(password, salt) == hash_str

class UserManager:
    """Handles user operations like registration, login, etc."""
    
    def __init__(self):
        self.db = DatabaseManager()
        # Initialize database table
        self.db.create_users_table()
    
    def register_user(self, username: str, email: str, password: str, signed_up_for_newsletter: bool = False, fav_stocks: list = None) -> Dict[str, Any]:
        """Register a new user."""
        try:
            # Check if user already exists
            if self.user_exists(username, email):
                return {"success": False, "message": "Username or email already exists"}
            
            # Generate salt and hash password
            salt = PasswordManager.generate_salt()
            password_hash = PasswordManager.hash_password(password, salt)
            
            # Set default empty list for fav_stocks if None
            if fav_stocks is None:
                fav_stocks = []
                
            # Insert user into database
            insert_query = """
            INSERT INTO users (username, email, password_hash, salt, signed_up_for_newsletter, fav_stocks)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, username, email, created_at, signed_up_for_newsletter, fav_stocks
            """
            
            conn = self.db.get_connection()
            if conn is None:
                return {"success": False, "message": "Database connection failed. Please try again later."}
            
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(insert_query, (username, email, password_hash, salt, signed_up_for_newsletter, fav_stocks))
                    user_data = cursor.fetchone()
                    conn.commit()
                    
                    return {
                        "success": True,
                        "message": "User registered successfully",
                        "user": dict(user_data)
                    }
                    
        except Exception as e:
            logger.error(f"User registration failed: {e}")
            return {"success": False, "message": "Registration failed. Please try again."}
    
    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user login."""
        try:
            select_query = """
            SELECT id, username, email, password_hash, salt, last_login, is_active, signed_up_for_newsletter, fav_stocks
            FROM users 
            WHERE username = %s AND is_active = TRUE
            """
            
            conn = self.db.get_connection()
            if conn is None:
                return {"success": False, "message": "Database connection failed. Please try again later."}
            
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(select_query, (username,))
                    user_data = cursor.fetchone()
                    
                    if not user_data:
                        return {"success": False, "message": "Invalid username or password"}
                    
                    # Verify password
                    if PasswordManager.verify_password(password, user_data['password_hash'], user_data['salt']):
                        # Update last login
                        update_query = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s"
                        cursor.execute(update_query, (user_data['id'],))
                        conn.commit()
                        
                        return {
                            "success": True,
                            "message": "Login successful",
                            "user": {
                                "id": user_data['id'],
                                "username": user_data['username'],
                                "email": user_data['email'],
                                "last_login": user_data['last_login'],
                                "signed_up_for_newsletter": user_data['signed_up_for_newsletter'],
                                "fav_stocks": user_data['fav_stocks']
                            }
                        }
                    else:
                        return {"success": False, "message": "Invalid username or password"}
                        
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return {"success": False, "message": "Authentication failed. Please try again."}
    
    def user_exists(self, username: str, email: str) -> bool:
        """Check if user already exists."""
        try:
            check_query = """
            SELECT COUNT(*) as count FROM users 
            WHERE username = %s OR email = %s
            """
            
            conn = self.db.get_connection()
            if conn is None:
                logger.error("Cannot check user existence: Database connection is None")
                return False
            
            with conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(check_query, (username, email))
                    result = cursor.fetchone()
                    return result['count'] > 0
                    
        except Exception as e:
            logger.error(f"Error checking user existence: {e}")
            return False

class SessionManager:
    """Manages user sessions using Streamlit session state."""
    
    @staticmethod
    def initialize_session():
        """Initialize session state variables."""
        if 'authenticated' not in st.session_state:
            st.session_state.authenticated = False
        if 'user_data' not in st.session_state:
            st.session_state.user_data = None
        if 'auth_timestamp' not in st.session_state:
            st.session_state.auth_timestamp = None
    
    @staticmethod
    def login_user(user_data: Dict[str, Any]):
        """Log in user and set session state."""
        st.session_state.authenticated = True
        st.session_state.user_data = user_data
        st.session_state.auth_timestamp = datetime.now()
    
    @staticmethod
    def logout_user():
        """Log out user and clear session state."""
        st.session_state.authenticated = False
        st.session_state.user_data = None
        st.session_state.auth_timestamp = None
    
    @staticmethod
    def is_authenticated() -> bool:
        """Check if user is authenticated."""
        return st.session_state.get('authenticated', False)
    
    @staticmethod
    def get_current_user() -> Optional[Dict[str, Any]]:
        """Get current user data."""
        return st.session_state.get('user_data')
    
    @staticmethod
    def is_session_valid(session_duration_hours: int = 24) -> bool:
        """Check if session is still valid."""
        if not SessionManager.is_authenticated():
            return False
        
        auth_time = st.session_state.get('auth_timestamp')
        if not auth_time:
            return False
        
        session_expiry = auth_time + timedelta(hours=session_duration_hours)
        return datetime.now() < session_expiry

def render_auth_page():
    """Render the authentication page with login and signup forms."""
    st.set_page_config(
        page_title="Financial Analyst - Authentication",
        page_icon="📊",
        layout="centered"
    )
    
    # Initialize session
    SessionManager.initialize_session()
    
    # Check if already authenticated
    if SessionManager.is_authenticated() and SessionManager.is_session_valid():
        return True
    
    # Custom CSS for auth page
    st.markdown("""
    <style>
    .auth-container {
        max-width: 400px;
        margin: 0 auto;
        padding: 2rem;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        background-color: white;
    }
    .auth-title {
        text-align: center;
        color: #1e3a8a;
        margin-bottom: 2rem;
    }
    .stButton > button {
        width: 100%;
        background-color: #1e3a8a;
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        font-weight: bold;
    }
    .stButton > button:hover {
        background-color: #1e40af;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.markdown('<h1 class="auth-title">📊 Financial Analyst</h1>', unsafe_allow_html=True)
    
    # Create tabs for login and signup
    tab1, tab2 = st.tabs(["Login", "Sign Up"])
    
    user_manager = UserManager()
    
    with tab1:
        st.subheader("Login to your account")
        
        with st.form("login_form"):
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.form_submit_button("Login"):
                if username and password:
                    with st.spinner("Authenticating..."):
                        result = user_manager.authenticate_user(username, password)
                        
                        if result["success"]:
                            SessionManager.login_user(result["user"])
                            st.success(result["message"])
                            st.rerun()
                        else:
                            st.error(result["message"])
                else:
                    st.error("Please fill in all fields")
    
    with tab2:
        st.subheader("Create a new account")
        
        with st.form("signup_form"):
            new_username = st.text_input("Username", key="signup_username")
            new_email = st.text_input("Email", key="signup_email")
            new_password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="confirm_password")
            signed_up_for_newsletter = st.checkbox("Sign up for daily stock newsletter", value=False, key="signup_newsletter")
            
            fav_stocks_input = st.text_input("Favorite Stocks (comma separated, e.g., AAPL,MSFT,GOOGL)", key="fav_stocks")
            
            if st.form_submit_button("Sign Up"):
                if new_username and new_email and new_password and confirm_password:
                    if new_password != confirm_password:
                        st.error("Passwords do not match")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters long")
                    else:
                        # Process favorite stocks
                        fav_stocks = [stock.strip().upper() for stock in fav_stocks_input.split(',')] if fav_stocks_input else []
                        
                        with st.spinner("Creating account..."):
                            result = user_manager.register_user(
                                new_username, 
                                new_email, 
                                new_password, 
                                signed_up_for_newsletter,
                                fav_stocks
                            )
                            
                            if result["success"]:
                                st.success(result["message"])
                                st.info("Please switch to the Login tab to sign in")
                            else:
                                st.error(result["message"])
                else:
                    st.error("Please fill in all fields")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align: center; color: #666;'>🔒 Secure authentication powered by Azure PostgreSQL</p>",
        unsafe_allow_html=True
    )
    
    return False

def require_auth(func):
    """Decorator to require authentication for a function."""
    def wrapper(*args, **kwargs):
        if not SessionManager.is_authenticated() or not SessionManager.is_session_valid():
            st.warning("Please log in to access this feature.")
            st.stop()
        return func(*args, **kwargs)
    return wrapper