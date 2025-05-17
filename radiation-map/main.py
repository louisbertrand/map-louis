from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import duckdb
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
from datetime import datetime, timedelta
from contextlib import contextmanager
from pathlib import Path
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

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

# Constants
SAFECAST_API_BASE = "https://tt.safecast.org"
DEVICE_URNS = [
    "geigiecast:62007",
    "geigiecast-zen:65049",
    "geigiecast:62106",
    "geigiecast:63209"
]

# Database connection management
@contextmanager
def get_db(raise_http_exception: bool = True) -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Get a database connection with proper cleanup.
    
    Args:
        raise_http_exception: If True, raises HTTPException on error. Set to False during initialization.
    """
    conn = None
    try:
        conn = duckdb.connect('safecast_data.db')
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
    """Initialize the database with required tables."""
    with get_db(raise_http_exception=False) as conn:
        try:
            # Drop and recreate tables to ensure clean state
            drop_queries = [
                "DROP TABLE IF EXISTS measurements",
                "DROP TABLE IF EXISTS device_fetch_status",
                "DROP TABLE IF EXISTS devices",
                "DROP TABLE IF EXISTS transport_info",
            ]
            
            for query in drop_queries:
                try:
                    conn.execute(query)
                except Exception as e:
                    logger.warning(f"Error dropping table: {e}")
            
            # Commit after dropping tables
            conn.commit()
            
            # Create devices table
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
            
            # Create measurements table
            conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS measurements_id_seq;
            
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY DEFAULT nextval('measurements_id_seq'),
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
            
            # Create device_fetch_status table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS device_fetch_status (
                device_urn TEXT PRIMARY KEY,
                last_fetched TIMESTAMP,
                last_measurement_time TIMESTAMP,
                fetch_status TEXT,
                error_message TEXT,
                FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
            )""")
            
            # Add all devices
            for device_urn in DEVICE_URNS:
                device_id = device_urn.split(':')[-1]  # Extract device ID from URN
                
                # Add the device if it doesn't exist
                conn.execute("""
                    INSERT OR IGNORE INTO devices (
                        device_urn, device_id, device_class, dev_test, dev_dashboard
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    device_urn,
                    int(device_id) if device_id.isdigit() else 0,  # Convert to int if possible
                    'GeigerCounter',
                    False,
                    f'https://safecast.org/tilemap/?y1=90&x1=-180&y2=-90&x2=180&l=0&m=0&sense=1&since=0&until=0&devices={device_id}'
                ))
                
                # Initialize fetch status if it doesn't exist
                conn.execute("""
                    INSERT OR IGNORE INTO device_fetch_status (device_urn, last_fetched, fetch_status)
                    VALUES (?, NULL, 'pending')
                """, (device_urn,))
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_device_urn ON measurements(device_urn)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_when_captured ON measurements(when_captured)")
            
            conn.commit()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            try:
                conn.rollback()
            except:
                pass
            logger.error(f"Error initializing database: {e}")
            logger.error(traceback.format_exc())
            raise

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
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Render the admin page for managing devices."""
    with get_db() as conn:
        devices = conn.execute("SELECT device_urn, device_id, device_class, last_seen FROM devices").fetchall()
        devices = [dict(zip(['device_urn', 'device_id', 'device_class', 'last_seen'], d)) for d in devices]
    return templates.TemplateResponse("admin.html", {"request": request, "devices": devices})

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
async def get_measurements(device_urn: str, days: int = Query(7, gt=0, le=365, description="Number of days of data to return")):
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
            
            # Get measurements for the device within the date range
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
                AND when_captured BETWEEN CAST(? AS TIMESTAMP) AND CAST(? AS TIMESTAMP)
                ORDER BY when_captured ASC
            """, (device_urn, start_date.isoformat(), end_date.isoformat()))
            
            # Convert to list of dicts
            measurements = []
            columns = [col[0] for col in result.description] if result.description else []
            for row in result.fetchall():
                measurements.append(dict(zip(columns, row)))
            
            return {"measurements": measurements}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        error_msg = f"Error fetching measurements for device {device_urn}: {str(e)}"
        logger.error(error_msg)
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
                f'https://safecast.org/tilemap/?y1=90&x1=-180&y2=-90&x2=180&l=0&m=0&sense=1&since=0&until=0&devices={device.device_id}'
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
            result = conn.execute("DELETE FROM devices WHERE device_urn = ? RETURNING device_urn", (device_urn,))
            deleted = result.fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="Device not found")
            conn.commit()
            return {"message": f"Device {device_urn} removed successfully"}
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
    with get_db(raise_http_exception=True) as conn:
        try:
            # Check if we already have a recent fetch in progress for any device
            status = conn.execute(
                "SELECT fetch_status, last_fetched FROM device_fetch_status WHERE fetch_status = 'fetching'"
            ).fetchone()
            
            if status and status[1] and (datetime.utcnow() - datetime.fromisoformat(status[1])).total_seconds() < 300:
                return {
                    "status": "already_fetching",
                    "message": "A fetch is already in progress. Please wait a few minutes before trying again."
                }
            
            # Start background tasks for each device
            for device_urn in DEVICE_URNS:
                # Update the status to show we're starting a fetch for this device
                conn.execute("""
                    INSERT OR REPLACE INTO device_fetch_status (device_urn, last_fetched, fetch_status)
                    VALUES (?, CURRENT_TIMESTAMP, 'fetching')
                """, (device_urn,))
                
                # Start the background task for this device
                background_tasks.add_task(fetch_and_store_device_data, device_urn)
            
            conn.commit()
            
            return {
                "status": "fetch_started",
                "message": f"Fetching data for {len(DEVICE_URNS)} devices in the background"
            }
            
        except Exception as e:
            error_msg = f"Error starting data fetch: {str(e)}"
            logger.error(error_msg)
            
            # Update the status to show the error for all devices
            for device_urn in DEVICE_URNS:
                conn.execute("""
                    UPDATE device_fetch_status 
                    SET fetch_status = 'error', error_message = ?
                    WHERE device_urn = ?
                """, (str(e), device_urn))
            conn.commit()
            
            raise HTTPException(status_code=500, detail=error_msg)

async def fetch_and_store_device_data(device_urn):
    """
    Fetches device data from the Safecast API and stores it in the database.
    This function is designed to be run in the background.
    
    Args:
        device_urn: The URN of the device to fetch data for
    """
    with get_db(raise_http_exception=True) as conn:
        try:
            # Extract device ID from URN (handle both formats: 'geigiecast:123' and 'geigiecast-zen:123')
            device_id = device_urn.split(':')[-1]  # Get the part after the last colon
            
            # Build the API URL for the device endpoint
            url = f"{SAFECAST_API_BASE}/device/{device_urn}"
            
            # Make the API request
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                
                # Parse the response as JSON
                data = response.json()
                
                # Check if we have current values
                if 'current_values' not in data:
                    logger.warning(f"No current values found for device {device_urn}")
                    return
                
                current_values = data['current_values']
                
                # Check if there's a measurement
                if 'lnd_7318u' not in current_values or current_values['lnd_7318u'] is None:
                    logger.warning(f"No radiation measurement found for device {device_urn}")
                    return
                
                # Update device information with location if available
                if current_values.get('loc_lat') and current_values.get('loc_lon'):
                    conn.execute("""
                        UPDATE devices 
                        SET 
                            latitude = ?,
                            longitude = ?,
                            last_seen = ?
                        WHERE device_urn = ?
                    """, (
                        current_values['loc_lat'],
                        current_values['loc_lon'],
                        current_values.get('when_captured', '').replace('Z', '+00:00'),
                        device_urn
                    ))
                    conn.commit()
                
                # Prepare the measurement data
                measurement = {
                    'captured_at': current_values.get('when_captured', '').replace('Z', '+00:00'),
                    'latitude': current_values.get('loc_lat'),
                    'longitude': current_values.get('loc_lon'),
                    'value': current_values['lnd_7318u'],
                    'unit': 'cpm',
                    'device_urn': device_urn,
                    'device_id': current_values.get('device'),
                    'device_class': current_values.get('device_class', 'GeigerCounter')
                }
                
                # Convert to a list for consistent processing
                measurements_data = [measurement] if measurement['value'] is not None else []
            
            # Store the measurements in the database
            new_measurements = 0
            for measurement in measurements_data:
                try:
                    captured_at = measurement.get('captured_at')
                    
                    conn.execute("""
                        INSERT OR IGNORE INTO measurements (
                            device_urn, when_captured, lnd_7318u, latitude, longitude,
                            service_uploaded, service_transport
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        device_urn,
                        captured_at,
                        measurement.get('value'),
                        measurement.get('latitude'),
                        measurement.get('longitude'),
                        measurement.get('service_uploaded'),
                        measurement.get('service_transport')
                    ))
                    new_measurements += 1
                except Exception as e:
                    logger.error(f"Error inserting measurement for device {device_urn}: {e}")
            
            # Update the device's last seen time and location if we have new measurements
            if new_measurements > 0:
                # First, ensure the device exists in the devices table
                conn.execute("""
                    INSERT OR IGNORE INTO devices (device_urn, device_id, device_class)
                    VALUES (?, ?, ?)
                """, (device_urn, device_id, 'GeigerCounter'))
                
                # Then update the last seen time and location
                conn.execute("""
                    UPDATE devices 
                    SET last_seen = CURRENT_TIMESTAMP,
                        latitude = (SELECT latitude FROM measurements 
                                  WHERE device_urn = ? 
                                  ORDER BY when_captured DESC LIMIT 1),
                        longitude = (SELECT longitude FROM measurements 
                                   WHERE device_urn = ? 
                                   ORDER BY when_captured DESC LIMIT 1),
                        last_reading = (SELECT lnd_7318u FROM measurements 
                                      WHERE device_urn = ? 
                                      ORDER BY when_captured DESC LIMIT 1)
                    WHERE device_urn = ?
                """, (device_urn, device_urn, device_urn, device_urn))
            
            # Update fetch status
            conn.execute("""
                UPDATE device_fetch_status 
                SET last_fetched = CURRENT_TIMESTAMP,
                    last_measurement_time = (SELECT MAX(when_captured) FROM measurements WHERE device_urn = ?),
                    fetch_status = 'success',
                    error_message = NULL
                WHERE device_urn = ?
            """, (device_urn, device_urn))
            
            conn.commit()
            logger.info(f"Successfully fetched {new_measurements} new measurements for device {device_urn}")
            
        except Exception as e:
            error_msg = f"Error in background fetch for device {device_urn}: {str(e)}"
            logger.error(error_msg)
            
            # Update fetch status with error
            conn.execute("""
                UPDATE device_fetch_status 
                SET fetch_status = 'error', 
                    error_message = ?,
                    last_fetched = CURRENT_TIMESTAMP
                WHERE device_urn = ?
            """, (device_urn, str(e))) # Corrected: Ensured str(e) is passed for the error message
            conn.commit()

# Create static directories if they don't exist
os.makedirs("static/js", exist_ok=True)

if __name__ == "__main__":
    import uvicorn
    
    try:
        # Initialize database
        init_db()
        
        # Run the server
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Error starting application: {e}")
        logger.error(traceback.format_exc())
        raise
