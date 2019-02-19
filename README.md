# pypresence
Bluetooth Presence detection

## Install requirements
sudo apt-get install bluetooth libbluetooth-dev

## Install pypresence
### Clone repo
git clone git@github.com:cgtobi/pypresence.git

### Create virtual environment
cd pypresence
python3 -m venv venv

### Install requirements
pip install -r requirements.txt

## Configuration
See presence.yaml.example

## Running pypresence as a service
See pypresence@pi.service
