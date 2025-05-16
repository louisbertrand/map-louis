# Radiation Map Project

A web application that visualizes radiation data from Safecast devices on an interactive map. This project fetches real-time radiation measurements and displays them using a heatmap overlay.

## Features

- Real-time radiation data visualization
- Interactive map with zoom and pan capabilities
- Historical data tracking
- Multiple device support
- Responsive design for desktop and mobile

## Prerequisites

- Python 3.8+
- pip (Python package manager)
- Git (for version control)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/radiation-map.git
   cd radiation-map
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the project root with the following variables (if needed):

```env
# Database configuration
DATABASE_URL=duckdb:///radiation_data.db

# Safecast API settings
SAFECAST_API_BASE=https://tt.safecast.org
```

## Running the Application

1. Start the FastAPI development server:
   ```bash
   uvicorn main:app --reload
   ```

2. Open your web browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```

## Project Structure

```
radiation-map/
├── main.py              # Main FastAPI application
├── requirements.txt     # Python dependencies
├── radiation_data.db    # Local database (created on first run)
├── safecast_data.db    # Cached Safecast data
├── static/             # Static files (CSS, JS, images)
│   ├── css/
│   └── js/
└── templates/          # HTML templates
    └── index.html
```

## API Endpoints

- `GET /` - Main application interface
- `GET /api/devices` - List all available devices
- `GET /api/measurements?device_urn={urn}&days={days}` - Get measurements for a device
- `POST /api/fetch-data` - Trigger data fetch from Safecast API

## Data Sources

This application uses data from the [Safecast API](https://safecast.org/).

## Contributing

1. Fork the repository
2. Create a new branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -am 'Add some feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Create a new Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Safecast](https://safecast.org/) for providing the radiation data
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [Leaflet](https://leafletjs.com/) for the interactive maps
