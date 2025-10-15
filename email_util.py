"""
Optimized email utility for sending stock newsletters to subscribed users.
Reuses existing database and stock fetching functionality from auth.py and app.py.
"""

import os
import logging
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Import dependencies required by the tools from app.py
import requests
import pandas as pd

# Import LangChain for data analysis
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Import existing modules and functions
from auth import DatabaseManager
from app import get_stock_price_metric, get_stock_news

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


class SubscriberManager:
    """Manages newsletter subscriber operations using existing DatabaseManager."""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def get_newsletter_subscribers(self) -> List[Dict[str, Any]]:
        """
        Retrieve all users subscribed to the newsletter with their favorite stocks.
        Returns: List of user dictionaries with id, username, email, and fav_stocks.
        """
        query = """
        SELECT id, username, email, fav_stocks
        FROM users
        WHERE signed_up_for_newsletter = TRUE AND is_active = TRUE
        ORDER BY id
        """
        
        try:
            conn = self.db_manager.get_connection()
            if not conn:
                return []
            
            with conn:
                from psycopg2.extras import RealDictCursor
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                    subscribers = cursor.fetchall()
                    return [dict(sub) for sub in subscribers]
        except Exception as e:
            logger.error(f"Failed to retrieve newsletter subscribers: {e}")
            return []


class StockDataProcessor:
    """Processes stock data using existing tools from app.py."""
    
    def __init__(self):
        # Initialize LLM for data analysis
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    def analyze_price_data_with_llm(self, stock_ticker: str, price_data_raw: str) -> str:
        """
        Use LLM to analyze price data and generate human-readable summary.
        Args:
            stock_ticker: Stock ticker symbol
            price_data_raw: Raw markdown price data
        Returns: Human-readable analysis
        """
        try:
            system_prompt = SystemMessage(content="""You are a financial analyst assistant. 
            Analyze the provided stock price data and create a clear, concise summary for investors.
            Focus on: current price, recent changes, performance trends, and key metrics.
            Format your response in a professional but easy-to-understand way.
            Keep it under 200 words.""")
            
            user_prompt = HumanMessage(content=f"""Analyze this price data for {stock_ticker} and provide a clear summary:

                {price_data_raw}

                Provide a concise analysis highlighting the most important metrics and trends.""")
            
            response = self.llm.invoke([system_prompt, user_prompt])
            return response.content
        except Exception as e:
            logger.error(f"LLM analysis failed for {stock_ticker}: {e}")
            return f"Price data for {stock_ticker}:\n\n{price_data_raw[:500]}..."
    
    @staticmethod
    def clean_news_data(news_data_raw: str) -> str:
        """
        Clean news data by removing table formatting and keeping only readable content.
        Args:
            news_data_raw: Raw markdown news data with table formatting
        Returns: Cleaned, human-readable news text
        """
        try:
            lines = news_data_raw.split('\n')
            cleaned_lines = []
            
            for line in lines:
                # Skip table separator lines (lines with |---|---|)
                if '|--' in line or line.strip().startswith('|---'):
                    continue
                
                # Skip header line with column names
                if 'symbols' in line.lower() and 'title' in line.lower():
                    continue
                
                # Process data rows
                if '|' in line and line.strip():
                    # Split by pipe and clean up
                    parts = [p.strip() for p in line.split('|') if p.strip()]
                    
                    if len(parts) >= 3:  # symbols, title, summary, url
                        title = parts[1] if len(parts) > 1 else ''
                        summary = parts[2] if len(parts) > 2 else ''
                        url = parts[3] if len(parts) > 3 else ''
                        
                        if title:
                            cleaned_lines.append(f"• {title}")
                            if summary:
                                cleaned_lines.append(f"  {summary}")
                            if url:
                                cleaned_lines.append(f"  🔗 {url}")
                            cleaned_lines.append('')  # Empty line for spacing
                else:
                    # Keep non-table lines (like the header text)
                    if line.strip() and not line.strip().startswith('|'):
                        cleaned_lines.append(line.strip())
            
            return '\n'.join(cleaned_lines)
        except Exception as e:
            logger.error(f"Error cleaning news data: {e}")
            return news_data_raw
    
    def fetch_stock_data(self, stock_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Fetch both price and news data for a stock ticker using existing tools.
        Args:
            stock_ticker: Stock ticker symbol
        Returns: Combined dictionary with processed price analysis and cleaned news, or None if failed
        """
        try:
            # Use existing tools from app.py - they return formatted markdown strings
            price_data_raw = get_stock_price_metric.invoke(stock_ticker)
            news_data_raw = get_stock_news.invoke(stock_ticker)
            
            # Analyze price data with LLM
            price_analysis = self.analyze_price_data_with_llm(stock_ticker, price_data_raw)
            
            # Clean news data
            news_cleaned = self.clean_news_data(news_data_raw)
            
            # Return the processed data
            return {
                'ticker': stock_ticker,
                'price_analysis': price_analysis,
                'news_data': news_cleaned
            }
        except Exception as e:
            logger.error(f"Failed to fetch data for {stock_ticker}: {e}")
            return None


class EmailSender:
    """Handles email composition and sending."""
    
    def __init__(self):
        self.sender_email = os.getenv("EMAIL_SENDER")
        self.sender_password = os.getenv("EMAIL_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        
        if not all([self.sender_email, self.sender_password]):
            logger.error("Email configuration incomplete. Set EMAIL_SENDER and EMAIL_PASSWORD.")
    
    def create_newsletter_html(self, username: str, stocks_data: List[Dict[str, Any]]) -> str:
        """
        Create HTML newsletter content with stock data.
        Args:
            username: User's name for personalization
            stocks_data: List of stock data dictionaries
        Returns: HTML string
        """
        current_date = datetime.now().strftime("%B %d, %Y")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 10px; margin-bottom: 30px; }}
                .header h1 {{ margin: 0; font-size: 28px; }}
                .header p {{ margin: 10px 0 0; font-size: 14px; opacity: 0.9; }}
                .stock-card {{ background: white; border-left: 5px solid #667eea; padding: 25px; margin: 20px 0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
                .stock-ticker {{ font-size: 26px; font-weight: bold; color: #667eea; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #e0e0e0; }}
                .data-section {{ background: #f8f9fa; padding: 20px; margin: 15px 0; border-radius: 6px; border: 1px solid #e0e0e0; }}
                .section-title {{ font-size: 18px; font-weight: bold; color: #2d3748; margin-bottom: 15px; display: flex; align-items: center; }}
                .data-content {{ font-family: 'Courier New', monospace; font-size: 13px; line-height: 1.8; color: #2d3748; white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto; }}
                .footer {{ text-align: center; margin-top: 40px; padding: 20px; color: #6c757d; font-size: 12px; background: white; border-radius: 8px; }}
                a {{ color: #667eea; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>Your Daily Stock Newsletter</h1>
                <p>Hello {username}! Here's your personalized market update for {current_date}</p>
            </div>
        """
        
        if not stocks_data:
            html += """
            <div style="text-align: center; padding: 40px; background: white; border-radius: 8px;">
                <p style="color: #6c757d; font-size: 16px;">No stock data available at this time.</p>
                <p style="color: #6c757d; font-size: 14px;">Please add your favorite stocks in your profile settings.</p>
            </div>
            """
        else:
            for stock_info in stocks_data:
                ticker = stock_info.get('ticker', 'N/A')
                price_analysis = stock_info.get('price_analysis', '')
                news_data = stock_info.get('news_data', '')
                
                html += f"""
                <div class="stock-card">
                    <div class="stock-ticker">{ticker}</div>
                """
                
                # Add LLM-analyzed price data section
                if price_analysis and len(price_analysis) > 20:
                    html += f"""
                    <div class="data-section">
                        <div class="section-title">Price Analysis</div>
                        <div style="font-size: 14px; line-height: 1.8; color: #2d3748; white-space: pre-wrap;">{self._escape_html(price_analysis)}</div>
                    </div>
                    """
                
                # Add cleaned news section
                if news_data and len(news_data) > 20:
                    html += f"""
                    <div class="data-section">
                        <div class="section-title">Latest News</div>
                        <div style="font-size: 14px; line-height: 1.8; color: #2d3748; white-space: pre-wrap;">{self._escape_html(news_data)}</div>
                    </div>
                    """
                
                html += '</div>'
        
        html += """
            <div class="footer">
                <p><strong>Financial Analyst Assistant</strong></p>
                <p>You're receiving this because you subscribed to our daily stock updates.</p>
                <p>To manage your subscription or update your favorite stocks, log in to your account and visit the Profile page.</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters to prevent rendering issues."""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#39;'))
    
    def send_email(self, recipient_email: str, subject: str, html_content: str) -> bool:
        """
        Send email to recipient.
        Args:
            recipient_email: Recipient's email address
            subject: Email subject
            html_content: HTML content of the email
        Returns: True if successful, False otherwise
        """
        if not all([self.sender_email, self.sender_password]):
            logger.error("Email credentials not configured.")
            return False
        
        try:
            # Create message
            message = MIMEMultipart('alternative')
            message['Subject'] = subject
            message['From'] = self.sender_email
            message['To'] = recipient_email
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            message.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
            
            logger.info(f"Email sent successfully to {recipient_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")
            return False


class NewsletterService:
    """Main service for managing newsletter operations."""
    
    def __init__(self):
        self.subscriber_manager = SubscriberManager()
        self.stock_processor = StockDataProcessor()
        self.email_sender = EmailSender()
    
    def process_subscriber(self, subscriber: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Process a single subscriber: fetch data and send email.
        Args:
            subscriber: Subscriber dictionary with user data
        Returns: Tuple of (email, success_status)
        """
        username = subscriber.get('username', 'User')
        email = subscriber.get('email')
        fav_stocks = subscriber.get('fav_stocks', [])
        
        if not email:
            logger.warning(f"No email found for user {username}")
            return (email, False)
        
        if not fav_stocks or len(fav_stocks) == 0:
            logger.info(f"No favorite stocks for user {username}. Sending empty newsletter.")
            fav_stocks = []
        
        # Fetch stock data for favorite stocks using existing tools
        stocks_data = []
        for ticker in fav_stocks[:10]:  # Limit to 10 stocks to avoid long emails
            try:
                data = self.stock_processor.fetch_stock_data(ticker)
                if data:
                    stocks_data.append(data)
            except Exception as e:
                logger.error(f"Error processing stock {ticker} for user {username}: {e}")
                continue
        
        # Create and send email
        subject = f"📊 Your Daily Stock Update - {datetime.now().strftime('%B %d, %Y')}"
        html_content = self.email_sender.create_newsletter_html(username, stocks_data)
        success = self.email_sender.send_email(email, subject, html_content)
        
        return (email, success)
    
    def send_newsletters_to_all_subscribers(self, max_workers: int = 3) -> Dict[str, Any]:
        """
        Send newsletters to all subscribed users using parallel processing.
        Args:
            max_workers: Maximum number of parallel email sending threads
        Returns: Dictionary with statistics
        """
        logger.info("Starting newsletter sending process...")
        
        # Get all subscribers using the existing DatabaseManager
        subscribers = self.subscriber_manager.get_newsletter_subscribers()
        
        if not subscribers:
            logger.info("No subscribers found.")
            return {
                'total_subscribers': 0,
                'emails_sent': 0,
                'emails_failed': 0,
                'success_rate': 0
            }
        
        logger.info(f"Found {len(subscribers)} subscribers.")
        
        # Process subscribers in parallel (with limited concurrency to avoid rate limits)
        successful_sends = 0
        failed_sends = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.process_subscriber, sub): sub for sub in subscribers}
            
            for future in as_completed(futures):
                try:
                    email, success = future.result()
                    if success:
                        successful_sends += 1
                    else:
                        failed_sends += 1
                except Exception as e:
                    logger.error(f"Error processing subscriber: {e}")
                    failed_sends += 1
        
        success_rate = (successful_sends / len(subscribers) * 100) if len(subscribers) > 0 else 0
        
        stats = {
            'total_subscribers': len(subscribers),
            'emails_sent': successful_sends,
            'emails_failed': failed_sends,
            'success_rate': round(success_rate, 2)
        }
        
        logger.info(f"Newsletter sending completed. Stats: {stats}")
        return stats


# Convenience function for scheduler
def send_newsletters_to_subscribers() -> Dict[str, Any]:
    """
    Main entry point for sending newsletters.
    Returns: Dictionary with sending statistics
    """
    service = NewsletterService()
    return service.send_newsletters_to_all_subscribers()


if __name__ == "__main__":
    # Test the newsletter service
    logger.info("Testing newsletter service...")
    stats = send_newsletters_to_subscribers()
    logger.info(f"Test completed with stats: {stats}")
