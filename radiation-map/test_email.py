#!/usr/bin/env python
"""
Test script to verify email sending functionality.
Run this script to test if your email configuration works correctly.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys

# Import email settings from config
from config import (
    EMAIL_ENABLED, 
    EMAIL_SERVER, 
    EMAIL_PORT, 
    EMAIL_USERNAME, 
    EMAIL_PASSWORD, 
    EMAIL_FROM
)

def test_email(recipient_email):
    """Send a test email to verify SMTP configuration."""
    if not EMAIL_ENABLED:
        print("⚠️ Email is disabled in config.py. Setting EMAIL_ENABLED = True temporarily for this test.")
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = recipient_email
        msg['Subject'] = "Test Email from Radiation Map"
        
        # Email body
        body = """
        <html>
            <body>
                <h2>Email Configuration Test</h2>
                <p>This is a test email from your Radiation Map application.</p>
                <p>If you're seeing this, your email configuration is working correctly!</p>
                <hr>
                <p><b>Configuration Details:</b></p>
                <ul>
                    <li>Server: {server}</li>
                    <li>Port: {port}</li>
                    <li>Username: {username}</li>
                </ul>
            </body>
        </html>
        """.format(
            server=EMAIL_SERVER,
            port=EMAIL_PORT,
            username=EMAIL_USERNAME
        )
        
        msg.attach(MIMEText(body, 'html'))
        
        # Connect to server and send
        print(f"Connecting to {EMAIL_SERVER}:{EMAIL_PORT}...")
        with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
            server.starttls()
            print(f"Logging in as {EMAIL_USERNAME}...")
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            print(f"Sending email to {recipient_email}...")
            server.send_message(msg)
            
        print("✅ Email sent successfully!")
        return True
    
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        
        if "authentication failed" in str(e).lower():
            print("\n🔑 Authentication Error Tips:")
            print("- For Gmail: Ensure you're using an App Password, not your regular password")
            print("- Generate App Password: Google Account → Security → App passwords")
            print("- Make sure EMAIL_USERNAME matches the account for the App Password")
        
        if "blocked" in str(e).lower() or "spam" in str(e).lower():
            print("\n🔒 Email Blocked Tips:")
            print("- Check if your email provider is blocking the connection")
            print("- Try enabling 'Less secure app access' in your email settings")
            print("- Check if you need to confirm a security prompt in your email")
        
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        recipient = sys.argv[1]
    else:
        recipient = input("Enter recipient email address: ")
    
    test_email(recipient) 