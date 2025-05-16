
    let map;
    let chart = null;

    // Format date for display
    function formatDate(dateString) {
        if (!dateString) return 'N/A';
        const options = { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        return new Date(dateString).toLocaleDateString(undefined, options);
    }

    // Create a custom radiation icon
    function createRadiationIcon() {
        return L.divIcon({
            className: 'radiation-marker',
            html: '☢',
            iconSize: [30, 30],
            iconAnchor: [15, 30],
            popupAnchor: [0, -30]
        });
    }

    // Initialize the map
    async function initMap() {
        try {
            // Initialize map with a view of the world
            map = L.map('map').setView([35.6895, 139.6917], 12);  // Centered on Tokyo by default
            
            // Add OpenStreetMap tiles with a subtle style
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
                maxZoom: 19,
            }).addTo(map);

            // Add scale control
            L.control.scale({imperial: false}).addTo(map);

            // Load and display devices
            const devices = await loadDevices();
            
            if (!devices || devices.length === 0) {
                showError('No radiation monitoring devices found.');
            }
            
            return map;
            
        } catch (error) {
            console.error('Error initializing map:', error);
            showError(`Failed to initialize map: ${error.message}`);
            throw error; // Re-throw to be caught by the caller
        }
    }

    // Load devices from the API
    async function loadDevices() {
        showLoading(true);
        showError('');
        
        try {
            const response = await fetch('/api/devices');
            if (!response.ok) {
                throw new Error(`Failed to load devices: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            const devices = data.devices || [];
            
            if (devices.length === 0) {
                showError('No devices found. The database might be empty.');
                console.log('No devices found');
                return [];
            }
            
            // Add markers for each device
            devices.forEach(device => {
                if (!device.latitude || !device.longitude) return;

                const popupContent = `
                    <div class="device-popup">
                        <h5>${device.device_class || 'Device'} ${device.device_id || ''}</h5>
                        ${device.location ? `<p class="mb-1"><strong>Location:</strong> ${device.location}</p>` : ''}
                        ${device.last_seen ? `<p class="mb-1"><strong>Last seen:</strong> ${formatDate(device.last_seen)}</p>` : ''}
                        <button class="btn btn-sm btn-primary w-100 mt-2" 
                                onclick="loadDeviceHistory('${device.device_urn}', '${device.device_id}')">
                            Show History
                        </button>
                    </div>
                `;

                const marker = L.marker(
                    [device.latitude, device.longitude],
                    { icon: createRadiationIcon() }
                )
                .addTo(map)
                .bindPopup(popupContent);

                marker.deviceUrn = device.device_urn;
                marker.deviceId = device.device_id;
            });
            
            // Fit map to show all markers
            const markers = devices
                .filter(d => d.latitude && d.longitude)
                .map(d => L.latLng(d.latitude, d.longitude));
            
            if (markers.length > 0) {
                const group = new L.featureGroup(markers);
                map.fitBounds(group.getBounds().pad(0.1));
            }
            
            return devices;
            
        } catch (error) {
            console.error('Error loading devices:', error);
            showError(`Error loading devices: ${error.message}`);
            throw error; // Re-throw to be caught by the caller
        } finally {
            showLoading(false);
        }
    }

    // Load historical data for a device
    async function loadDeviceHistory(deviceUrn, deviceId) {
        showLoading(true);
        showError('');
        
        try {
            const response = await fetch(`/api/measurements/${encodeURIComponent(deviceUrn)}?days=7`);
            if (!response.ok) {
                throw new Error(`Failed to load data: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (!data.measurements || data.measurements.length === 0) {
                updateChart([], [], `No data available for device ${deviceId}`, 'CPM');
                showError(`No measurement data available for this device.`);
                return;
            }

            // Prepare chart data
            const timestamps = data.measurements.map(m => new Date(m.when_captured));
            const values = data.measurements.map(m => m.lnd_7318u);
            
            // Calculate average CPM for the popup
            const avgCpm = (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2);
            const maxCpm = Math.max(...values).toFixed(2);
            
            // Update chart with new data
            updateChart(
                timestamps, 
                values, 
                `Radiation (CPM) - Device ${deviceId}`,
                'CPM (Counts per Minute)'
            );
            
            // Update the popup with the loaded data
            const popupContent = `
                <div class="device-popup">
                    <h5>${deviceId || 'Device'} - ${deviceUrn.split(':').pop()}</h5>
                    <p class="mb-1"><strong>Average CPM:</strong> ${avgCpm}</p>
                    <p class="mb-1"><strong>Max CPM:</strong> ${maxCpm}</p>
                    <p class="mb-1"><strong>Last updated:</strong> ${formatDate(new Date().toISOString())}</p>
                    <button class="btn btn-sm btn-primary w-100 mt-2" 
                            onclick="loadDeviceHistory('${deviceUrn}', '${deviceId}')">
                        Refresh Data
                    </button>
                </div>
            `;
            
            // Find and update the marker's popup
            map.eachLayer(layer => {
                if (layer instanceof L.Marker && layer.deviceUrn === deviceUrn) {
                    layer.setPopupContent(popupContent);
                }
            });
            
        } catch (error) {
            console.error('Error loading device history:', error);
            showError(`Failed to load device history: ${error.message}`);
            
            // Update the popup to show the error
            const popupContent = `
                <div class="device-popup">
                    <h5>${deviceId || 'Device'} - ${deviceUrn.split(':').pop()}</h5>
                    <div class="alert alert-danger p-2 mt-2 mb-2">
                        <small>Error loading data: ${error.message}</small>
                    </div>
                    <button class="btn btn-sm btn-primary w-100" 
                            onclick="loadDeviceHistory('${deviceUrn}', '${deviceId}')">
                        Retry
                    </button>
                </div>
            `;
            
            // Find and update the marker's popup
            map.eachLayer(layer => {
                if (layer instanceof L.Marker && layer.deviceUrn === deviceUrn) {
                    layer.setPopupContent(popupContent);
                }
            });
            
        } finally {
            showLoading(false);
        }
    }
    
    // Update or create the chart
    function updateChart(labels, data, title, yAxisLabel = 'CPM') {
        const ctx = document.getElementById('chart').getContext('2d');
        
        if (chart) {
            chart.destroy();
        }
        
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: title,
                    data: data,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    borderWidth: 2,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    fill: true,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: title,
                        font: {
                            size: 16
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function(context) {
                                return `${yAxisLabel}: ${context.parsed.y ? context.parsed.y.toFixed(2) : 'N/A'}`;
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
                                hour: 'MMM d HH:mm',
                                day: 'MMM d',
                                week: 'MMM d',
                                month: 'MMM yyyy'
                            }
                        },
                        title: {
                            display: true,
                            text: 'Date/Time'
                        },
                        grid: {
                            display: false
                        }
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: yAxisLabel
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index'
                }
            }
        });
    }
    
    // Show loading state
    function showLoading(show) {
        const loadingEl = document.getElementById('loading');
        if (loadingEl) {
            loadingEl.style.display = show ? 'flex' : 'none';
        }
    }

    // Show error message
    function showError(message) {
        const errorEl = document.getElementById('error-message');
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.style.display = message ? 'block' : 'none';
        }
    }

    // Update last updated time
    function updateLastUpdated() {
        const now = new Date();
        const options = { 
            year: 'numeric', 
            month: 'short', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        };
        const lastUpdatedEl = document.getElementById('last-updated');
        if (lastUpdatedEl) {
            lastUpdatedEl.textContent = now.toLocaleDateString('en-US', options);
        }
    }

    // Initialize the application
    async function initApp() {
        showLoading(true);
        showError('');
        
        try {
            await initMap();
            updateLastUpdated();
        } catch (error) {
            console.error('Error initializing app:', error);
            showError(`Failed to initialize application: ${error.message}`);
        } finally {
            showLoading(false);
        }
    }

    // Make functions available globally for HTML onclick handlers
    window.loadDeviceHistory = loadDeviceHistory;
    
    // Initialize the application when the page loads
    document.addEventListener('DOMContentLoaded', initApp);
    