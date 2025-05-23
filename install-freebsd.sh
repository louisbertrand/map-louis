#!/usr/bin/env sh
# Script to deploy the application on a new FreeBSD server with nginx as reverse proxy

# Use doas (do-as, get it?) for root privileges


doas pkg install git
doas pkg install python311
doas pkg install py311-supervisor
doas mkdir -p /usr/local/www/rt-ca.safecast.org
doas chown user:user /usr/local/www/rt-ca.safecast.org

# Configure virtual host on nginx
doas cp nginx-conf-rt-ca.safecast.org /usr/local/etc/nginx/sites-available/rt-ca.safecast.org
doas ln -s /usr/local/etc/nginx/sites-available/rt-ca.safecast.org /usr/local/etc/nginx/sites-enabled/rt-ca.safecast.org
doas service nginx restart

# Clone the git repo into the target directory
# Do this as a regular user
cd /usr/local/www/rt-ca.safecast.org
git clone git@github.com:louisbertrand/map-louis.git
cd map-louis/radiation-map

# Make a Python virtual environment for the application and activate it
python3 -m venv venv-map
. ./venv-map/bin/activate

# Install the required Python modules
python3 -m pip install --upgrade pip
pip install -r requirements.txt



