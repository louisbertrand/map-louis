let map;
let chart = null;
let popupCharts = {}; // Keep track of chart instances in popups

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
            const reading = Math.round(sensor.last_reading || 0);
            const marker = L.circleMarker([sensor.latitude, sensor.longitude], {
                radius: 20, // Increased size
                fillColor: '#2ecc71',
                color: '#ffffff', // White border
                weight: 3, // Thicker border
                opacity: 1,
                fillOpacity: 0.9
            }).addTo(map);
            
            // Add the reading value as a div icon with improved styling
            const icon = L.divIcon({
                className: 'sensor-value-label',
                html: `<div style="color: white; font-weight: bold; font-size: 16px; display: flex; justify-content: center; align-items: center; width: 100%; height: 100%; text-align: center; margin-top: -3px;">${reading}</div>`,
                iconSize: [40, 40], // Increased size
                iconAnchor: [20, 20] // Centered
            });
            
            // Make this marker non-interactive
            L.marker([sensor.latitude, sensor.longitude], { icon: icon, interactive: false }).addTo(map);
            
            // Get the sensor ID for display
            const sensorId = sensor.device_id || sensor.device_urn.split(':').pop();
            
            // Generate the external URL using the full device_urn
            const externalURL = `https://dashboard.radnote.org/d/cdq671mxg2cjka/radnote-overview?var-device=dev:${sensor.device_urn}`;
            
            // Format the last seen date if available
            let lastSeenFormatted = 'Unknown';
            if (sensor.last_seen) {
                try {
                    const lastSeen = new Date(sensor.last_seen);
                    lastSeenFormatted = lastSeen.toLocaleString();
                    console.log(`Formatted timestamp for ${sensorId}: ${lastSeenFormatted} from ${sensor.last_seen}`);
                } catch (e) {
                    console.error(`Error formatting date: ${e.message}`, sensor.last_seen);
                    lastSeenFormatted = sensor.last_seen || 'Unknown';
                }
            } else {
                console.warn(`No last_seen data available for ${sensorId}`);
            }
            
            console.log(`Device ${sensorId} data:`, sensor);
            
            // Popup with sensor ID, timestamp, link to RadNote dashboard, and chart
            const popupHtml = `
                <div style="width: 280px;">
                    <h3 style="margin: 5px 0; text-align: center; padding-bottom: 2px;">Sensor ${sensorId}</h3>
                    <div style="text-align: center; margin: 8px 0; padding: 8px; background-color: #f0f8ff; border: 1px solid #007bff; border-radius: 5px; font-size: 14px; color: #000;">
                        <strong>Last Reading Time:</strong><br>
                        ${lastSeenFormatted}
                    </div>
                    <div style="text-align: center; margin-bottom: 8px;">
                        <a href="${externalURL}" target="_blank" style="font-size: 12px; color: #3498db; text-decoration: none;">
                            More Information <i style="font-size: 10px;">↗</i>
                        </a>
                    </div>
                    <div id="popup-graph-${sensorId}" style="width: 100%; height: 200px;"></div>
                </div>
            `;
            
            console.log(`Popup HTML for ${sensorId}:`, popupHtml);
            
            marker.bindPopup(popupHtml, { maxWidth: 300 });
            
            // Restore original popupopen event for graph creation
            marker.on('popupopen', function() {
                setTimeout(() => {
                    createChartGraph(sensor.device_urn, `popup-graph-${sensorId}`);
                }, 100); // 100ms delay to ensure popup is in DOM
            });

            // Clean up chart when popup closes
            marker.on('popupclose', function() {
                if (popupCharts[`popup-graph-${sensorId}`]) {
                    popupCharts[`popup-graph-${sensorId}`].destroy();
                    delete popupCharts[`popup-graph-${sensorId}`];
                }
            });
            
            marker.sensorId = sensor.device_urn;
        });
        
    } catch (error) {
        console.error('Error loading sensor data:', error);
    }
}

async function createChartGraph(sensorId, containerId) {
    try {
        // Show loading spinner
        document.getElementById(containerId).innerHTML = `
            <div style="display: flex; justify-content: center; align-items: center; height: 150px;">
                <div style="text-align: center;">
                    <div class="spinner" style="border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                    <p style="margin-top: 10px;">Loading measurement data...</p>
                </div>
            </div>
            <style>
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            </style>
        `;
        
        console.log(`Fetching data for sensor ${sensorId}`);
        const response = await fetch(`/api/measurements/${sensorId}?days=30`);
        const data = await response.json();
        console.log(`Received data for ${sensorId}:`, data);
        
        if (!data.measurements || data.measurements.length === 0) {
            document.getElementById(containerId).innerHTML = `
                <div style="padding: 10px; text-align: center;">
                    <p>No measurement data available</p>
                    <button onclick="retryFetchData('${sensorId}', '${containerId}')" 
                            style="margin-top: 10px; padding: 5px 10px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        Retry
                    </button>
                </div>
            `;
            return;
        }
        
        // Get all measurements for the chart
        const measurements = data.measurements;
        const container = document.getElementById(containerId);
        
        // Clear any existing content
        container.innerHTML = '';
        
        // Create a canvas for the chart
        const canvas = document.createElement('canvas');
        canvas.style.height = '180px';
        container.appendChild(canvas);
        
        // Add external history link if available
        if (data.external_history_url) {
            const linkDiv = document.createElement('div');
            linkDiv.style.textAlign = 'center';
            linkDiv.style.marginTop = '10px';
            linkDiv.style.fontSize = '12px';
            linkDiv.innerHTML = `
                <a href="${data.external_history_url}" target="_blank" style="color: #3498db; text-decoration: none;">
                    More Information <i style="font-size: 10px;">↗</i>
                </a>
            `;
            container.appendChild(linkDiv);
        }
        
        // Prepare data for Chart.js
        const ctx = canvas.getContext('2d');
        
        // Clean up any existing chart
        if (popupCharts[containerId]) {
            popupCharts[containerId].destroy();
            delete popupCharts[containerId];
        }
        
        // Format the data for Chart.js
        const chartData = measurements.map(m => ({
            x: new Date(m.when_captured),
            y: m.lnd_7318u
        }));
        
        // Simplify to just use hour unit with good spacing
        let timeUnit = 'hour';
        
        // Create a Chart.js chart that matches the screenshot style
        popupCharts[containerId] = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: 'Radiation (cpm)',
                    data: chartData,
                    borderColor: 'rgba(54, 162, 235, 1)',
                    backgroundColor: 'rgba(54, 162, 235, 0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: true,
                    tension: 0.2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                return `${Math.round(context.raw.y)} cpm`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        title: {
                            display: true,
                            text: 'Radiation (cpm)',
                            position: 'left'
                        },
                        beginAtZero: true,
                        grid: {
                            display: true,
                            drawBorder: false
                        },
                        ticks: {
                            stepSize: 20
                        }
                    },
                    x: {
                        type: 'time',
                        time: {
                            unit: 'hour',
                            displayFormats: {
                                hour: 'h:mm a'
                            },
                            tooltipFormat: 'MMM D, h:mm a'
                        },
                        grid: {
                            display: false
                        },
                        ticks: {
                            maxRotation: 0,
                            autoSkip: true,
                            maxTicksLimit: 6
                        }
                    }
                }
            }
        });
        
    } catch (error) {
        console.error('Error creating chart:', error);
        document.getElementById(containerId).innerHTML = `
            <div style="padding: 10px; text-align: center;">
                <p>Error loading data: ${error.message}</p>
                <button onclick="retryFetchData('${sensorId}', '${containerId}')" 
                        style="margin-top: 10px; padding: 5px 10px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    Retry
                </button>
            </div>
        `;
    }
}

// Add a helper function to retry fetching data
function retryFetchData(sensorId, containerId) {
    // Show loading indicator
    document.getElementById(containerId).innerHTML = `
        <div style="display: flex; justify-content: center; align-items: center; height: 150px;">
            <div style="text-align: center;">
                <div class="spinner" style="border: 4px solid #f3f3f3; border-top: 4px solid #3498db; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 0 auto;"></div>
                <p style="margin-top: 10px;">Refreshing data...</p>
            </div>
        </div>
    `;
    
    // Trigger a data refresh
    fetch('/api/fetch-device-data')
        .then(response => {
            // Wait 3 seconds to allow background tasks to complete
            setTimeout(() => {
                // Now fetch the measurements again
                createChartGraph(sensorId, containerId);
            }, 3000);
        })
        .catch(error => {
            console.error("Error refreshing data:", error);
            document.getElementById(containerId).innerHTML = `
                <div style="padding: 10px; text-align: center;">
                    <p>Error refreshing data: ${error.message}</p>
                    <button onclick="retryFetchData('${sensorId}', '${containerId}')" 
                            style="margin-top: 10px; padding: 5px 10px; background: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        Try Again
                    </button>
                </div>
            `;
        });
}

async function loadSensorData(sensorId) {
    try {
        const response = await fetch(`/api/measurements/${sensorId}?days=30`);
        const data = await response.json();
        
        if (!data.measurements || data.measurements.length === 0) {
            console.warn(`No measurement data available for ${sensorId}`);
            return;
        }
        
        // Format the data for Chart.js
        const chartData = data.measurements.map(m => ({
            x: new Date(m.when_captured),
            y: m.lnd_7318u
        }));
        
        // Create or update chart
        const chartContainer = document.getElementById('chart');
        const ctx = chartContainer.getContext('2d');
        
        if (chart) {
            chart.destroy();
        }
        
        // Create title with external link if available
        const chartTitle = document.getElementById('chart-title') || document.createElement('h2');
        chartTitle.id = 'chart-title';
        chartTitle.style.textAlign = 'center';
        chartTitle.style.marginBottom = '20px';
        
        // Format title with link if available
        if (data.external_history_url) {
            chartTitle.innerHTML = `
                Radiation History - Device ${sensorId.split(':').pop()} 
                <a href="${data.external_history_url}" target="_blank" style="font-size: 0.7em; color: #3498db; text-decoration: none; margin-left: 10px;">
                    More Information <i style="font-size: 10px;">↗</i>
                </a>
            `;
        } else {
            chartTitle.textContent = `Radiation History - Device ${sensorId.split(':').pop()}`;
        }
        
        // Add title before the chart if it doesn't exist
        if (!document.getElementById('chart-title')) {
            chartContainer.parentNode.insertBefore(chartTitle, chartContainer);
        }
        
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [{
                    label: `Radiation Level - ${sensorId}`,
                    data: chartData,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.2
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        title: {
                            display: true,
                            text: 'Radiation (cpm)'
                        },
                        beginAtZero: true
                    },
                    x: {
                        type: 'time',
                        time: {
                            unit: 'day'
                        },
                        title: {
                            display: true,
                            text: 'Date'
                        }
                    }
                },
                plugins: {
                    title: {
                        display: true,
                        text: `Last ${data.max_days} Days of Radiation Data`
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