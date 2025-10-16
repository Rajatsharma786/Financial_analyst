"""
Newsletter scheduler API for triggering newsletter sending via Google Cloud Scheduler.
Exposes FastAPI endpoints to be called by Cloud Scheduler at scheduled times.
"""

import logging
import os
from datetime import datetime
import pytz
from dotenv import load_dotenv
import sys
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import traceback

# Load environment variables
load_dotenv()

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

# Create FastAPI app
app = FastAPI(
    title="Financial Analyst Newsletter Scheduler",
    description="API for scheduling and triggering newsletter sending",
    version="1.0.0"
)

def send_newsletter_job():
    """Job function to send newsletters."""
    try:
        # Check required environment variables
        required_vars = ['AZURE_POSTGRES_PASSWORD', 'EMAIL_SENDER', 'EMAIL_PASSWORD']
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        
        if missing_vars:
            error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Import the send_newsletters function
        from email_util import send_newsletters_to_subscribers
        
        # Get current time in AEST
        current_time = datetime.now(AEST).strftime('%Y-%m-%d %H:%M:%S %Z')
        
        # Run the newsletter sending process
        logger.info(f"Starting the newsletter sending process at {current_time}...")
        send_newsletters_to_subscribers()
        logger.info("Newsletter sending process completed successfully.")
        
        return {
            "status": "success",
            "message": "Newsletters sent successfully",
            "timestamp": current_time
        }
        
    except Exception as e:
        # More detailed logging for the specific error
        error_trace = traceback.format_exc()
        logger.error(f"Error in newsletter sending process: {e}")
        logger.error(f"Traceback: {error_trace}")
        raise


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "service": "Financial Analyst Newsletter Scheduler",
        "status": "running",
        "timezone": str(AEST),
        "current_time": datetime.now(AEST).strftime('%Y-%m-%d %H:%M:%S %Z')
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(AEST).isoformat()
    }


@app.post("/send-newsletter")
async def trigger_newsletter(background_tasks: BackgroundTasks):
    """
    Endpoint to trigger newsletter sending.
    This endpoint should be called by Google Cloud Scheduler.
    """
    try:
        logger.info("Newsletter trigger received from Cloud Scheduler")
        
        # Run the newsletter job in the background
        background_tasks.add_task(send_newsletter_job)
        
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "message": "Newsletter sending process started",
                "timestamp": datetime.now(AEST).strftime('%Y-%m-%d %H:%M:%S %Z')
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to trigger newsletter: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger newsletter: {str(e)}"
        )


@app.post("/send-newsletter-sync")
async def trigger_newsletter_sync():
    """
    Synchronous endpoint to trigger newsletter sending.
    This endpoint waits for the newsletter to be sent before returning.
    Use this for testing or when you need confirmation of completion.
    """
    try:
        logger.info("Synchronous newsletter trigger received")
        result = send_newsletter_job()
        
        return JSONResponse(
            status_code=200,
            content=result
        )
        
    except Exception as e:
        logger.error(f"Failed to send newsletter: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send newsletter: {str(e)}"
        )



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
    """
    Run the FastAPI server directly for local testing.
    In production, this is handled by the container startup script.
    """
    import uvicorn
    
    # Apply patches to prevent common errors
    patch_module_dict()
    
    logger.info("=" * 60)
    logger.info("Newsletter Scheduler API starting...")
    logger.info("Current time: " + datetime.now(AEST).strftime('%Y-%m-%d %H:%M:%S %Z'))
    logger.info("API will be available at http://0.0.0.0:8000")
    logger.info("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")



if __name__ == "__main__":
    main()