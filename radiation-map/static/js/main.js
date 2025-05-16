
// Global variables
let map;
let chart = null;
let markers = [];

// Initialize the map and load device data
async function initMap() {
    try {
        // Show loading state
        const loadingElement = document.getElementById('loading');
        loadingElement.style.display = 'flex';
        
        // Hide error message if visible
        const errorElement = document.getElementById('error-message');
        errorElement.classList.add('d-none');
        
        // Initialize map centered on Tokyo by default
        map = L.map('map').setView([35.6895, 139.6917], 13);
        
        // Add OpenStreetMap tiles
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);
        
        // Load device data
        await loadDevices();
        
    } catch (error) {
        console.error('Error initializing map:', error);
        showError('Failed to initialize the map. Please try again later.');
    } finally {
        // Hide loading indicator
        const loadingElement = document.getElementById('loading');
        loadingElement.style.display = 'none';
    }
}

// Load devices from the API
async function loadDevices() {
    try {
        const response = await fetch('/api/devices');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Clear existing markers
        clearMarkers();
        
        if (data.devices && data.devices.length > 0) {
            let bounds = [];
            
            // Add markers for each device
            data.devices.forEach(device => {
                if (device.latitude && device.longitude) {
                    const marker = L.marker(
                        [device.latitude, device.longitude],
                        { icon: createRadiationIcon() }
                    );
                    
                    marker.addTo(map)
                        .bindPopup(createDevicePopup(device));
                    
                    // Store device data in the marker
                    marker.deviceData = device;
                    markers.push(marker);
                    
                    // Add to bounds for fitting the map view
                    bounds.push([device.latitude, device.longitude]);
                }
            });
            
            // Fit map to show all markers if there are any
            if (bounds.length > 0) {
                map.fitBounds(bounds, { padding: [50, 50] });
            }
        } else {
            console.log('No devices found');
            showInfo('No radiation monitoring devices found.');
        }
        
    } catch (error) {
        console.error('Error loading devices:', error);
        showError('Failed to load devices. Please check your connection and try again.');
    }
}

// Create a custom radiation marker icon
function createRadiationIcon() {
    return L.divIcon({
        className: 'radiation-marker',
        html: '☢',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -12]
    });
}

// Create HTML content for device popup
function createDevicePopup(device) {
    return `
        <div class="device-popup">
            <h5>Device: ${device.device_id || 'N/A'}</h5>
            <p><strong>Type:</strong> ${device.device_class || 'N/A'}</p>
            <p><strong>Last seen:</strong> ${formatDate(device.last_seen) || 'N/A'}</p>
            <p><strong>Location:</strong> ${device.location || 'Unknown'}</p>
            <button class="btn btn-primary btn-sm w-100 mt-2" 
                    onclick="loadDeviceData('${device.device_urn}', '${device.device_id}')">
                View Measurements
            </button>
        </div>
    `;
}

// Format date for display
function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Clear all markers from the map
function clearMarkers() {
    markers.forEach(marker => map.removeLayer(marker));
    markers = [];
}

// Show error message
function showError(message) {
    const errorElement = document.getElementById('error-message');
    errorElement.textContent = message;
    errorElement.classList.remove('d-none');
}

// Show info message
function showInfo(message) {
    // You can implement a toast or info banner here
    console.log('Info:', message);
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
    const loadingElement = document.getElementById('loading');
    const chartContainer = document.getElementById('chart-container');
    
    try {
        // Show loading state
        loadingElement.style.display = 'flex';
        
        // Hide any previous errors
        document.getElementById('error-message').classList.add('d-none');
        
        // Fetch measurement data
        const response = await fetch(`/api/measurements/${encodeURIComponent(deviceUrn)}?days=7`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.measurements || data.measurements.length === 0) {
            throw new Error('No measurement data available for this device.');
        }
        
        // Prepare chart data - sort by timestamp to ensure correct order
        const sortedMeasurements = [...data.measurements].sort((a, b) => 
            new Date(a.when_captured) - new Date(b.when_captured)
        );
        
        const timestamps = sortedMeasurements.map(m => new Date(m.when_captured));
        const values = sortedMeasurements.map(m => m.lnd_7318u);
        
        // Get the chart canvas context
        const ctx = document.getElementById('chart').getContext('2d');
        
        // Destroy previous chart if it exists
        if (chart) {
            chart.destroy();
        }
        
        // Create new chart
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: timestamps,
                datasets: [{
                    label: `Radiation (CPM) - Device ${deviceId}`,
                    data: values,
                    borderColor: 'rgba(13, 110, 253, 0.8)',
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    borderWidth: 2,
                    pointRadius: 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: 'rgba(13, 110, 253, 1)',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(13, 110, 253, 1)',
                    tension: 0.3,
                    fill: true
                }]
            },
            options: getChartOptions(deviceId)
        });
        
        // Show the chart container
        chartContainer.classList.remove('d-none');
        
        // Scroll to the chart
        setTimeout(() => {
            chartContainer.scrollIntoView({ behavior: 'smooth' });
        }, 100);
        
    } catch (error) {
        console.error('Error loading device data:', error);
        showError(`Failed to load measurement data: ${error.message}`);
        
        // Hide chart container on error
        chartContainer.classList.add('d-none');
        
    } finally {
        // Hide loading indicator
        loadingElement.style.display = 'none';
    }
}

// Get chart options with consistent styling
function getChartOptions(deviceId) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
            mode: 'nearest',
            axis: 'x',
            intersect: false
        },
        plugins: {
            legend: {
                position: 'top',
                labels: {
                    color: '#495057',
                    font: {
                        weight: '600',
                        family: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
                    },
                    padding: 20
                }
            },
            tooltip: {
                mode: 'index',
                intersect: false,
                backgroundColor: 'rgba(33, 37, 41, 0.95)',
                titleFont: {
                    weight: '600',
                    size: 13
                },
                bodyFont: {
                    weight: '500',
                    size: 13
                },
                padding: 12,
                cornerRadius: 6,
                displayColors: false,
                callbacks: {
                    title: function(context) {
                        const date = new Date(context[0].label);
                        return `Device ${deviceId} - ${date.toLocaleString()}`;
                    },
                    label: function(context) {
                        return `Radiation: ${context.parsed.y.toFixed(2)} CPM`;
                    }
                }
            }
        },
        scales: {
            x: {
                type: 'time',
                time: {
                    unit: 'day',
                    tooltipFormat: 'MMM d, yyyy HH:mm',
                    displayFormats: {
                        hour: 'HH:mm',
                        day: 'MMM d',
                        week: 'MMM d',
                        month: 'MMM yyyy',
                        year: 'yyyy'
                    }
                },
                grid: {
                    display: false,
                    drawBorder: false
                },
                ticks: {
                    color: '#6c757d',
                    maxRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 8
                },
                title: {
                    display: true,
                    text: 'Date/Time',
                    color: '#6c757d',
                    font: {
                        weight: '600',
                        size: 12
                    },
                    padding: { top: 10, bottom: 0 }
                }
            },
            y: {
                beginAtZero: true,
                grid: {
                    color: 'rgba(0, 0, 0, 0.05)',
                    drawBorder: false
                },
                ticks: {
                    color: '#6c757d',
                    padding: 8,
                    callback: function(value) {
                        return value + ' CPM';
                    }
                },
                title: {
                    display: true,
                    text: 'Radiation Level (CPM)',
                    color: '#6c757d',
                    font: {
                        weight: '600',
                        size: 12
                    },
                    padding: { bottom: 10, top: 0 }
                }
            }
        },
        animation: {
            duration: 1000,
            easing: 'easeInOutQuart'
        },
        elements: {
            line: {
                tension: 0.3
            }
        },
        layout: {
            padding: {
                left: 10,
                right: 10,
                top: 10,
                bottom: 10
            }
        }
    };
}

// Close chart container
function closeChart() {
    const chartContainer = document.getElementById('chart-container');
    chartContainer.classList.add('d-none');
    
    // Destroy chart to free up memory
    if (chart) {
        chart.destroy();
        chart = null;
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initialize map when the page loads
    initMap();
    
    // Add event listener for close chart button
    document.getElementById('close-chart').addEventListener('click', closeChart);
});