"""
User profile page with newsletter and stock preferences management.
"""

import streamlit as st
from typing import List, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from auth import SessionManager, require_auth

class ProfileManager:
    """Manages user profile data and operations."""
    
    def __init__(self, conn_params: Dict[str, Any]):
        """Initialize with database connection parameters."""
        self.connection_params = conn_params
    
    def get_connection(self):
        """Get database connection."""
        try:
            conn = psycopg2.connect(**self.connection_params)
            return conn
        except Exception as e:
            st.error(f"Database connection failed: {e}")
            return None
    
    def update_newsletter_preference(self, user_id: int, signed_up: bool) -> bool:
        """Update user's newsletter preference."""
        try:
            update_query = """
            UPDATE users 
            SET signed_up_for_newsletter = %s
            WHERE id = %s
            """
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(update_query, (signed_up, user_id))
                    conn.commit()
                    return True
                    
        except Exception as e:
            st.error(f"Failed to update newsletter preference: {e}")
            return False
    
    def update_favorite_stocks(self, user_id: int, fav_stocks: List[str]) -> bool:
        """Update user's favorite stocks list."""
        try:
            update_query = """
            UPDATE users 
            SET fav_stocks = %s
            WHERE id = %s
            """
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(update_query, (fav_stocks, user_id))
                    conn.commit()
                    return True
                    
        except Exception as e:
            st.error(f"Failed to update favorite stocks: {e}")
            return False
    
    def get_user_profile(self, user_id: int) -> Dict[str, Any]:
        """Get user profile data."""
        try:
            select_query = """
            SELECT username, email, signed_up_for_newsletter, fav_stocks, profile_data
            FROM users 
            WHERE id = %s
            """
            
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(select_query, (user_id,))
                    profile = cursor.fetchone()
                    return dict(profile) if profile else {}
                    
        except Exception as e:
            st.error(f"Failed to get user profile: {e}")
            return {}


@require_auth
def render_profile_page():
    """Render the user profile page."""
    st.title("My Profile")
    
    # Get current user data
    user = SessionManager.get_current_user()
    if not user:
        st.error("User data not found.")
        return
    
    # Initialize profile manager with connection parameters
    from auth import DatabaseManager
    db = DatabaseManager()
    profile_manager = ProfileManager(db.connection_params)
    
    # Get full profile data
    profile = profile_manager.get_user_profile(user["id"])
    
    # Display basic user information
    st.subheader("Account Information")
    st.write(f"**Username:** {profile.get('username', '')}")
    st.write(f"**Email:** {profile.get('email', '')}")
    
    # Newsletter preferences section
    st.subheader("Newsletter Preferences")
    
    newsletter_status = profile.get('signed_up_for_newsletter', False)
    newsletter_signup = st.checkbox(
        "Subscribe to daily stock market newsletter", 
        value=newsletter_status
    )
    
    if newsletter_signup != newsletter_status:
        if profile_manager.update_newsletter_preference(user["id"], newsletter_signup):
            st.success("Newsletter preference updated!")
            # Update session state
            user["signed_up_for_newsletter"] = newsletter_signup
            SessionManager.login_user(user)  # Re-login to update session
    
    # Favorite stocks section
    st.subheader("Favorite Stocks")
    st.write("Add your favorite stocks to track in the daily newsletter")
    
    # Current favorite stocks
    current_fav_stocks = profile.get('fav_stocks', [])
    fav_stocks_str = ", ".join(current_fav_stocks) if current_fav_stocks else ""
    
    new_fav_stocks = st.text_input(
        "Enter stock symbols separated by commas (e.g., AAPL, MSFT, GOOGL)", 
        value=fav_stocks_str
    )
    
    if st.button("Update Favorite Stocks"):
        # Process the input
        stock_list = [stock.strip().upper() for stock in new_fav_stocks.split(',') if stock.strip()]
        
        if profile_manager.update_favorite_stocks(user["id"], stock_list):
            st.success("Favorite stocks updated!")
            # Update session state
            user["fav_stocks"] = stock_list
            SessionManager.login_user(user)  # Re-login to update session
    
    # Account actions section
    st.subheader("Account Actions")
    if st.button("Logout"):
        SessionManager.logout_user()
        st.rerun()