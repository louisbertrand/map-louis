# Radiation Map

A real-time radiation monitoring application that displays data from multiple radiation sensors on an interactive map.

## Features

### Interactive Map
- Real-time display of radiation sensors with current CPM readings
- Circular markers with clear, visible readings
- Popup information windows when clicking on sensors
- Historical data charts for each sensor

### Admin Panel
- Device management (add, remove, restore)
- Data refresh controls
- Alert configuration for radiation threshold monitoring

## Alert System

The application includes a configurable alert system that can notify administrators when radiation levels exceed custom thresholds:

### Alert Configuration
1. Go to the admin panel (`/admin`)
2. Click the "Configure Alert" button for any device
3. Set the following parameters:
   - **CPM Threshold**: The radiation level (in counts per minute) that will trigger an alert
   - **Email for Alerts**: Email address to receive notifications
   - **SMS Number for Alerts**: Phone number to receive SMS notifications (include country code)
   - **Alert Cooldown**: Minimum time between alerts for the same device (prevents notification spam)
   - **Enable Alert**: Toggle to activate/deactivate the alert for this device

### Test Alerts
- Use the "Send Test Alert" button to verify your notification settings work correctly
- This sends a test notification using the current settings without changing the saved configuration

## Installation

1. Clone the repository
2. Install required packages:
   ```
   pip install -r requirements.txt
   ```
3. Configure email and SMS settings in `config.py`

## Configuration

### Email Notifications
Edit `config.py` to configure email settings:
```python
# Email notification settings
EMAIL_ENABLED = True  # Set to True to enable email notifications
EMAIL_SERVER = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USERNAME = "your-email@gmail.com"
EMAIL_PASSWORD = "your-app-password"  # Use app password for Gmail
EMAIL_FROM = "Radiation Alert <your-email@gmail.com>"
```

For Gmail, use an App Password instead of your regular password:
1. Go to your Google Account settings
2. Select Security
3. Under "Signing in to Google", select "App passwords"
4. Generate a new app password for "Mail" and use it in the configuration

### SMS Notifications
Edit `config.py` to configure SMS settings using Twilio:
```python
# SMS notification settings (via Twilio)
SMS_ENABLED = True  # Set to True to enable SMS notifications
TWILIO_ACCOUNT_SID = "your-twilio-account-sid"
TWILIO_AUTH_TOKEN = "your-twilio-auth-token"
TWILIO_FROM_NUMBER = "+1234567890"  # Your Twilio phone number
```

## Running the Application

Start the application using:
```
uvicorn main:app --reload
```

Access the application at:
- Map view: http://localhost:8000/
- Admin panel: http://localhost:8000/admin

## Data Management

- Data is collected every 5 minutes from each sensor
- Historical data is retained for 30 days
- Removed devices remain in the database but are hidden from the map 