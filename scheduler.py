"""
Scheduler script to run the newsletter sending process.
Automatically sends newsletters daily at 8:00 AM AEST.
Run this script as a background process to keep it running.
"""

import logging
import os
import schedule
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("newsletter_scheduler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Set timezone to AEST (Australian Eastern Standard Time)
AEST = pytz.timezone('Australia/Sydney')

def send_newsletter_job():
    """Job function to send newsletters."""
    try:
        # Load environment variables
        load_dotenv()
        
        # Check required environment variables
        required_vars = ['AZURE_POSTGRES_PASSWORD', 'EMAIL_SENDER', 'EMAIL_PASSWORD']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            return
        
        # Import the send_newsletters function
        from email_util import send_newsletters_to_subscribers
        
        # Get current time in AEST
        current_time = datetime.now(AEST).strftime('%Y-%m-%d %H:%M:%S %Z')
        
        # Run the newsletter sending process in a try-except block with more detailed logging
        try:
            logger.info(f"Starting the newsletter sending process at {current_time}...")
            send_newsletters_to_subscribers()
            logger.info("Newsletter sending process completed successfully.")
        except Exception as inner_e:
            # More detailed logging for the specific error
            import traceback
            logger.error(f"Error in newsletter sending process: {inner_e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise  # Re-raise for outer exception handler
        
    except Exception as e:
        logger.error(f"An error occurred while running the newsletter scheduler: {e}")


def patch_module_dict():
    """
    Apply monkey patch to prevent dictionary changed size during iteration errors.
    This patches the sys.modules dict to prevent issues during imports.
    """
    try:
        # Store a safe copy of sys.modules to prevent dictionary changed size during iteration
        if hasattr(sys, 'modules') and not hasattr(sys, '_safe_modules'):
            sys._safe_modules = list(sys.modules.items())
        logger.info("Applied sys.modules patch to prevent dictionary iteration errors")
    except Exception as e:
        logger.error(f"Failed to apply sys.modules patch: {e}")

def main():
    """Main function to set up and run the scheduler."""
    # Apply patches to prevent common errors
    patch_module_dict()
    
    logger.info("=" * 60)
    logger.info("Newsletter Scheduler started")
    logger.info("Newsletters will be sent daily at 8:00 AM AEST")
    logger.info("Current time: " + datetime.now(AEST).strftime('%Y-%m-%d %H:%M:%S %Z'))
    logger.info("Press Ctrl+C to stop the scheduler")
    logger.info("=" * 60)
    
    # Schedule the job to run every day at 8:00 AM (AEST is UTC+10, so 08:00 AEST is 22:00 UTC the previous day)
    schedule.every().day.at("10:30").do(send_newsletter_job)
    
    # For testing, you can uncomment the line below to run every minute
    # schedule.every(1).minutes.do(send_newsletter_job)
    
    # Optional: Uncomment the line below to run immediately on startup for testing
    #send_newsletter_job()
    
    # Keep the script running
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        logger.info("\nScheduler stopped by user")
    except Exception as e:
        logger.error(f"Scheduler encountered an error: {e}")


if __name__ == "__main__":
    main()