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
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_urn VARCHAR(50),
            when_captured TIMESTAMP,
            lnd_7318u FLOAT,
            FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS locations (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            device_urn VARCHAR(50),
            when_captured TIMESTAMP,
            latitude FLOAT,
            longitude FLOAT,
            FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
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
            zip_code VARCHAR(20),
            FOREIGN KEY (device_urn) REFERENCES devices(device_urn)
        )
    """)
    
    # Create indexes for better query performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_device_urn ON measurements(device_urn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_measurements_when_captured ON measurements(when_captured)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_locations_device_urn ON locations(device_urn)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_locations_when_captured ON locations(when_captured)")
    
    return conn

def add_sample_data(conn):
    # Add a sample device
    device = (
        "safecast:12345",  # device_urn
        12345,             # device
        "bGeigie",         # device_class
        False,             # dev_test
        "2023-01-01 12:00:00",  # service_uploaded
        "api"              # service_transport
    )
    
    # Clear existing data
    conn.execute("DELETE FROM measurements")
    conn.execute("DELETE FROM locations")
    conn.execute("DELETE FROM transport_info")
    conn.execute("DELETE FROM devices")
    
    # Insert sample device
    conn.execute(
        """
        INSERT INTO devices (device_urn, device, device_class, dev_test, service_uploaded, service_transport)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        device
    )
    
    # Add some sample locations
    base_time = datetime.now() - timedelta(days=30)
    for day in range(30):
        timestamp = base_time + timedelta(days=day, hours=random.randint(0, 23))
        # Add some random variation to the location
        lat = 35.6895 + (random.random() - 0.5) * 0.1
        lon = 139.6917 + (random.random() - 0.5) * 0.1
        
        conn.execute(
            """
            INSERT INTO locations (device_urn, when_captured, latitude, longitude)
            VALUES (?, ?, ?, ?)
            """,
            (device[0], timestamp.isoformat(), lat, lon)
        )
    
    # Add transport info
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
    
    # Add some sample measurements
    base_time = datetime.now() - timedelta(days=30)
    for day in range(30):
        for hour in range(0, 24, 3):  # Every 3 hours
            timestamp = base_time + timedelta(days=day, hours=hour)
            # Add some realistic variation (CPM typically ranges from 5-60 in normal conditions)
            cpm = 20 + (random.random() - 0.5) * 10  # Random value around 20 CPM
            
            conn.execute(
                """
                INSERT INTO measurements (device_urn, when_captured, lnd_7318u)
                VALUES (?, ?, ?)
                """,
                (device[0], timestamp.isoformat(), cpm)
            )

# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("templates/index.html") as f:
        return f.read()

@app.get("/api/devices")
async def get_devices():
    try:
        conn = duckdb.connect('safecast_data.db')
        
        # First, check if the tables exist
        tables = conn.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'main' 
            AND table_name IN ('devices', 'locations', 'transport_info')
        """).fetchall()
        
        if len(tables) < 3:
            # If any table is missing, initialize the database
            conn = init_db()
        
        # Get the latest location for each device
        query = """
            WITH latest_locations AS (
                SELECT device_urn, latitude, longitude, when_captured,
                       ROW_NUMBER() OVER (PARTITION BY device_urn ORDER BY when_captured DESC) as rn
                FROM locations
            )
            SELECT d.device_urn, d.device, d.device_class, 
                   ll.latitude, ll.longitude, ll.when_captured,
                   ti.city, ti.country
            FROM devices d
            LEFT JOIN latest_locations ll ON d.device_urn = ll.device_urn AND (ll.rn = 1 OR ll.rn IS NULL)
            LEFT JOIN transport_info ti ON d.device_urn = ti.device_urn
        """
        
        result = conn.execute(query).fetchall()
        
        devices = []
        for row in result:
            try:
                devices.append({
                    "device_urn": row[0],
                    "device_id": row[1],
                    "device_class": row[2],
                    "latitude": float(row[3]) if row[3] is not None else None,
                    "longitude": float(row[4]) if row[4] is not None else None,
                    "last_seen": row[5].isoformat() if row[5] is not None else None,
                    "location": f"{row[6]}, {row[7]}" if row[6] and row[7] else None
                })
            except Exception as e:
                print(f"Error processing device row: {row}")
                print(f"Error: {e}")
                continue
                
        return {"devices": devices}
        
    except Exception as e:
        print(f"Error in get_devices: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/measurements/{device_urn}")
async def get_measurements(device_urn: str, days: int = 7):
    conn = duckdb.connect('safecast_data.db')
    
    # Get device info
    device = conn.execute(
        "SELECT device_urn, device, device_class FROM devices WHERE device_urn = ?", 
        (device_urn,)
    ).fetchone()
    
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    
    # Get measurements for the last N days
    cutoff_date = datetime.now() - timedelta(days=days)
    
    result = conn.execute("""
        SELECT when_captured, lnd_7318u 
        FROM measurements 
        WHERE device_urn = ? AND when_captured >= ?
        ORDER BY when_captured
    """, (device_urn, cutoff_date.isoformat())).fetchall()
    
    measurements = [
        {
            "when_captured": row[0].isoformat(),
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
