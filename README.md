# Financial Analyst Assistant

An AI-powered financial analyst assistant that helps users analyze stocks and get insights about the market.

## Features

- **AI Stock Analysis**: Get detailed information about stocks, including price metrics, fundamental indicators, and recent news
- **User Authentication**: Secure user authentication with PostgreSQL database
- **Newsletter Subscription**: Users can subscribe to a daily newsletter with updates on their favorite stocks
- **User Profiles**: Users can manage their favorite stocks and newsletter preferences

# Architecture
<img width="3122" height="6531" alt="financial_analyst_flow" src="https://github.com/user-attachments/assets/e446d25f-2507-45e5-aa23-22bfd92b1947" />


## Installation

1. Clone this repository
2. Install the required packages:
   ```
   pip install -r Requirements.txt
   ```

## Configuration

Create a `.env` file in the root directory with the following variables:

```
# OpenAI API key
OPENAI_API_KEY=your_openai_api_key

# OpenBB API key
OPENBB_PAT=your_openbb_pat

# PostgreSQL Database Configuration
AZURE_POSTGRES_HOST=financialdb.postgres.database.azure.com
AZURE_POSTGRES_DB=postgres
AZURE_POSTGRES_USER=tony_123
AZURE_POSTGRES_PASSWORD=your_database_password
AZURE_POSTGRES_PORT=5432

# Email Configuration (for newsletters)
EMAIL_SENDER=your_email@example.com
EMAIL_PASSWORD=your_email_password
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
```

## Running the Application

Run the Streamlit app:
```
streamlit run app.py
```

## Setting up the Newsletter Scheduler

The newsletter scheduler is configured to automatically send newsletters daily at **8:00 AM AEST (Australian Eastern Standard Time)**.

### Running the Scheduler

1. Install the required packages:
   ```
   pip install -r Requirements.txt
   ```

2. Make sure your `.env` file is configured with the required email credentials

3. Run the scheduler script:
   ```
   python scheduler.py
   ```

The script will:
- Run continuously in the background
- Send newsletters to all subscribed users every day at 8:00 AM AEST
- Log all activities to `newsletter_scheduler.log`

### Running as a Background Service

#### Windows:
Use `pythonw` to run without a console window:
```
pythonw scheduler.py
```

Or create a Windows Service using NSSM (Non-Sucking Service Manager):
```
nssm install NewsletterScheduler "C:\path\to\python.exe" "C:\path\to\scheduler.py"
nssm start NewsletterScheduler
```

#### Linux/Mac:
Use `nohup` to run in the background:
```
nohup python scheduler.py &
```

Or create a systemd service (Linux):
```
sudo nano /etc/systemd/system/newsletter-scheduler.service
```

Add:
```
[Unit]
Description=Financial Analyst Newsletter Scheduler
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/Financial Analyst
ExecStart=/usr/bin/python3 scheduler.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:
```
sudo systemctl enable newsletter-scheduler
sudo systemctl start newsletter-scheduler
```

### Testing the Scheduler

To test immediately without waiting for 8:00 AM, uncomment this line in `scheduler.py`:
```python
# send_newsletter_job()  # Uncomment to run immediately
```

### Manual Execution

To send newsletters manually at any time (without the scheduler):
```
python -c "from email import send_newsletters_to_subscribers; send_newsletters_to_subscribers()"
```

## Database Schema

The application uses a PostgreSQL database with the following schema:

```sql
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
```

## Project Structure

- `app.py`: Main Streamlit application
- `auth.py`: Authentication module
- `email.py`: Email and newsletter functionality
- `user_profile.py`: User profile management
- `scheduler.py`: Daily newsletter scheduler
