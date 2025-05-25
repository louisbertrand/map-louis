from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
# import duckdb
import sqlite3
import os
import httpx
import asyncio
import json
import logging
import time
import random
import traceback
from typing import List, Dict, Any, Optional, Generator
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Import config settings
from config import MAX_DATA_DAYS, EXTERNAL_HISTORY_URL, DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM, AUTO_REFRESH_INTERVAL_SECONDS
from config import EMAIL_ENABLED, EMAIL_SERVER, EMAIL_PORT, EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_FROM
from config import SMS_ENABLED, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
import constants  # Application constants and magic numbers


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global tasks tracking
background_task = None

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch periodic data fetch
    global background_task
    last_cleanup = datetime.now() - timedelta(days=1)  # Initialize to run cleanup on first cycle
    
    async def periodic_data_fetch():
        """Periodically fetch device data based on config setting"""
        nonlocal last_cleanup
        while True:
            try:
                logger.info("Running scheduled device data fetch")
                async with httpx.AsyncClient() as client:
                    response = await client.get("http://localhost:8000/api/fetch-device-data")
                    if response.status_code == 200:
                        logger.info("Scheduled device data fetch started successfully")
                    else:
                        logger.error(f"Failed to start scheduled device data fetch: {response.status_code} - {response.text}")
                
                # Run cleanup once per day
                now = datetime.now()
                if (now - last_cleanup).days >= 1:
                    logger.info("Running daily data cleanup")
                    await cleanup_old_data()
                    last_cleanup = now
                
            except Exception as e:
                logger.error(f"Error during scheduled device data fetch: {e}")
            
            # Wait for the configured refresh interval before the next fetch
            logger.info(f"Waiting {AUTO_REFRESH_INTERVAL_SECONDS} seconds until next data refresh")
            await asyncio.sleep(AUTO_REFRESH_INTERVAL_SECONDS)
    
    # Start the periodic task
    background_task = asyncio.create_task(periodic_data_fetch())
    logger.info(f"Started periodic device data fetch task (every {AUTO_REFRESH_INTERVAL_SECONDS} seconds)")
    
    yield
    
    # Shutdown: Cancel the background task
    if background_task:
        logger.info("Cancelling periodic device data fetch task")
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            logger.info("Periodic device data fetch task cancelled")

# Initialize FastAPI app
app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up templates
templates = Jinja2Templates(directory="templates")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Constants from a separate file (module)
SAFECAST_API_BASE = constants.SAFECAST_API_BASE
DEVICE_URNS = constants.DEVICE_URNS

# Database connection management
@contextmanager
def get_db(raise_http_exception: bool = True) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection with proper cleanup.
    
    Args:
        raise_http_exception: If True, raises HTTPException on error. Set to False during initialization.
    """
    conn = None
    try:
        conn = sqlite3.connect('safecast_data.db')
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        if raise_http_exception:
            raise HTTPException(status_code=500, detail="Database connection error")
        raise  # Re-raise the exception if not raising HTTPException
    finally:
        if conn:
            conn.close()

def init_db():
    """Initialize the database with required tables. Makes an effort to preserve existing device data."""
    with get_db(raise_http_exception=False) as conn:
        try:
            # Drop tables that are purely for volatile/historical data or less critical to preserve across restarts
            # Measurements are fetched from API, so can be rebuilt.
            # Transport_info is also derived.
            # KEEP devices and device_fetch_status data if possible.
            volatile_drop_queries = [
                # "DROP TABLE IF EXISTS measurements",  # COMMENTED OUT TO PRESERVE MEASUREMENT DATA BETWEEN RESTARTS
                # "DROP TABLE IF EXISTS transport_info", # Decide if this needs to be dropped
            ]
            
            for query in volatile_drop_queries:
                try:
                    conn.execute(query)
                except Exception as e:
                    logger.warning(f"Warning dropping table {query.split()[-1]}: {e}")
            
            conn.commit() # Commit drops of volatile tables
            
            # Create devices table - IF NOT EXISTS
            conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                device_urn VARCHAR PRIMARY KEY,
                device_id INTEGER,
                device_class VARCHAR,
                device_sn VARCHAR,
                device_contact_name VARCHAR,
                device_contact_email VARCHAR,
                last_seen TIMESTAMP,
                latitude DOUBLE,
                longitude DOUBLE,
                last_reading DOUBLE,
                dev_test BOOLEAN,
                dev_dashboard VARCHAR,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            
            # # Create measurements table - IF NOT EXISTS (though we drop it above, good practice)
            # redundant CREATE SEQUENCE IF NOT EXISTS measurements_id_seq;
            # redundant: DEFAULT nextval('measurements_id_seq'),
            conn.execute("""
              CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY,  
                device_urn TEXT,
                when_captured TIMESTAMP,
                lnd_7318u REAL,
                latitude REAL,
                longitude REAL,
                service_uploaded TEXT,
                service_transport TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(device_urn, when_captured, lnd_7318u)
            )""")
            
            # Create device_fetch_status table - IF NOT EXISTS
            conn.execute("""
            CREATE TABLE IF NOT EXISTS device_fetch_status (
                device_urn TEXT PRIMARY KEY,
                last_fetched TIMESTAMP,
                last_attempted TIMESTAMP,
                last_measurement_time TIMESTAMP,
                fetch_status TEXT,
                error_message TEXT,
                FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
            )""")

            # Create transport_info table - IF NOT EXISTS
            # If you choose not to drop transport_info above, this ensures it's created.
            # If it contains data linked to devices that should persist, don't drop it.
            conn.execute("""
            CREATE TABLE IF NOT EXISTS transport_info (
                device_urn TEXT PRIMARY KEY,
                query_ip TEXT,
                status TEXT,
                as_info TEXT,
                city TEXT,
                country TEXT,
                country_code TEXT,
                isp TEXT,
                latitude REAL,
                longitude REAL,
                org TEXT,
                region TEXT,
                region_name TEXT,
                timezone TEXT,
                zip_code TEXT,
                FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
            )""")
            
            # Create a 'deleted_devices' table to track intentionally removed devices
            conn.execute("""
            CREATE TABLE IF NOT EXISTS deleted_devices (
                device_urn VARCHAR PRIMARY KEY,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            
            # Create alert_thresholds table to store alerting configuration
            conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_thresholds (
                device_urn VARCHAR PRIMARY KEY,
                threshold_cpm INTEGER NOT NULL,
                alert_email VARCHAR,
                alert_sms VARCHAR,
                alert_enabled BOOLEAN DEFAULT 0,
                last_alert_sent TIMESTAMP,
                alert_cooldown_minutes INTEGER DEFAULT 60,
                FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
            )
            """)
            
            # Check which devices have been deleted
            deleted_devices = set()
            try:
                result = conn.execute("SELECT device_urn FROM deleted_devices").fetchall()
                deleted_devices = {row[0] for row in result}
                if deleted_devices:
                    logger.info(f"Found {len(deleted_devices)} previously deleted devices that will not be re-added")
            except Exception as e:
                logger.warning(f"Error fetching deleted devices: {e}")
            
            # Only add devices that haven't been deleted
            for device_urn in DEVICE_URNS:
                # Skip if device was previously deleted
                if device_urn in deleted_devices:
                    logger.info(f"Skipping device {device_urn} as it was previously deleted")
                    continue
                    
                device_id_str = device_urn.split(':')[-1]
                device_id = int(device_id_str) if device_id_str.isdigit() else 0
                
                # Add the device if it doesn't exist. 
                # We only set core identifying info and defaults here.
                # Other fields like lat, lon, last_reading are populated by fetch_and_store_device_data
                conn.execute("""
                    INSERT OR IGNORE INTO devices (
                        device_urn, device_id, device_class, dev_test, dev_dashboard
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    device_urn,
                    device_id,
                    'GeigerCounter', # Default class
                    False,           # Default dev_test
                    f'https://dashboard.radnote.org/d/cdq671mxg2cjka/radnote-overview?var-device=dev:{device_id}'
                ))
                
                # Initialize fetch status if it doesn't exist using INSERT OR IGNORE
                conn.execute("""
                    INSERT OR IGNORE INTO device_fetch_status (device_urn, fetch_status)
                    VALUES (?, 'pending')
                """, (device_urn,))
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_device_urn ON measurements(device_urn)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_when_captured ON measurements(when_captured)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_devices_device_id ON devices(device_id)") # Index for device_id
            conn.execute("CREATE INDEX IF NOT EXISTS idx_transport_info_device_urn ON transport_info(device_urn)")

            conn.commit()
            logger.info("Database initialized (non-destructive for existing device data).")
            
        except Exception as e:
            try:
                conn.rollback() # Attempt to rollback on error during init
            except Exception as rb_exc:
                logger.error(f"Rollback failed during init_db error handling: {rb_exc}")
            logger.error(f"Error initializing database: {e}")
            logger.error(traceback.format_exc())
            # Depending on severity, you might want to re-raise or exit if DB init is critical and fails
            raise # Re-raise the exception to make it visible if startup should halt

# Initialize the database when the application starts
init_db()

def add_sample_data(conn):
    # Create tables if they don't exist
    init_db()
    
    # Add a sample device
    device = (
        "safecast:12345",  # device_urn
        12345,             # device
        "bGeigie",         # device_class
        False,             # dev_test
        "2023-01-01 12:00:00",  # service_uploaded
        "api"              # service_transport
    )
    
    # Clear existing data if tables exist
    try:
        conn.execute("DELETE FROM measurements")
    except Exception as e:
        print(f"Warning: Could not clear measurements table: {e}")
    
    try:
        conn.execute("DELETE FROM locations")
    except Exception as e:
        print(f"Warning: Could not clear locations table: {e}")
    
    try:
        conn.execute("DELETE FROM transport_info")
    except Exception as e:
        print(f"Warning: Could not clear transport_info table: {e}")
    
    try:
        conn.execute("DELETE FROM devices")
    except Exception as e:
        print(f"Warning: Could not clear devices table: {e}")
    
    # Insert sample device
    try:
        conn.execute(
            """
            INSERT INTO devices (device_urn, device, device_class, dev_test, service_uploaded, service_transport)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            device
        )
    except Exception as e:
        print(f"Error inserting device: {e}")
    
    # Add some sample locations
    base_time = datetime.now() - timedelta(days=30)
    for day in range(30):
        timestamp = base_time + timedelta(days=day, hours=0)
        # Add some random variation to the location
        lat = 35.6895 + (0 - 0.5) * 0.1
        lon = 139.6917 + (0 - 0.5) * 0.1
        
        try:
            conn.execute(
                """
                INSERT INTO locations (device_urn, when_captured, latitude, longitude)
                VALUES (?, ?, ?, ?)
                """,
                (device[0], timestamp.isoformat(), lat, lon)
            )
        except Exception as e:
            print(f"Error inserting location: {e}")
    
    # Add transport info
    try:
        transport_info = (
            device[0],  # device_urn
            "192.168.1.1",  # query_ip
            "success",  # status
            "AS12345 Example ISP",  # as_info
            "Tokyo",  # city
            "Japan",  # country
            "JP",  # country_code
            "Example ISP",  # isp
            35.6895,  # latitude
            139.6917,  # longitude
            "Example Org",  # org
            "13",  # region
            "Tokyo",  # region_name
            "Asia/Tokyo",  # timezone
            "100-0001"  # zip_code
        )
        
        conn.execute(
            """
            INSERT INTO transport_info (
                device_urn, query_ip, status, as_info, city, country, country_code,
                isp, latitude, longitude, org, region, region_name, timezone, zip_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            transport_info
        )
    except Exception as e:
        print(f"Error inserting transport info: {e}")
    
    # Add some sample measurements
    base_time = datetime.now() - timedelta(days=30)
    for day in range(30):
        for hour in range(0, 24, 3):  # Every 3 hours
            timestamp = base_time + timedelta(days=day, hours=hour)
            # Add some realistic variation (CPM typically ranges from 5-60 in normal conditions)
            cpm = 20 + (0 - 0.5) * 10  # Random value around 20 CPM
            
            try:
                conn.execute(
                    """
                    INSERT INTO measurements (device_urn, when_captured, lnd_7318u)
                    VALUES (?, ?, ?)
                    """,
                    (device[0], timestamp.isoformat(), cpm)
                )
            except Exception as e:
                print(f"Error inserting measurement: {e}")

# API Endpoints
@app.get("/map", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Render the admin page for managing devices."""
    with get_db() as conn:
        # Get active devices
        devices = conn.execute("SELECT device_urn, device_id, device_class, last_seen FROM devices").fetchall()
        devices = [dict(zip(['device_urn', 'device_id', 'device_class', 'last_seen'], d)) for d in devices]
        
        # Get deleted devices
        deleted_devices = conn.execute("SELECT device_urn, deleted_at FROM deleted_devices ORDER BY deleted_at DESC").fetchall()
        deleted_devices = [dict(zip(['device_urn', 'deleted_at'], d)) for d in deleted_devices]
        
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "devices": devices,
        "deleted_devices": deleted_devices
    })

@app.get("/api/devices")
async def get_devices():
    try:
        with get_db() as conn:
            try:
                # First, check if transport_info table exists
                table_exists = False
                try:
                    check_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transport_info'").fetchone()
                    table_exists = check_table is not None
                except Exception as table_error:
                    logger.warning(f"Error checking if transport_info table exists: {table_error}")
                    table_exists = False
                
                # First, get all devices
                devices_query = """
                    SELECT device_urn, device_id, device_class, last_seen, latitude, longitude, last_reading
                    FROM devices
                """
                
                devices_result = conn.execute(devices_query).fetchall()
                
                if not devices_result:
                    return {"devices": []}
                
                devices = []
                for device_row in devices_result:
                    try:
                        device_urn = device_row[0]
                        device_id = device_row[1]
                        device_class = device_row[2]
                        last_seen = device_row[3]
                        latitude = device_row[4]
                        longitude = device_row[5]
                        last_reading = device_row[6]
                        
                        # Get transport info if the table exists
                        transport_result = None
                        if table_exists:
                            try:
                                transport_query = """
                                    SELECT city, country 
                                    FROM transport_info 
                                    WHERE device_urn = ?
                                    LIMIT 1
                                """
                                transport_result = conn.execute(transport_query, (device_urn,)).fetchone()
                            except Exception as transport_error:
                                logger.warning(f"Error fetching transport info for device {device_urn}: {transport_error}")
                        
                        # Build device data
                        device_data = {
                            "device_urn": device_urn,
                            "device_id": device_id,
                            "device_class": device_class,
                            "latitude": float(latitude) if latitude is not None else None,
                            "longitude": float(longitude) if longitude is not None else None,
                            "last_seen": last_seen.isoformat() if hasattr(last_seen, 'isoformat') else str(last_seen) if last_seen else None,
                            "last_reading": float(last_reading) if last_reading is not None else None,
                            "location": None
                        }
                        
                        # Add location string if transport info is available
                        if transport_result and transport_result[0] and transport_result[1]:
                            device_data["location"] = f"{transport_result[0]}, {transport_result[1]}"
                        
                        devices.append(device_data)
                    except Exception as device_error:
                        logger.error(f"Error processing device row {device_row}: {device_error}")
                        continue
                
                return {"devices": devices}
                
            except Exception as query_error:
                logger.error(f"Database query error in get_devices: {query_error}")
                logger.error(traceback.format_exc())
                raise HTTPException(status_code=500, detail=f"Database query error: {str(query_error)}")
                
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        error_msg = f"Unexpected error in get_devices: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/measurements/{device_urn}")
async def get_measurements(device_urn: str, days: int = Query(default=7, gt=0, le=MAX_DATA_DAYS, description=f"Number of days of data to return (max {MAX_DATA_DAYS} days)")):
    """Get measurements for a specific device over the last N days."""
    try:
        with get_db() as conn:
            # Verify the device exists
            device_exists = conn.execute(
                "SELECT 1 FROM devices WHERE device_urn = ?",
                (device_urn,)
            ).fetchone()
            
            if not device_exists:
                raise HTTPException(status_code=404, detail="Device not found")
            
            # Calculate the date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Add debugging
            logger.info(f"Fetching measurements for {device_urn} from {start_date.isoformat()} to {end_date.isoformat()}")
            
            # Check if any data exists for this device
            count = conn.execute(
                "SELECT COUNT(*) FROM measurements WHERE device_urn = ?",
                (device_urn,)
            ).fetchone()[0]
            
            logger.info(f"Found {count} total measurements for {device_urn}")
            
            # Get measurements for the device within the date range
            query = """
                SELECT 
                    id,
                    device_urn,
                    when_captured,
                    lnd_7318u,
                    latitude,
                    longitude,
                    service_uploaded,
                    service_transport,
                    recorded_at
                FROM measurements
                WHERE device_urn = ? 
                AND when_captured BETWEEN CAST(? AS TIMESTAMP) AND CAST(? AS TIMESTAMP)
                ORDER BY when_captured ASC
            """
            
            # Log the query and parameters for debugging
            logger.info(f"Executing query: {query} with params: {device_urn}, {start_date.isoformat()}, {end_date.isoformat()}")
            
            result = conn.execute(query, (device_urn, start_date.isoformat(), end_date.isoformat()))
            
            # Convert to list of dicts
            measurements = []
            columns = [col[0] for col in result.description] if result.description else []
            for row in result.fetchall():
                measurements.append(dict(zip(columns, row)))
            
            logger.info(f"Query returned {len(measurements)} measurements")
            
            # If no measurements found within time range, return all measurements for this device (limited to 10)
            if not measurements:
                logger.info(f"No measurements found in date range, returning most recent measurements")
                result = conn.execute("""
                    SELECT 
                        id,
                        device_urn,
                        when_captured,
                        lnd_7318u,
                        latitude,
                        longitude,
                        service_uploaded,
                        service_transport,
                        recorded_at
                    FROM measurements
                    WHERE device_urn = ? 
                    ORDER BY when_captured DESC
                    LIMIT 10
                """, (device_urn,))
                
                measurements = []
                columns = [col[0] for col in result.description] if result.description else []
                for row in result.fetchall():
                    measurements.append(dict(zip(columns, row)))
                
                logger.info(f"Fallback query returned {len(measurements)} measurements")
            
            # Create the external history URL using device_urn
            external_history_url = None
            if device_urn:
                external_history_url = EXTERNAL_HISTORY_URL.format(device_urn=device_urn)
            
            return {
                "measurements": measurements,
                "max_days": MAX_DATA_DAYS,
                "external_history_url": external_history_url
            }
    
    except HTTPException as he:
        raise he
    except Exception as e:
        error_msg = f"Error fetching measurements for device {device_urn}: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=error_msg)

# Create necessary directories if they don't exist
os.makedirs("templates", exist_ok=True)
os.makedirs("static/css", exist_ok=True)
os.makedirs("static/js", exist_ok=True)

# Admin API endpoints
class DeviceCreate(BaseModel):
    device_urn: str
    device_id: int
    device_class: str = "GeigerCounter"
    dev_test: bool = False

# Alert configuration model
class AlertConfig(BaseModel):
    device_urn: str
    threshold_cpm: int
    alert_email: str = None
    alert_sms: str = None
    alert_cooldown_minutes: int = 60
    alert_enabled: bool = False

# Alert notification functions
async def send_email_alert(to_email: str, device_urn: str, cpm_value: float, location: str = None):
    """Send an email alert when radiation levels exceed the threshold."""
    if not EMAIL_ENABLED:
        logger.warning("Email alerts are disabled in config. Alert not sent.")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = f"RADIATION ALERT: High CPM detected on {device_urn}"
        
        # Device dashboard link
        device_id = device_urn.split(':')[-1]
        dashboard_link = EXTERNAL_HISTORY_URL.format(device_urn=device_id)
        
        # Email body
        body = f"""
        <html>
            <body>
                <h2>⚠️ Radiation Alert</h2>
                <p>High radiation levels have been detected on device <strong>{device_urn}</strong>.</p>
                <ul>
                    <li><strong>Current CPM:</strong> {cpm_value:.1f}</li>
                    {f"<li><strong>Location:</strong> {location}</li>" if location else ""}
                    <li><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</li>
                </ul>
                <p>Please check the <a href="{dashboard_link}">device dashboard</a> for more information.</p>
                <p>This is an automated alert from your Radiation Map monitoring system.</p>
            </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP(EMAIL_SERVER, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"Email alert sent to {to_email} for device {device_urn}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}")
        return False

async def send_sms_alert(to_number: str, device_urn: str, cpm_value: float):
    """Send an SMS alert when radiation levels exceed the threshold."""
    if not SMS_ENABLED:
        logger.warning("SMS alerts are disabled in config. Alert not sent.")
        return False
    
    try:
        # Import Twilio only if SMS is enabled
        from twilio.rest import Client
        
        # Device ID for dashboard link
        device_id = device_urn.split(':')[-1]
        
        # Message text
        message_text = f"⚠️ RADIATION ALERT: Device {device_urn} detected {cpm_value:.1f} CPM, exceeding threshold. Check dashboard for details."
        
        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        # Send SMS
        message = client.messages.create(
            body=message_text,
            from_=TWILIO_FROM_NUMBER,
            to=to_number
        )
        
        logger.info(f"SMS alert sent to {to_number} for device {device_urn}")
        return True
    
    except ImportError:
        logger.error("Twilio library not installed. Cannot send SMS alerts.")
        return False
    except Exception as e:
        logger.error(f"Failed to send SMS alert: {e}")
        return False

# Alert check function - called when new measurements are received
async def check_and_trigger_alerts(device_urn: str, cpm_value: float, location: str = None):
    """Check if the CPM value exceeds the threshold and trigger alerts if needed."""
    try:
        with get_db() as conn:
            # Get alert configuration for this device
            alert_config = conn.execute("""
                SELECT threshold_cpm, alert_email, alert_sms, alert_enabled, 
                       last_alert_sent, alert_cooldown_minutes
                FROM alert_thresholds
                WHERE device_urn = ?
            """, (device_urn,)).fetchone()
            
            if not alert_config:
                return  # No alert configured for this device
            
            threshold_cpm, alert_email, alert_sms, alert_enabled, last_alert_sent, alert_cooldown = alert_config
            
            # Skip if alerts are disabled
            if not alert_enabled:
                return
            
            # Skip if CPM value doesn't exceed threshold
            if cpm_value <= threshold_cpm:
                return
            
            # Check cooldown period
            now = datetime.now(timezone.utc)
            if last_alert_sent:
                last_sent_dt = datetime.fromisoformat(last_alert_sent.replace("Z", "+00:00")) if isinstance(last_alert_sent, str) else last_alert_sent
                cooldown_minutes = timedelta(minutes=alert_cooldown)
                
                if now - last_sent_dt < cooldown_minutes:
                    logger.info(f"Alert for {device_urn} in cooldown period. Skipping.")
                    return
            
            # Update last_alert_sent timestamp
            conn.execute("""
                UPDATE alert_thresholds
                SET last_alert_sent = ?
                WHERE device_urn = ?
            """, (now, device_urn))
            conn.commit()
            
            # Send alerts asynchronously
            notification_tasks = []
            
            if alert_email:
                notification_tasks.append(send_email_alert(alert_email, device_urn, cpm_value, location))
            
            if alert_sms:
                notification_tasks.append(send_sms_alert(alert_sms, device_urn, cpm_value))
            
            # Execute all notification tasks
            if notification_tasks:
                results = await asyncio.gather(*notification_tasks, return_exceptions=True)
                logger.info(f"Alert notifications for {device_urn}: {results}")
    
    except Exception as e:
        logger.error(f"Error checking alerts for {device_urn}: {e}")

@app.post("/api/admin/devices")
async def add_device(device: DeviceCreate):
    """Add a new device."""
    with get_db() as conn:
        try:
            conn.execute("""
                INSERT INTO devices (device_urn, device_id, device_class, dev_test, dev_dashboard, last_updated)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                device.device_urn,
                device.device_id,
                device.device_class,
                device.dev_test,
                f'https://dashboard.radnote.org/d/cdq671mxg2cjka/radnote-overview?var-device=dev:{device.device_id}'
            ))
            
            # Initialize fetch status
            conn.execute("""
                INSERT OR IGNORE INTO device_fetch_status (device_urn, last_fetched, fetch_status)
                VALUES (?, NULL, 'pending')
            """, (device.device_urn,))
            
            conn.commit()
            return {"message": f"Device {device.device_urn} added successfully"}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/admin/devices/{device_urn}")
async def remove_device(device_urn: str):
    """Remove a device by its URN."""
    with get_db() as conn:
        try:
            # Delete from device_fetch_status first due to foreign key constraint
            conn.execute("DELETE FROM device_fetch_status WHERE device_urn = ?", (device_urn,))
            
            # Delete the device
            result = conn.execute("DELETE FROM devices WHERE device_urn = ? RETURNING device_urn", (device_urn,))
            deleted = result.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Device not found")
                
            # Add to deleted_devices table to prevent re-addition on server restart
            conn.execute(
                "INSERT OR REPLACE INTO deleted_devices (device_urn, deleted_at) VALUES (?, CURRENT_TIMESTAMP)",
                (device_urn,)
            )
            
            conn.commit()
            logger.info(f"Device {device_urn} removed and added to deleted_devices list")
            return {"message": f"Device {device_urn} removed successfully"}
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/devices/restore/{device_urn}")
async def restore_device(device_urn: str):
    """Restore a previously deleted device."""
    with get_db() as conn:
        try:
            # Check if the device is in the deleted_devices table
            deleted = conn.execute("SELECT 1 FROM deleted_devices WHERE device_urn = ?", (device_urn,)).fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Device not found in deleted devices list")
            
            # Remove from deleted_devices table
            conn.execute("DELETE FROM deleted_devices WHERE device_urn = ?", (device_urn,))
            
            # Initialize the device if it's in DEVICE_URNS
            if device_urn in DEVICE_URNS:
                device_id_str = device_urn.split(':')[-1]
                device_id = int(device_id_str) if device_id_str.isdigit() else 0
                
                # Add the device
                conn.execute("""
                    INSERT OR IGNORE INTO devices (
                        device_urn, device_id, device_class, dev_test, dev_dashboard
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    device_urn,
                    device_id,
                    'GeigerCounter', # Default class
                    False,           # Default dev_test
                    f'https://dashboard.radnote.org/d/cdq671mxg2cjka/radnote-overview?var-device=dev:{device_id}'
                ))
                
                # Initialize fetch status
                conn.execute("""
                    INSERT OR IGNORE INTO device_fetch_status (device_urn, fetch_status)
                    VALUES (?, 'pending')
                """, (device_urn,))
                
                conn.commit()
                logger.info(f"Device {device_urn} restored successfully")
                return {"message": f"Device {device_urn} restored successfully"}
            else:
                raise HTTPException(status_code=400, detail=f"Device {device_urn} is not in the configured device list")
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))

# Endpoint to fetch and store device data from Safecast API
@app.get("/api/fetch-device-data")
async def fetch_device_data(background_tasks: BackgroundTasks):
    """
    Fetches the latest data for all configured devices from the Safecast API
    and stores it in the local database.
    """
    devices_to_fetch = []
    with get_db(raise_http_exception=True) as conn:
        try:
            # Check for ongoing fetches (optional, but good practice)
            # status = conn.execute(
            #     "SELECT fetch_status, last_fetched FROM device_fetch_status WHERE fetch_status = 'fetching'"
            # ).fetchone()
            # if status and status[1] and (datetime.utcnow() - datetime.fromisoformat(status[1])).total_seconds() < 300:
            #     return {
            #         "status": "already_fetching",
            #         "message": "A fetch is already in progress. Please wait a few minutes before trying again."
            #     }

            # Validate which devices from DEVICE_URNS actually exist in the DB
            for device_urn_candidate in DEVICE_URNS:
                exists = conn.execute("SELECT 1 FROM devices WHERE device_urn = ?", (device_urn_candidate,)).fetchone()
                if exists:
                    devices_to_fetch.append(device_urn_candidate)
                else:
                    logger.warning(f"Device {device_urn_candidate} from DEVICE_URNS not found in 'devices' table. Skipping for this fetch cycle.")

            if not devices_to_fetch:
                logger.info("No valid devices found to fetch data for.")
                return {
                    "status": "no_devices_to_fetch",
                    "message": "No configured and existing devices to fetch data for."
                }

            # Start background tasks for each existing device
            for device_urn in devices_to_fetch:
                # Update the status to show we're starting a fetch for this device
                conn.execute("""
                    INSERT OR REPLACE INTO device_fetch_status (device_urn, last_fetched, fetch_status, error_message)
                    VALUES (?, CURRENT_TIMESTAMP, 'fetching', NULL)
                """, (device_urn,))
                
                background_tasks.add_task(fetch_and_store_device_data, device_urn)
            
            conn.commit()
            
            return {
                "status": "fetch_started",
                "message": f"Fetching data for {len(devices_to_fetch)} devices in the background: {', '.join(devices_to_fetch)}"
            }
            
        except Exception as e:
            error_msg = f"Error starting data fetch: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc()) # Log the full traceback for better debugging
            
            # Attempt to update status to error for devices that were intended to be fetched
            try:
                if conn: # Ensure connection is still valid
                    for device_urn in devices_to_fetch: # Only try to update devices we were about to fetch
                        conn.execute("""
                            UPDATE device_fetch_status 
                            SET fetch_status = 'error', error_message = ?
                            WHERE device_urn = ?
                        """, (str(e)[:255], device_urn)) # Limit error message length
                    conn.commit()
            except Exception as e_conn_fail:
                logger.error(f"Failed to update device_fetch_status to error during exception handling: {e_conn_fail}")

            raise HTTPException(status_code=500, detail=error_msg)

async def fetch_and_store_device_data(device_urn):
    """Fetch data for a single device and store it."""
    logger.info(f"Starting data fetch for device: {device_urn}")
    # Use the new API endpoint structure - REMOVE .json
    api_url = f"{SAFECAST_API_BASE}/device/{device_urn}" 
    
    last_measurement_time_for_status_update = None
    fetch_status = "error"  # Default status
    error_message = None
    
    try:
        with get_db() as conn:
            device_exists_initial = conn.execute("SELECT 1 FROM devices WHERE device_urn = ?", (device_urn,)).fetchone()
            if not device_exists_initial:
                logger.warning(f"Device {device_urn} not found at the beginning of fetch. Skipping.")
                # Update status to 'error' with a specific message if device is unexpectedly missing
                conn.execute(
                    "UPDATE device_fetch_status SET fetch_status = ?, last_fetched = ?, error_message = ? WHERE device_urn = ?",
                    ("error", datetime.now(timezone.utc), f"Device {device_urn} not found in devices table.", device_urn)
                )
                return

            # Set status to 'fetching'
            conn.execute(
                "UPDATE device_fetch_status SET fetch_status = 'fetching', last_attempted = ?, error_message = NULL WHERE device_urn = ?",
                (datetime.now(timezone.utc), device_urn)
            )
            conn.commit()

        async with httpx.AsyncClient(timeout=60.0) as client:
            logger.info(f"Requesting URL: {api_url}")
            response = await client.get(api_url)
            logger.info(f"Raw Safecast API response status for {device_urn}: {response.status_code}")
            logger.info(f"Raw Safecast API response text (first 500 chars) for {device_urn}: {response.text[:500]}")
            response.raise_for_status() 
            
            data = response.json()
            logger.info(f"Type of data for {device_urn}: {type(data)}")

            if not isinstance(data, dict):
                logger.error(f"Expected a dictionary response from {api_url}, but got {type(data)}")
                error_message = f"Unexpected data type {type(data)} from API."
                raise ValueError(error_message)

            current_values = data.get("current_values")
            if not current_values:
                logger.warning(f"No 'current_values' in API response for {device_urn}. Response: {data}")
                error_message = "No 'current_values' in API response."
                # Potentially update status to 'no_data' or keep 'error'
                fetch_status = "no_data" # Or some other appropriate status
                # No new data to process, but the fetch itself might not be an 'error' if the API call was successful
                # We will update the status to 'no_data' or 'completed' with 0 new measurements later
            
            else:
                logger.info(f"'current_values' for {device_urn}: {current_values}")
                
                latitude = current_values.get("loc_lat")
                longitude = current_values.get("loc_lon")
                # Assuming 'lnd_7318u' is the radiation value we want for 'last_reading'
                # Fallback to other potential radiation fields if necessary, e.g., 'value_hr', 'value_cpm'
                radiation_value = current_values.get("lnd_7318u") 
                captured_at_str = current_values.get("when_captured")

                if latitude is not None and longitude is not None and radiation_value is not None and captured_at_str:
                    try:
                        # Ensure latitude and longitude are valid numbers
                        latitude = float(latitude)
                        longitude = float(longitude)
                        radiation_value = float(radiation_value) # Or int, depending on expected value

                        # Parse the timestamp
                        # Example format: "2025-05-17T02:59:17Z"
                        last_seen_dt = datetime.fromisoformat(captured_at_str.replace("Z", "+00:00"))
                        last_measurement_time_for_status_update = last_seen_dt # For status update
                        
                        with get_db() as conn:
                            # Update the devices table with the latest info
                            conn.execute(
                                """
                                UPDATE devices
                                SET latitude = ?, longitude = ?, last_seen = ?, last_reading = ?
                                WHERE device_urn = ?
                                """,
                                (latitude, longitude, last_seen_dt, radiation_value, device_urn)
                            )
                            
                            # Insert the current reading into measurements table if it doesn't exist
                            conn.execute("""
                                INSERT OR IGNORE INTO measurements (
                                    device_urn, when_captured, lnd_7318u, latitude, longitude, 
                                    service_uploaded, service_transport
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                device_urn,
                                last_seen_dt,
                                radiation_value,
                                latitude,
                                longitude,
                                current_values.get('service_uploaded'),
                                current_values.get('service_transport')
                            ))
                            
                            # Check for alert thresholds and trigger alerts if needed
                            location_str = None
                            try:
                                transport_info = conn.execute(
                                    "SELECT city, country FROM transport_info WHERE device_urn = ?", 
                                    (device_urn,)
                                ).fetchone()
                                
                                if transport_info and transport_info[0] and transport_info[1]:
                                    location_str = f"{transport_info[0]}, {transport_info[1]}"
                            except Exception as loc_err:
                                logger.warning(f"Error getting location for alerts: {loc_err}")
                            
                            # Create a background task for alert checking to avoid blocking
                            asyncio.create_task(check_and_trigger_alerts(
                                device_urn=device_urn,
                                cpm_value=radiation_value,
                                location=location_str
                            ))
                            
                            # Now, process the geiger_history array
                            geiger_history = data.get('geiger_history', [])
                            if geiger_history and isinstance(geiger_history, list):
                                logger.info(f"Processing {len(geiger_history)} geiger_history entries for {device_urn}")
                                entries_inserted = 0
                                
                                for entry in geiger_history:
                                    try:
                                        # Only process valid entries
                                        if not isinstance(entry, dict):
                                            continue
                                            
                                        entry_when_captured = entry.get('when_captured')
                                        entry_reading = entry.get('lnd_7318u')
                                        entry_lat = entry.get('loc_lat')
                                        entry_lon = entry.get('loc_lon')
                                        
                                        if not (entry_when_captured and entry_reading):
                                            continue
                                            
                                        # Convert values to appropriate types
                                        try:
                                            entry_reading = float(entry_reading)
                                            entry_dt = datetime.fromisoformat(entry_when_captured.replace("Z", "+00:00"))
                                            entry_lat = float(entry_lat) if entry_lat is not None else None
                                            entry_lon = float(entry_lon) if entry_lon is not None else None
                                        except (ValueError, TypeError) as ve:
                                            logger.warning(f"Value conversion error for history entry: {ve}")
                                            continue
                                            
                                        # Insert the historical reading
                                        conn.execute("""
                                            INSERT OR IGNORE INTO measurements (
                                                device_urn, when_captured, lnd_7318u, latitude, longitude,
                                                service_uploaded, service_transport
                                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """, (
                                            device_urn,
                                            entry_dt,
                                            entry_reading,
                                            entry_lat,
                                            entry_lon,
                                            entry.get('service_uploaded'),
                                            entry.get('service_transport')
                                        ))
                                        entries_inserted += 1
                                        
                                    except Exception as entry_error:
                                        logger.warning(f"Error processing history entry: {entry_error}")
                                        continue
                                
                                logger.info(f"Inserted {entries_inserted} historical entries for {device_urn}")
                            else:
                                logger.info(f"No valid geiger_history found for {device_urn}")
                            
                            logger.info(f"Updated device {device_urn} with: lat={latitude}, lon={longitude}, reading={radiation_value}, seen={last_seen_dt}")
                            conn.commit()
                        fetch_status = "completed" 
                    except ValueError as ve:
                        logger.error(f"Data parsing error for {device_urn}: {ve}. Data: {current_values}")
                        error_message = f"Data parsing error: {ve}"
                    except Exception as e:
                        logger.error(f"Database update error for {device_urn}: {e}")
                        error_message = f"DB update error: {e}"
                else:
                    missing_fields = []
                    if latitude is None: missing_fields.append("latitude")
                    if longitude is None: missing_fields.append("longitude")
                    if radiation_value is None: missing_fields.append("radiation_value (lnd_7318u)")
                    if captured_at_str is None: missing_fields.append("when_captured")
                    logger.warning(f"Missing critical data in 'current_values' for {device_urn}: {', '.join(missing_fields)}. Data: {current_values}")
                    error_message = f"Missing data in current_values: {', '.join(missing_fields)}"
                    fetch_status = "error" # Or "no_data" if preferred for this case

        # Final status update after attempt
        with get_db() as conn:
            current_time_utc = datetime.now(timezone.utc)
            update_query = """
                UPDATE device_fetch_status 
                SET fetch_status = ?, last_fetched = ?, error_message = ?
            """
            params = [fetch_status, current_time_utc, error_message]

            if last_measurement_time_for_status_update:
                update_query += ", last_measurement_time = ?"
                params.append(last_measurement_time_for_status_update)
            
            update_query += " WHERE device_urn = ?"
            params.append(device_urn)
            
            conn.execute(update_query, tuple(params))
            conn.commit()
            logger.info(f"Fetch status for {device_urn} updated to '{fetch_status}'. Error: {error_message}")

    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP error fetching data for {device_urn}: {exc.response.status_code} - {exc.response.text}")
        error_message = f"HTTP error: {exc.response.status_code}"
        fetch_status = "error"
    except httpx.RequestError as exc:
        logger.error(f"Request error fetching data for {device_urn}: {exc}")
        error_message = f"Request error: {type(exc).__name__}"
        fetch_status = "error"
    except json.JSONDecodeError as exc:
        logger.error(f"JSON decode error for {device_urn}: {exc}. Response text was: {response.text[:500] if 'response' in locals() else 'N/A'}")
        error_message = "JSON decode error"
        fetch_status = "error"
    except ValueError as ve: # Catch specific ValueErrors raised by our logic
        logger.error(f"ValueError during processing for {device_urn}: {ve}")
        # error_message is already set if this is one of our ValueErrors
        if not error_message: error_message = str(ve)
        fetch_status = "error"
    except Exception as e:
        logger.error(f"Unexpected error in fetch_and_store_device_data for {device_urn}: {e}", exc_info=True)
        error_message = f"Unexpected error: {type(e).__name__}"
        fetch_status = "error"
    finally:
        # This finally block ensures status is updated even if an unexpected error occurs before the specific try-except for status update
        try:
            with get_db() as conn:
                # Check if status was already updated by the main logic block
                # This is a safety net; ideally, it's updated before finally.
                status_record = conn.execute("SELECT fetch_status FROM device_fetch_status WHERE device_urn = ?", (device_urn,)).fetchone()
                if status_record and status_record[0] == 'fetching': # If still 'fetching', means an error happened before final update
                    logger.warning(f"Fetch for {device_urn} was interrupted while 'fetching'. Updating status to '{fetch_status}'.")
                    conn.execute(
                        "UPDATE device_fetch_status SET fetch_status = ?, last_fetched = ?, error_message = ? WHERE device_urn = ?",
                        (fetch_status, datetime.now(timezone.utc), error_message or "Interrupted", device_urn)
                    )
                    conn.commit()
        except Exception as db_exc:
            logger.error(f"CRITICAL: Failed to update fetch status in finally block for {device_urn}: {db_exc}")
        
        logger.info(f"Finished data fetch attempt for device: {device_urn} with status: {fetch_status}. Error: {error_message}")

# Pydantic models for API requests/responses
# ... existing code ...

# Create static directories if they don't exist
os.makedirs("static/js", exist_ok=True)

async def startup_tasks():
    """Run startup tasks like initial data fetch"""
    try:
        # Wait a few seconds to let the server fully start
        await asyncio.sleep(3)
        
        # Trigger data fetch for all devices
        logger.info("Running initial device data fetch at startup")
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8000/api/fetch-device-data")
            if response.status_code == 200:
                logger.info("Initial device data fetch started successfully")
            else:
                logger.error(f"Failed to start initial device data fetch: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Error running startup tasks: {e}")

async def cleanup_old_data():
    """Remove measurement data older than MAX_DATA_DAYS to keep the database size manageable."""
    try:
        with get_db(raise_http_exception=False) as conn:
            # Calculate the cutoff date
            cutoff_date = (datetime.utcnow() - timedelta(days=MAX_DATA_DAYS)).isoformat()
            
            # Get count of records to be deleted
            count = conn.execute(
                "SELECT COUNT(*) FROM measurements WHERE when_captured < CAST(? AS TIMESTAMP)",
                (cutoff_date,)
            ).fetchone()[0]
            
            if count > 0:
                # Delete old records
                conn.execute(
                    "DELETE FROM measurements WHERE when_captured < CAST(? AS TIMESTAMP)",
                    (cutoff_date,)
                )
                conn.commit()
                logger.info(f"Deleted {count} measurement records older than {MAX_DATA_DAYS} days")
            else:
                logger.info(f"No measurement records older than {MAX_DATA_DAYS} days to delete")
    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")
        logger.error(traceback.format_exc())

# Alert configuration endpoints
@app.get("/api/admin/alerts/{device_urn}")
async def get_alert_config(device_urn: str):
    """Get alert configuration for a device."""
    with get_db() as conn:
        try:
            # Check if device exists first
            device = conn.execute("SELECT 1 FROM devices WHERE device_urn = ?", (device_urn,)).fetchone()
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
            
            # Get alert config
            alert = conn.execute("""
                SELECT device_urn, threshold_cpm, alert_email, alert_sms, 
                       alert_enabled, alert_cooldown_minutes
                FROM alert_thresholds
                WHERE device_urn = ?
            """, (device_urn,)).fetchone()
            
            if not alert:
                return JSONResponse(status_code=204, content={})  # No content yet
            
            return {
                "device_urn": alert[0],
                "threshold_cpm": alert[1],
                "alert_email": alert[2],
                "alert_sms": alert[3],
                "alert_enabled": bool(alert[4]),
                "alert_cooldown_minutes": alert[5]
            }
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/alerts")
async def set_alert_config(alert: AlertConfig):
    """Set or update alert configuration for a device."""
    with get_db() as conn:
        try:
            # Check if device exists first
            device = conn.execute("SELECT 1 FROM devices WHERE device_urn = ?", (alert.device_urn,)).fetchone()
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
            
            # Insert or update alert config
            conn.execute("""
                INSERT OR REPLACE INTO alert_thresholds
                (device_urn, threshold_cpm, alert_email, alert_sms, alert_enabled, alert_cooldown_minutes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                alert.device_urn,
                alert.threshold_cpm,
                alert.alert_email,
                alert.alert_sms,
                alert.alert_enabled,
                alert.alert_cooldown_minutes
            ))
            
            conn.commit()
            return {"message": f"Alert configuration for {alert.device_urn} updated successfully"}
            
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/admin/alerts/test")
async def test_alert(alert: AlertConfig):
    """Send a test alert using the provided configuration."""
    try:
        # Check if device exists
        with get_db() as conn:
            device = conn.execute("SELECT device_urn, device_id, latitude, longitude FROM devices WHERE device_urn = ?", 
                                 (alert.device_urn,)).fetchone()
            
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
            
            # Try to get location information
            location_str = None
            try:
                transport_info = conn.execute(
                    "SELECT city, country FROM transport_info WHERE device_urn = ?", 
                    (alert.device_urn,)
                ).fetchone()
                
                if transport_info and transport_info[0] and transport_info[1]:
                    location_str = f"{transport_info[0]}, {transport_info[1]}"
            except Exception:
                pass
        
        # Initialize results object
        results = {"email": None, "sms": None}
        
        # Send test notifications
        if alert.alert_email:
            try:
                email_result = await send_email_alert(
                    to_email=alert.alert_email,
                    device_urn=alert.device_urn,
                    cpm_value=alert.threshold_cpm,
                    location=location_str
                )
                results["email"] = "sent successfully" if email_result else "failed to send"
            except Exception as e:
                results["email"] = f"error: {str(e)}"
        
        if alert.alert_sms:
            try:
                sms_result = await send_sms_alert(
                    to_number=alert.alert_sms,
                    device_urn=alert.device_urn,
                    cpm_value=alert.threshold_cpm
                )
                results["sms"] = "sent successfully" if sms_result else "failed to send"
            except Exception as e:
                results["sms"] = f"error: {str(e)}"
        
        # Construct detailed message
        message_parts = []
        if alert.alert_email:
            message_parts.append(f"Email: {results['email']}")
        if alert.alert_sms:
            message_parts.append(f"SMS: {results['sms']}")
        
        return {
            "success": True,
            "message": " | ".join(message_parts)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending test alert: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send test alert: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    try:
        # Initialize database
        init_db()
        
        # Schedule startup tasks to run after server starts
        background_tasks = BackgroundTasks()
        background_tasks.add_task(startup_tasks)
        
        # Run the server
        uvicorn.run(
            "main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Error starting application: {e}")
        logger.error(traceback.format_exc())
        raise
