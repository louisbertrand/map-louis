import duckdb
from datetime import datetime, timedelta

# Connect to the database
conn = duckdb.connect('safecast_data.db')

# Calculate the timestamp for 30 minutes ago
now = datetime.now()
thirty_min_ago = (now - timedelta(minutes=30)).isoformat()
print(f"Current time: {now.isoformat()}")
print(f"Checking data points since: {thirty_min_ago}")

# Get count of measurements per device in the last 30 minutes
print("\n=== Recent Measurement Counts (Last 30 Minutes) ===")
result = conn.execute(f"""
    SELECT device_urn, COUNT(*) as count 
    FROM measurements 
    WHERE when_captured >= '{thirty_min_ago}'
    GROUP BY device_urn
""").fetchall()

if result:
    for row in result:
        print(f"Device: {row[0]}, Data points: {row[1]}")
    
    # Get total count
    total = conn.execute(f"""
        SELECT COUNT(*) 
        FROM measurements 
        WHERE when_captured >= '{thirty_min_ago}'
    """).fetchone()[0]
    
    print(f"\nTotal data points in the last 30 minutes: {total}")
else:
    print("No data points collected in the last 30 minutes")

# Check the time intervals between successive measurements
print("\n=== Time Intervals Between Measurements ===")
for device_urn in conn.execute("SELECT DISTINCT device_urn FROM measurements").fetchall():
    device_urn = device_urn[0]
    print(f"\nDevice: {device_urn}")
    
    # Get the last 20 measurements ordered by time
    measurements = conn.execute("""
        SELECT when_captured 
        FROM measurements 
        WHERE device_urn = ? 
        ORDER BY when_captured DESC 
        LIMIT 20
    """, (device_urn,)).fetchall()
    
    if len(measurements) < 2:
        print("  Not enough measurements to calculate intervals")
        continue
    
    # Calculate time differences between consecutive measurements
    intervals = []
    for i in range(len(measurements) - 1):
        current = datetime.fromisoformat(str(measurements[i][0]).replace('Z', '+00:00') if 'Z' in str(measurements[i][0]) else str(measurements[i][0]))
        next_point = datetime.fromisoformat(str(measurements[i+1][0]).replace('Z', '+00:00') if 'Z' in str(measurements[i+1][0]) else str(measurements[i+1][0]))
        diff_minutes = abs((current - next_point).total_seconds() / 60)
        intervals.append(diff_minutes)
    
    # Calculate average interval
    avg_interval = sum(intervals) / len(intervals)
    min_interval = min(intervals)
    max_interval = max(intervals)
    
    print(f"  Average interval: {avg_interval:.2f} minutes")
    print(f"  Min interval: {min_interval:.2f} minutes")
    print(f"  Max interval: {max_interval:.2f} minutes")

# Check the oldest and newest data point
print("\n=== Data Age Analysis ===")
oldest_record = conn.execute("""
    SELECT MIN(when_captured) FROM measurements
""").fetchone()[0]

newest_record = conn.execute("""
    SELECT MAX(when_captured) FROM measurements
""").fetchone()[0]

if oldest_record and newest_record:
    oldest_date = datetime.fromisoformat(str(oldest_record).replace('Z', '+00:00') if 'Z' in str(oldest_record) else str(oldest_record))
    newest_date = datetime.fromisoformat(str(newest_record).replace('Z', '+00:00') if 'Z' in str(newest_record) else str(newest_record))
    
    days_range = (newest_date - oldest_date).total_seconds() / (60 * 60 * 24)
    
    print(f"Oldest record: {oldest_date.isoformat()} ({(now - oldest_date).days} days old)")
    print(f"Newest record: {newest_date.isoformat()}")
    print(f"Data spans {days_range:.2f} days")
    
    # Check if we're keeping data older than 30 days
    thirty_days_ago = now - timedelta(days=30)
    if oldest_date < thirty_days_ago:
        older_than_30_days = conn.execute(f"""
            SELECT COUNT(*) FROM measurements
            WHERE when_captured < '{thirty_days_ago.isoformat()}'
        """).fetchone()[0]
        
        print(f"WARNING: Found {older_than_30_days} records older than 30 days!")
        print("This suggests the cleanup function may not be working correctly.")
    else:
        print("No data older than 30 days found, which is correct.")

# Count total records
total_records = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
print(f"\nTotal records in the database: {total_records}")

conn.close() 