# -*- coding: utf-8 -*-
"""Presence detection made in python."""
import subprocess
import time
import re
import datetime
import json
from collections import OrderedDict
import paho.mqtt.client as mqtt
import yaml

watched = {}


class Watchedmac:
    """Watched bl/ble macs."""

    def __init__(self, name, mac, lastseen, confidence, bt_type):
        """Constructeur de notre classe."""
        self.name = name
        self.mac = mac
        self.lastseen = lastseen
        self.confidence = confidence
        self.bt_type = bt_type

    def decrease_confidence(self):
        """."""
        if self.confidence != 0:
            self.confidence = self.confidence - 5


class Tracker:
    """Bluetooth tracker."""

    def __init__(self):
        """Initialize BLE tracker."""

# https://gist.github.com/ghostbitmeta/694934062c0814680d52

# The callback for when the client receives a CONNACK response from the server.


# def on_connect(client, userdata, flag, rc):
#     """."""
#     print("Connected with result code %s" % (str(rc)))
#     # Subscribing in on_connect() means that if we lose the connection and
#     # reconnect then subscriptions will be renewed.
#     client.subscribe("presence/#")


def on_connect(mqttc, userdata, flag, rc):
    print("Connected with result code "+str(rc))
    if rc != 0:
        mqttc.reconnect()


def on_publish(mqttc, userdata, mid):
    print("Published")


def on_disconnect(mqttc, userdata, rc):
    if rc != 0:
        print("Unexpected disconnection. Reconnecting...")
        mqttc.reconnect()
    else:
        print("Disconnected successfully")


def scan_ble():
    """."""
    beacons_raw = ''
    try:
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'down'])
        time.sleep(1)
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'up'])
        time.sleep(1)
        beacons_raw = subprocess.check_output(
            ['sudo', 'timeout', '--signal', '9', '7',
             'hcitool', 'lescan', '--duplicate'])

    except subprocess.CalledProcessError as e:
        if e.returncode == -9:
            return str(e.output)
        return ("error code", e.returncode, e.output)

    return str(beacons_raw)
    # https://stackoverflow.com/questions/6341451/piping-together-several-subprocesses''

    # sudo timeout --signal SIGINT $beacon_scan_interval hcitool lescan --duplicates 2>&1

    # local result=$(timeout --signal SIGINT $name_scan_timeout hcitool -i hci0 name "$1" 2>&1 | grep -v 'not available' | grep -vE "hcitool|timeout|invalid|error" )


def search_ble(mac):
    """."""
    raw = scan_ble()
    p = re.compile(r"(?:[0-9a-fA-F]:?){12}")
    macs = OrderedDict((x, True) for x in re.findall(p, raw)).keys()
    print(mac in macs, macs)
    return mac in macs


def scan_bt(mac):
    """."""
    beacons_raw = ''
    try:
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'down'])
        time.sleep(1)
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'up'])
        time.sleep(1)
        beacons_raw = subprocess.check_output(
            ['sudo', 'timeout', '--signal', '9', '7',
             'hcitool', '-i', 'hci0', 'name', mac])
    except subprocess.CalledProcessError as e:
        if e.returncode == -9:
            return str(beacons_raw, 'utf-8')
        return 'error'
    return str(beacons_raw, 'utf-8')


def search_bt(mac):
    """."""
    print("search_bt({0})".format(mac))
    beacons_raw = scan_bt(mac)
    print("result scan_bt {0}".format(beacons_raw))
    if "error" in beacons_raw:
        return False
    elif "not available" in beacons_raw:
        return False
    elif "timeout" in beacons_raw:
        return False
    elif "invalid" in beacons_raw:
        return False
    elif "hcitool" in beacons_raw:
        return False
    elif beacons_raw.strip() == b'':
        return False
    elif not (beacons_raw and beacons_raw.strip()):
        return False
    print("bt found {0}".format(beacons_raw))
    return True


def json_default(value):
    """."""
    if isinstance(value, datetime.date):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
        # return dict(year=value.year, month=value.month, day=value.day)
    return value.__dict__


def post_mqtt(client, current):
    """."""
    print("post_mqtt")
    global room
    client.publish("location/owner/{0}/{1}".format(room, current.mac),
                   json.dumps(current, ensure_ascii=False,
                              default=json_default).encode('utf-8'))
    # str(json.dumps(current, default=lambda o: o.__dict__)), encoding='ascii')


def init_watch():
    """."""
    global watched
    global conf
    watched = {}  # reset dictionnary
    # watched['EF:7C:D4:AE:ED:1F'] =  Watchedmac('EF:7C:D4:AE:ED:1F', 0, 0 ,0)
    print(conf)
    for mac in conf["macs"]:
        print(mac)
        watched[mac["name"]] = Watchedmac(name=mac["name"], mac=mac["mac"],
                                          bt_type=mac["bt_type"], confidence=0,
                                          lastseen="")  # datetime.date.min)


conf = yaml.load(open('./presence.yaml'))

room = conf["room"]
if room is None:
    room = "default"

init_watch()
for a in watched:
    print(watched[a].mac)


mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_publish = on_publish
mqtt_client.on_disconnect = on_disconnect
mqtt_client.username_pw_set(conf["mqtt_user"], conf["mqtt_pwd"])
mqtt_client.connect(conf["mqtt_host"], conf["mqtt_port"], 60)
mqtt_client.loop_start()

while True:
    for key in watched:
        print("Searching for {0} with mac {1}".format(watched[key].name,
                                                      watched[key].mac))

        found = False
        if watched[key].bt_type != "bt":
            print("BLE Scan")
            if search_ble(watched[key].mac):
                watched[key].bt_type = "ble"
                watched[key].confidence = 100
                watched[key].lastseen = datetime.datetime.now().strftime(
                                                        "%Y-%m-%d %H:%M:%S")
                found = True

        if watched[key].bt_type != "ble":
            print("BT Scan")
            if search_bt(watched[key].mac):
                watched[key].bt_type = "bt"
                watched[key].confidence = 100
                watched[key].lastseen = datetime.datetime.now().strftime(
                                                        "%Y-%m-%d %H:%M:%S")
                found = True

        if not found:
            print("Not found")
            watched[key].decrease_confidence()

        post_mqtt(mqtt_client, watched[key])
        time.sleep(5)
