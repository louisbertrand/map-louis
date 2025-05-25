# Radiation Map Project

A web application that visualizes radiation data from Safecast devices on an interactive map. This project fetches real-time radiation measurements and displays them using a heatmap overlay.

## Features

- Real-time radiation data visualization
- Interactive map with zoom and pan capabilities
- Historical data tracking
- Multiple device support
- Responsive design for desktop and mobile

## Prerequisites
- Up-to-date FreeBSD installation (current is `14.2-RELEASE`)
- nginx web and reverse proxy server
- `curl` minimal web client for testing
- `certbot` utility to install TLS certificates from Let's Encrypt
- Ability to escalate user privileges to execute commands as root with `doas` (preferred) or `sudo`

## Installation on a FreeBSD (14.x or later) server with nginx
This procedure assumes that `nginx` is installed normally. The virtual host directories are
under `/usr/local/www` and the configuration files are under `/usr/local/etc/nginx`.
The virtual host configurations are under `/usr/local/etc/nginx/sites-available`
and they are activated by making a symbolic link to each active site in directory
`/usr/local/etc/nginx/sites-enabled`.

## Obtain and install a TLS (SSL) certificate for the site
Follow the EFF.org [`certbot`](https://certbot.eff.org/) instructions to 
obtain a free TLS certificatefrom [Let's Encrypt](https://letsencrypt.org/).

Copy the location of the certificate files into the server configuration file `rt-ca.safecast.org` in `/usr/local/etc/nginx/sites-available`.
Remember to renew the certificate before it expires.

## Bootstrap the configuration script
The initial configuration script `install-freebsd.sh` in the Git repository provides commands that should do most of the installation. To bootstrap the installation, download the script from GitHub.com or copy it from a separate checkout of the repository. You may copy it to any temporary directory like `/tmp` or the user's own home directory.

Edit the script before execution to change the user name from *user* to the user name who will own the application directory.

Execute the script as the unprivileged user. The commands that require privilege escalation are prefixed with `doas`.

## Configuration script by section
The script is described in the following sections.

1. This executes the pre-requisite package system commands and creates the application's directory in the web server's directory tree. Obviously, we need Git and Python. The Supervisor subsystem will launch and monitor the application. Less obviously, the `rust` compiler is used by the Python installation program (`pip`) to build some packages (a.k.a. wheels) from source.
   ```
   doas pkg install git
   doas pkg install rust
   doas pkg install python311
   doas pkg install py311-supervisor
   doas mkdir -p /usr/local/www/rt-ca.safecast.org
   doas chown user:user /usr/local/www/rt-ca.safecast.org
   ```

2. Copy the nginx server configuration to the `sites-available` and make a symbolic link in `sites-enabled`, then restart `nginx`. Check for errors displayed on the terminal.
   ```
   # Configure virtual host on nginx
   doas cp nginx-conf-rt-ca.safecast.org /usr/local/etc/nginx/sites-available/rt-ca.safecast.org
   doas ln -s /usr/local/etc/nginx/sites-available/rt-ca.safecast.org /usr/local/etc/nginx/sites-enabled/rt-ca.safecast.org
   doas service nginx restart
   ```

3. Clone the git repo into the target directory. Do this as a regular user, the owner of the application directory.
   ```
   cd /usr/local/www/rt-ca.safecast.org
   git clone git@github.com:louisbertrand/map-louis.git
   cd map-louis/radiation-map
   mkdir logs
   ```

4. As the user who owns the application directory, create a Python virtual environment. The name is chosen deliberately to show that the application is running in a special-purpose environment. The `.` dot is the `/bin/sh` source directive (same as `source` in `bash`).
   ```
   cd map-louis/radiation-map
   python3 -m venv venv-map
   . ./venv-map/bin/activate
   ```

5. Install the required Python modules from the list provided in `requirements.txt`. This may take a long time.
   ```
   python3 -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Testing the application
The first stage of testing is to make sure that the application itself
is responding to requests. Those requests will eventually be passed through
the nginx server.

### Test the application alone
1. Launch `supervisord` as service
   ```
   $ doas service supervisor onestart
   ```
Check for error messages to the console. Also check
`/var/log/supervisord.log` for error messages.

3. Using `curl`, read the response from the application (option `-v` shows the headers as well as the response.
   ```
   $ curl -v http://127.0.0.1:8000/map
   ```
Check under the `logs` directory in `stdout.err` and `stderr.log` for information messages.

### Test the application alone
Test that `nginx` is correctly responding to requests to the published end-points.

1. Quick test with curl:
   ```
   $ curl -v https://rt-ca.safecast.org/map
   ```
   
2. Test with a full-feature browser. At this point you should see the map with markers for each sensor. Clicking on a sensor should bring up the history and a link to more information about that sensor.

At first, the history will be short. As the application continues to run, the database will accumulate readings. Typically, the sensors only report once every five minutes.


## Project Structure

```
radiation-map/
├── main.py             # Main FastAPI application
├── map_app_start       # Startup script invoked by supervisord
├── requirements.txt    # Python dependencies
├── radiation_data.db   # Local database (does not seem to be used)
├── safecast_data.db    # Cached Safecast data
├── venv-map            # Python virtual environment
├── static/             # Static files (CSS, JS, images)
│   ├── css/
│   └── js/
└── templates/          # HTML templates
    └── index.html
```

## API Endpoints
Note that the top level link `/` is not part of the application. It can be used as an index page to document the application and the monitoring effort in general.
- `GET /map` - Main application interface
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
