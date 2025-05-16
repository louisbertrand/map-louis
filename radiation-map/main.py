from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import duckdb
from datetime import datetime, timedelta
import random

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize DuckDB
def init_db():
    conn = duckdb.connect('safecast_data.db')
    
    # Create tables if they don't exist
    conn.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            device_urn VARCHAR(50) PRIMARY KEY,
            device INTEGER,
            device_class VARCHAR(50),
            dev_test BOOLEAN,
            service_uploaded TIMESTAMP,
            service_transport VARCHAR(100)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id BIGINT,
            device_urn VARCHAR(50),
            when_captured TIMESTAMP,
            lnd_7318u FLOAT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id BIGINT,
            device_urn VARCHAR(50),
            when_captured TIMESTAMP,
            latitude FLOAT,
            longitude FLOAT
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transport_info (
            device_urn VARCHAR(50) PRIMARY KEY,
            query_ip VARCHAR(50),
            status VARCHAR(20),
            as_info VARCHAR(100),
            city VARCHAR(100),
            country VARCHAR(100),
            country_code VARCHAR(10),
            isp VARCHAR(100),
            latitude FLOAT,
            longitude FLOAT,
            org VARCHAR(100),
            region VARCHAR(10),
            region_name VARCHAR(100),
            timezone VARCHAR(50),
            zip_code VARCHAR(20)
        )
    """)
    
    # Create indexes for better query performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_device_urn ON measurements(device_urn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_when_captured ON measurements(when_captured)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_locations_device_urn ON locations(device_urn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_locations_when_captured ON locations(when_captured)")
    
    return conn

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
        timestamp = base_time + timedelta(days=day, hours=random.randint(0, 23))
        # Add some random variation to the location
        lat = 35.6895 + (random.random() - 0.5) * 0.1
        lon = 139.6917 + (random.random() - 0.5) * 0.1
        
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
            cpm = 20 + (random.random() - 0.5) * 10  # Random value around 20 CPM
            
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
async def read_root():
    with open("templates/index.html") as f:
        return f.read()

@app.get("/api/devices")
async def get_devices():
    try:
        db_file = 'safecast_data.db'
        
        # Initialize database if it doesn't exist
        if not os.path.exists(db_file) or os.path.getsize(db_file) == 0:
            print("Database not found or empty, initializing...")
            conn = init_db()
            add_sample_data(conn)
        else:
            # Connect to existing database
            conn = duckdb.connect(db_file)
            
            # Check if database is properly initialized
            try:
                result = conn.execute("SELECT COUNT(*) FROM devices").fetchone()
                if not result or result[0] == 0:
                    print("Database is empty, adding sample data...")
                    add_sample_data(conn)
            except Exception as e:
                print(f"Error checking database: {e}")
                print("Reinitializing database...")
                conn = init_db()
                add_sample_data(conn)
        
        # First, get all devices
        devices_query = """
            SELECT device_urn, device, device_class 
            FROM devices
        """
        
        devices_result = conn.execute(devices_query).fetchall()
        
        if not devices_result:
            return {"devices": []}
        
        devices = []
        for device_row in devices_result:
            device_urn = device_row[0]
            device_id = device_row[1]
            device_class = device_row[2]
            
            # Get the latest location for this device
            location_query = """
                SELECT latitude, longitude, when_captured 
                FROM locations 
                WHERE device_urn = ? 
                ORDER BY when_captured DESC 
                LIMIT 1
            """
            
            location_result = conn.execute(location_query, (device_urn,)).fetchone()
            
            # Get transport info if available
            transport_query = """
                SELECT city, country 
                FROM transport_info 
                WHERE device_urn = ?
                LIMIT 1
            """
            
            transport_result = conn.execute(transport_query, (device_urn,)).fetchone()
            
            # Build device data
            device_data = {
                "device_urn": device_urn,
                "device_id": device_id,
                "device_class": device_class,
                "latitude": None,
                "longitude": None,
                "last_seen": None,
                "location": None
            }
            
            # Add location data if available
            if location_result:
                lat, lon, when = location_result
                if lat is not None and lon is not None:
                    device_data["latitude"] = float(lat)
                    device_data["longitude"] = float(lon)
                if when is not None:
                    device_data["last_seen"] = when.isoformat()
            
            # Add location string if transport info is available
            if transport_result and transport_result[0] and transport_result[1]:
                device_data["location"] = f"{transport_result[0]}, {transport_result[1]}"
            
            devices.append(device_data)
        
        return {"devices": devices}
        
    except Exception as e:
        error_msg = f"Error in get_devices: {str(e)}"
        print(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/api/measurements/{device_urn}")
async def get_measurements(device_urn: str, days: int = 7):
    try:
        conn = duckdb.connect('safecast_data.db')
        
        # Get device info
        device = conn.execute(
            "SELECT device_urn, device, device_class FROM devices WHERE device_urn = ?", 
            (device_urn,)
        ).fetchone()
        
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Get measurements for the last N days
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Use explicit CAST to ensure proper type comparison
        result = conn.execute("""
            SELECT when_captured, lnd_7318u 
            FROM measurements 
            WHERE device_urn = ? 
            AND CAST(when_captured AS TIMESTAMP) >= CAST(? AS TIMESTAMP)
            ORDER BY when_captured
        """, (device_urn, cutoff_date)).fetchall()
        
        measurements = [
            {
                "when_captured": row[0].isoformat() if hasattr(row[0], 'isoformat') else row[0],
                "lnd_7318u": float(row[1]) if row[1] is not None else None
            }
            for row in result
        ]
        
        return {
            "device_urn": device[0],
            "device_id": device[1],
            "device_class": device[2],
            "measurements": measurements
        }
    except Exception as e:
        print(f"Error in get_measurements: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Create templates directory if it doesn't exist
import os
os.makedirs("templates", exist_ok=True)

# Create basic HTML template
with open("templates/index.html", "w") as f:
    f.write("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Radiation Sensor Map</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <style>
            #map { height: 600px; }
            .chart-container {
                width: 100%;
                max-width: 800px;
                margin: 20px auto;
            }
        </style>
    </head>
    <body>
        <h1 style="text-align: center;">Radiation Sensor Network</h1>
        <div id="map"></div>
        <div id="chart" class="chart-container"></div>
        
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script src="/static/js/main.js"></script>
    </body>
    </html>
    """)

# Create static directories if they don't exist
os.makedirs("static/js", exist_ok=True)

# Create main.js
with open("static/js/main.js", "w") as f:
    f.write("""
    let map;
    let chart = null;

    async function initMap() {
        // Initialize map
        map = L.map('map').setView([20, 0], 2);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        // Load sensor data
        try {
            const response = await fetch('/api/sensors');
            const data = await response.json();
            
            // Add markers for each sensor
            data.sensors.forEach(sensor => {
                const marker = L.marker([sensor.latitude, sensor.longitude])
                    .addTo(map)
                    .bindPopup(`
                        <h3>${sensor.name}</h3>
                        <p>${sensor.description}</p>
                        <button onclick="loadSensorData(${sensor.id}, '${sensor.name}')">Show History</button>
                    `);
                
                marker.sensorId = sensor.id;
                marker.sensorName = sensor.name;
            });
            
        } catch (error) {
            console.error('Error loading sensor data:', error);
        }
    }

    async function loadSensorData(sensorId, sensorName) {
        try {
            const response = await fetch(`/api/measurements/${sensorId}?days=30`);
            const data = await response.json();
            
            // Prepare chart data
            const timestamps = data.measurements.map(m => new Date(m.timestamp));
            const values = data.measurements.map(m => m.value);
            
            // Create or update chart
            const ctx = document.getElementById('chart').getContext('2d');
            
            if (chart) {
                chart.destroy();
            }
            
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: timestamps,
                    datasets: [{
                        label: `Radiation Level (${data.unit}) - ${data.sensor_name}`,
                        data: values,
                        borderColor: 'rgb(75, 192, 192)',
                        tension: 0.1
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                unit: 'day'
                            },
                            title: {
                                display: true,
                                text: 'Date'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: `Radiation (${data.unit})`
                            }
                        }
                    }
                }
            });
            
        } catch (error) {
            console.error('Error loading sensor data:', error);
        }
    }

    // Initialize the map when the page loads
    document.addEventListener('DOMContentLoaded', initMap);
    """)

if __name__ == "__main__":
    import uvicorn
    # Initialize database
    conn = init_db()
    conn.close()
    
    # Run the server
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
