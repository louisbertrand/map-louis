
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
            const response = await fetch('/api/devices');
            const data = await response.json();
            
            // Add markers for each sensor
            data.devices.forEach(sensor => {
                const marker = L.marker([sensor.latitude, sensor.longitude])
                    .addTo(map)
                    .bindPopup(`
                        <h3>${sensor.device_urn}</h3>
                        <p>${sensor.device_class}</p>
                        <button onclick="loadSensorData('${sensor.device_urn}')">Show History</button>
                    `);
                
                marker.sensorId = sensor.device_urn;
                marker.sensorName = sensor.device_urn;
            });
            
        } catch (error) {
            console.error('Error loading sensor data:', error);
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
    