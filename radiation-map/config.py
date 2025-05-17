# Configuration settings for the Radiation Map application

# Data retention settings
MAX_DATA_DAYS = 30  # Maximum number of days to keep in the database and display in charts

# External website links
# You can use the placeholder {device_urn} which will be replaced with the actual device URN
EXTERNAL_HISTORY_URL = "https://dashboard.radnote.org/d/cdq671mxg2cjka/radnote-overview?var-device=dev:{device_urn}"

# Default center coordinates for the map
DEFAULT_MAP_CENTER = [43.9, -79.0]
DEFAULT_MAP_ZOOM = 10

# Refresh intervals
AUTO_REFRESH_INTERVAL_SECONDS = 300  # 5 minutes 