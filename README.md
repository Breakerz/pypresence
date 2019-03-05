# pypresence
A Bluetooth presence detection written in python.

## Install requirements
```bash
$ sudo apt-get install bluetooth libbluetooth-dev
```

## Install pypresence
### Clone repo
```bash
git clone git@github.com:cgtobi/pypresence.git
```

### Create virtual environment
```bash
cd pypresence
python3 -m venv venv
```

### Install requirements
```bash
pip install -r requirements.txt
```

## Configuration
Make a copy of `presence.yaml.example` and edit according to your environment.

### MQTT
```yaml
mqtt_host: 192.168.0.123
mqtt_port: 1883
mqtt_user: usermqtt
mqtt_pwd: 123
```

#### iPhone/iOS device
```yaml
- name : iphone
  mac: '40:9F:AF:79:9F:D2'
  bt_type : bt
```
#### Chipolo Key Tag
```yaml
- name: KeyTag
  mac: 'EF:7F:DF:AF:ED:1F'
  bt_type : ble
```

#### Withings/Nokia Smartwatch
```yaml
- name : Withings Watch
  uuid: '00000012345671234556000000000000'
  bt_type : ble
```


## Running pypresence as a service
Copy `pypresence@pi.service` to `/etc/systemd/system/pypresence@pi.service`.

Enable the service and check its state.
```bash
sudo systemctl daemon-reload
  265  sudo systemctl enable pypresence@pi.service --now
  266  sudo systemctl status pypresence@pi.service
```

Check the service logs:
```bash
sudo journalctl -f -u pypresence@pi.service
```
