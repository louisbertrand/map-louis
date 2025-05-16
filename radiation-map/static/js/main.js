let map;
let popupChart = null;

// Function to generate fake radiation data
function generateFakeRadiationData(baseValue, hours = 24) {
    const data = [];
    const now = new Date();
    
    // Generate data points for the last 'hours' hours
    for (let i = hours; i >= 0; i--) {
        const timestamp = new Date(now);
        timestamp.setHours(timestamp.getHours() - i);
        
        // Add some randomness to the base value
        const randomFactor = 0.8 + Math.random() * 0.4; // Random between 0.8 and 1.2
        const value = Math.round(baseValue * randomFactor * 10) / 10; // Round to 1 decimal
        
        data.push({
            x: timestamp,
            y: value
        });
    }
    
    return data;
}

// Function to create a small chart in the popup
function createMiniChart(container, data, currentValue) {
    // Create a canvas element for the chart
    const canvas = document.createElement('canvas');
    container.innerHTML = '';
    container.appendChild(canvas);
    
    // Convert data to use timestamps
    const chartData = {
        datasets: [{
            label: 'Radiation (cpm)',
            data: data.map(item => ({
                x: item.x.getTime(),
                y: item.y
            })),
            borderColor: '#3b82f6',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 0,
            pointHoverRadius: 4
        }]
    };
    
    // Create chart with current value and trend
    return new Chart(canvas, {
        type: 'line',
        data: chartData,
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
                            return `Radiation: ${context.raw.y} cpm`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'HH:00'
                        },
                        tooltipFormat: 'MMM d, yyyy HH:mm'
                    },
                    grid: {
                        display: false
                    },
                    ticks: {
                        maxRotation: 0,
                        autoSkip: true,
                        maxTicksLimit: 6
                    }
                },
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Radiation (cpm)'
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        maxTicksLimit: 4,
                        color: '#666',
                        font: {
                            size: 9
                        },
                        callback: function(value) {
                            return value + ' cpm';
                        }
                    }
                }
            },
            elements: {
                line: {
                    borderWidth: 2
                }
            }
        }
    });
}

async function initMap() {
    // Initialize map centered on a default location
    map = L.map('map').setView([43.8, -79.0], 10);
    
    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    try {
        const response = await fetch('/api/devices');
        const data = await response.json();
        
        // Function to create a marker for a sensor
        const createSensorMarker = async (sensor) => {
            if (!sensor.latitude || !sensor.longitude) return null;
            
            // Get the latest measurement for this sensor
            let currentValue = 0;
            try {
                const response = await fetch(`/api/measurements/${sensor.device_urn}?days=1`);
                const data = await response.json();
                if (data.measurements && data.measurements.length > 0) {
                    // Get the most recent measurement
                    const latest = data.measurements.reduce((latest, current) => {
                        return (new Date(current.when_captured) > new Date(latest.when_captured)) ? current : latest;
                    });
                    currentValue = latest.lnd_7318u || 0;
                }
            } catch (error) {
                console.error(`Error fetching measurements for ${sensor.device_urn}:`, error);
                currentValue = 0;
            }
            
            // Generate fake historical data for the chart, but use the real current value
            const fakeData = generateFakeRadiationData(currentValue || 20, 12);
            
            // Create popup content
            const popupContent = document.createElement('div');
            popupContent.style.width = '240px';
            popupContent.style.height = '160px';
            popupContent.style.padding = '8px';
            popupContent.innerHTML = `
                <div style="margin-bottom: 8px;">
                    <div style="font-weight: bold; font-size: 14px; color: #333;">
                        Sensor ${sensor.device_urn.split(':')[1]}
                    </div>
                    <div style="font-size: 12px; color: #666; margin-top: 2px;">
                        ${sensor.latitude?.toFixed(4)}, ${sensor.longitude?.toFixed(4)}
                    </div>
                </div>
                <div id="chart-${sensor.device_urn}" style="width: 100%; height: 100px; margin-top: 8px;"></div>
            `;
            
            // Create marker with popup
            const marker = L.marker([sensor.latitude, sensor.longitude], {
                icon: L.divIcon({
                    className: 'sensor-marker',
                    html: `
                        <div style="
                            background: ${currentValue > 30 ? '#ef4444' : '#10b981'};
                            width: 24px;
                            height: 24px;
                            border-radius: 50%;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            color: white;
                            font-size: 10px;
                            font-weight: bold;
                            border: 2px solid white;
                            box-shadow: 0 0 5px rgba(0,0,0,0.3);
                        ">
                            ${Math.round(currentValue)}
                        </div>
                    `
                })
            }).addTo(map).bindPopup(popupContent);
            
            // Create chart when popup opens
            marker.on('popupopen', function() {
                const chartContainer = document.getElementById(`chart-${sensor.device_urn}`);
                if (chartContainer) {
                    if (popupChart) {
                        popupChart.destroy();
                    }
                    popupChart = createMiniChart(chartContainer, fakeData, currentValue.toFixed(1));
                }
            });
            
            // Clean up chart when popup closes
            marker.on('popupclose', function() {
                if (popupChart) {
                    popupChart.destroy();
                    popupChart = null;
                }
            });
            
            return marker;
        };
        
        // Create markers for all sensors in parallel
        const markerPromises = data.devices.map(createSensorMarker);
        const markers = (await Promise.all(markerPromises)).filter(marker => marker !== null);
        
        // Fit map to show all markers with some padding
        if (markers.length > 0) {
            const group = L.featureGroup(markers);
            map.fitBounds(group.getBounds().pad(0.1));
        }
        
    } catch (error) {
        console.error('Error initializing map:', error);
    }
}

// Add some custom styles for the map
const style = document.createElement('style');
style.textContent = `
    .sensor-marker {
        text-align: center;
        font-weight: bold;
        text-shadow: 0 0 3px rgba(0,0,0,0.5);
    }
    .sensor-marker.high {
        color: #ef4444;
    }
    .sensor-marker.normal {
        color: #10b981;
    }
    .leaflet-popup-content-wrapper {
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
    }
    .leaflet-popup-content {
        margin: 8px 12px;
    }
`;
document.head.appendChild(style);

// Initialize the map when the page loads
document.addEventListener('DOMContentLoaded', function() {
    initMap();
});
