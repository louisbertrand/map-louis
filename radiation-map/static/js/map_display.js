let map;
let chart = null;

async function initMap() {
    // Initialize map centered on the Toronto area
    map = L.map('map').setView([43.9, -79.0], 10);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // Load sensor data
    try {
        const response = await fetch('/api/devices');
        const data = await response.json();
        
        // Add markers for each sensor
        data.devices.forEach(sensor => {
            // Skip sensors with invalid coordinates
            if (sensor.latitude === null || sensor.longitude === null || 
                isNaN(sensor.latitude) || isNaN(sensor.longitude)) {
                console.warn(`Skipping sensor ${sensor.device_urn} due to invalid coordinates:`, sensor);
                return;
            }
            
            // Create a green circular marker with sensor value
            const reading = Math.round((sensor.last_reading || 0) * 17.5); // Convert to CPM
            const marker = L.circleMarker([sensor.latitude, sensor.longitude], {
                radius: 15,
                fillColor: '#2ecc71',
                color: '#27ae60',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.8
            }).addTo(map);
            
            // Add the reading value as a div icon
            const icon = L.divIcon({
                className: 'sensor-value-label',
                html: `<div style="color: white; font-weight: bold; font-size: 12px;">${reading}</div>`,
                iconSize: [30, 30],
                iconAnchor: [15, 15]
            });
            
            L.marker([sensor.latitude, sensor.longitude], { icon: icon }).addTo(map);
            
            // Get the sensor ID for display
            const sensorId = sensor.device_id || sensor.device_urn.split(':').pop();
            
            // Create popup with graph for sensor data
            marker.bindPopup(`
                <div style="width: 300px;">
                    <h3>Sensor ${sensorId}</h3>
                    <div id="popup-graph-${sensorId}" style="width: 100%; height: 150px;"></div>
                </div>
            `);
            
            marker.on('popupopen', function() {
                setTimeout(() => {
                    createSimpleGraph(sensor.device_urn, `popup-graph-${sensorId}`);
                }, 100);
            });
            
            marker.sensorId = sensor.device_urn;
        });
        
    } catch (error) {
        console.error('Error loading sensor data:', error);
    }
}

async function createSimpleGraph(sensorId, containerId) {
    try {
        const response = await fetch(`/api/measurements/${sensorId}?days=7`);
        const data = await response.json();
        
        if (!data.measurements || data.measurements.length === 0) {
            document.getElementById(containerId).innerHTML = "No data available";
            return;
        }
        
        // Get last 24 measurements for the mini graph
        const measurements = data.measurements.slice(-24);
        const canvas = document.createElement('canvas');
        canvas.width = 300;
        canvas.height = 150;
        
        document.getElementById(containerId).innerHTML = '';
        document.getElementById(containerId).appendChild(canvas);
        
        const ctx = canvas.getContext('2d');
        
        // Draw simple graph
        const values = measurements.map(m => m.lnd_7318u * 17.5); // Convert to CPM
        const maxValue = Math.max(...values, 40); // Ensure at least 0-40 range
        
        // Draw axes
        ctx.beginPath();
        ctx.moveTo(40, 10);
        ctx.lineTo(40, 120);
        ctx.lineTo(280, 120);
        ctx.stroke();
        
        // Draw labels
        ctx.font = '10px Arial';
        ctx.textAlign = 'right';
        ctx.fillText('40 cpm', 35, 15);
        ctx.fillText('20 cpm', 35, 65);
        ctx.fillText('0 cpm', 35, 120);
        
        // Draw time labels
        ctx.textAlign = 'center';
        const firstTime = new Date(measurements[0].when_captured);
        const lastTime = new Date(measurements[measurements.length-1].when_captured);
        
        ctx.fillText(firstTime.getHours() + ':00', 50, 135);
        ctx.fillText(lastTime.getHours() + ':00', 270, 135);
        
        // Draw line
        ctx.beginPath();
        ctx.strokeStyle = 'blue';
        ctx.lineWidth = 2;
        
        values.forEach((value, i) => {
            const x = 40 + (i * 240 / (values.length - 1));
            const y = 120 - (value / maxValue * 110);
            
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        
        ctx.stroke();
        
    } catch (error) {
        console.error('Error creating graph:', error);
        document.getElementById(containerId).innerHTML = "Error loading data";
    }
}

async function loadSensorData(sensorId) {
    try {
        const response = await fetch(`/api/measurements/${sensorId}?days=30`);
        const data = await response.json();
        
        // Prepare chart data
        const timestamps = data.measurements.map(m => new Date(m.when_captured));
        const values = data.measurements.map(m => m.lnd_7318u);
        
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
                    label: `Radiation Level - ${sensorId}`,
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
                            text: 'Radiation'
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