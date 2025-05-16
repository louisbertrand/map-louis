
    let map;
    let chart = null;

    async function initMap() {
        // Initialize map centered on first device or default to Tokyo
        map = L.map('map').setView([35.6895, 139.6917], 13);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);

        // Show loading indicator
        const loadingElement = document.getElementById('loading');
        loadingElement.style.display = 'block';

        try {
            // Load device data
            const response = await fetch('/api/devices');
            const data = await response.json();
            
            if (data.devices && data.devices.length > 0) {
                // Add markers for each device
                data.devices.forEach(device => {
                    if (device.latitude && device.longitude) {
                        const marker = L.marker([device.latitude, device.longitude])
                            .addTo(map)
                            .bindPopup(`
                                <h3>Device: ${device.device_id || 'N/A'}</h3>
                                <p>Type: ${device.device_class || 'N/A'}</p>
                                <p>Last seen: ${device.last_seen || 'N/A'}</p>
                                <p>Location: ${device.location || 'Unknown'}</p>
                                <button onclick="loadDeviceData('${device.device_urn}', '${device.device_id}')">Show History</button>
                            `);
                        
                        marker.deviceUrn = device.device_urn;
                        marker.deviceId = device.device_id;
                        
                        // If this is the first device, center the map on it
                        if (data.devices.indexOf(device) === 0) {
                            map.setView([device.latitude, device.longitude], 13);
                        }
                    }
                });
            } else {
                console.log('No devices found');
            }
            
        } catch (error) {
            console.error('Error loading device data:', error);
            alert('Failed to load device data. Please check the console for details.');
        } finally {
            // Hide loading indicator
            loadingElement.style.display = 'none';
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

async function loadDeviceData(deviceUrn, deviceId) {
    try {
        const response = await fetch(`/api/measurements/${encodeURIComponent(deviceUrn)}?days=7`);
        const data = await response.json();
        
        if (!data.measurements || data.measurements.length === 0) {
            alert('No measurement data available for this device.');
            return;
        }
        
        // Prepare chart data - sort by timestamp to ensure correct order
        const sortedMeasurements = [...data.measurements].sort((a, b) => 
            new Date(a.when_captured) - new Date(b.when_captured)
        );
        
        const timestamps = sortedMeasurements.map(m => new Date(m.when_captured));
        const values = sortedMeasurements.map(m => m.lnd_7318u);
        
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
                    label: `Radiation (CPM) - Device ${deviceId}`,
                    data: values,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    borderWidth: 2,
                    pointRadius: 2,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'day',
                            tooltipFormat: 'MMM d, yyyy HH:mm',
                            displayFormats: {
                                hour: 'MMM d HH:mm',
                                day: 'MMM d'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Date/Time',
                            color: '#666',
                            font: {
                                weight: 'bold'
                            }
                        },
                        grid: {
                            display: false
                        },
                        ticks: {
                            color: '#666'
                        }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'CPM (Counts Per Minute)',
                            color: '#666',
                            font: {
                                weight: 'bold'
                            }
                        },
                        min: 0,
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            color: '#666',
                            stepSize: 5
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#666',
                            font: {
                                weight: 'bold'
                            }
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        titleFont: {
                            weight: 'bold'
                        },
                        callbacks: {
                            label: function(context) {
                                return `CPM: ${context.parsed.y.toFixed(2)}`;
                            }
                        }
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                },
                animation: {
                    duration: 1000,
                    easing: 'easeInOutQuart'
                }
            }
        });
        
        // Show the chart container with smooth animation
        const chartContainer = document.getElementById('chart-container');
        chartContainer.style.display = 'block';
        chartContainer.style.opacity = '0';
        chartContainer.style.transition = 'opacity 0.5s ease-in-out';
        setTimeout(() => {
            chartContainer.style.opacity = '1';
        }, 10);
        
        // Scroll to the chart
        chartContainer.scrollIntoView({ behavior: 'smooth' });
        
    } catch (error) {
        console.error('Error loading device data:', error);
        alert('Failed to load device data. Please check the console for details.');
    }
}

// Initialize the map when the page loads
document.addEventListener('DOMContentLoaded', initMap);