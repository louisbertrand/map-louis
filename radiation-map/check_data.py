import duckdb

# Connect to the database
conn = duckdb.connect('safecast_data.db')

# Check device_fetch_status table
print("=== Device Fetch Status ===")
result = conn.execute('SELECT device_urn, fetch_status, last_fetched FROM device_fetch_status').fetchall()
for row in result:
    print(f"Device: {row[0]}, Status: {row[1]}, Last fetched: {row[2]}")

print("\n=== Device Info ===")
result = conn.execute('SELECT device_urn, device_id, latitude, longitude, last_reading, last_seen FROM devices').fetchall()
for row in result:
    print(f"Device: {row[0]}, ID: {row[1]}, Location: ({row[2]}, {row[3]}), Last reading: {row[4]} cpm, Last seen: {row[5]}")

# Check measurements for each device
for device in conn.execute('SELECT DISTINCT device_urn FROM devices').fetchall():
    device_urn = device[0]
    print(f"\n=== Measurements for {device_urn} ===")
    result = conn.execute(f'''
        SELECT when_captured, lnd_7318u 
        FROM measurements 
        WHERE device_urn = '{device_urn}' 
        ORDER BY when_captured DESC 
        LIMIT 5
    ''').fetchall()
    
    if result:
        for row in result:
            print(f"{row[0]} - {row[1]} cpm")
    else:
        print("No measurements found")

conn.close() 