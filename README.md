# LinkedIn Games Bot

A WhatsApp bot powered by Twilio that sends game notifications and manages game scores for LinkedIn games.

## Features

- Sends scheduled game notifications via WhatsApp
- Tracks and manages game results
- Database persistence using SQLite
- Scheduled tasks for automatic game drops and checks
- Timezone-aware scheduling
- Flask web server for Twilio webhook integration

## Requirements

- Python 3.x
- Twilio account with WhatsApp API access
- Flask
- APScheduler
- python-dotenv
- Twilio Python SDK
- pytz

## Installation

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your configuration:
   ```
   TWILIO_ACCOUNT_SID=your_account_sid
   TWILIO_AUTH_TOKEN=your_auth_token
   TWILIO_WHATSAPP_FROM=whatsapp:+your_twilio_number
   
   USER1=whatsapp:+user_phone_number
   USER2=whatsapp:+user_phone_number
   
   TIMEZONE=Asia/Kolkata
   DROP_HOUR=13
   DROP_MINUTE=30
   CHECK_HOUR=10
   CHECK_MINUTE=0
   ```

## Running the Bot

```bash
python main.py
```

The bot will start the Flask server and scheduled tasks. By default, it listens on `http://localhost:5000`

## Configuration

Environment variables:
- `TWILIO_ACCOUNT_SID` - Your Twilio account SID
- `TWILIO_AUTH_TOKEN` - Your Twilio auth token
- `TWILIO_WHATSAPP_FROM` - Your Twilio WhatsApp number
- `USER1` - First user's WhatsApp number
- `USER2` - Second user's WhatsApp number
- `TIMEZONE` - Timezone for scheduling (default: Asia/Kolkata)
- `DROP_HOUR` - Hour for game drop notification (default: 13)
- `DROP_MINUTE` - Minute for game drop notification (default: 30)
- `CHECK_HOUR` - Hour for game check notification (default: 10)
- `CHECK_MINUTE` - Minute for game check notification (default: 0)

## Security Note

**IMPORTANT**: Never commit your `.env` file to version control. The `.gitignore` file is configured to exclude it. Store your sensitive credentials securely.
