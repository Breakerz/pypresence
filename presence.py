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
        """Initialize class variables."""
        self.name = name
        self.mac = mac
        self.lastseen = lastseen
        self.confidence = confidence
        self.bt_type = bt_type

    def decrease_confidence(self):
        """Decrese confidence."""
        if self.confidence != 0:
            self.confidence = self.confidence - 5


class Tracker:
    """Bluetooth tracker."""

    def __init__(self):
        """Initialize BLE tracker."""


def on_connect(mqttc, userdata, flag, rc):
    """Implement callback on mqtt connect."""
    print("Connected with result code "+str(rc))
    if rc != 0:
        mqttc.reconnect()


def on_publish(mqttc, userdata, mid):
    """Implement callback for mqtt publish."""
    print("Published")


def on_disconnect(mqttc, userdata, rc):
    """Implement callback for mqtt disconnect."""
    if rc != 0:
        print("Unexpected disconnection. Reconnecting...")
        mqttc.reconnect()
    else:
        print("Disconnected successfully")


def scan_ble():
    """Execute bluetooth low energy scan."""
    beacons_raw = ''
    t_out = 10
    try:
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'reset'])
        beacons_raw = subprocess.check_output(
            ['sudo', 'timeout', '--signal', '9', str(t_out),
             'hcitool', 'lescan', '--duplicate', '--passive'])
    except subprocess.CalledProcessError as e:
        if e.returncode == -9:
            return str(e.output)
        return ("error code", e.returncode, e.output)
    return str(beacons_raw)


def search_ble(raw, mac):
    """Search for bluetooth low energy mac address."""
    p = re.compile(r"(?:[0-9a-fA-F]:?){12}")
    macs = OrderedDict((x, True) for x in re.findall(p, raw)).keys()
    return mac in macs


def scan_bt(mac):
    """Execute bluetooth scan."""
    beacons_raw = ''
    t_out = 10
    try:
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'reset'])
        beacons_raw = subprocess.check_output(
            ['sudo', 'timeout', '--signal', '9', str(t_out),
             'hcitool', '-i', 'hci0', 'name', mac])
    except subprocess.CalledProcessError as e:
        if e.returncode == -9:
            return str(beacons_raw, 'utf-8')
        return 'error'
    return str(beacons_raw, 'utf-8')


def search_bt(mac):
    """Search for bluetooth mac address."""
    beacons_raw = scan_bt(mac)
    if (("error" in beacons_raw)
            or ("not available" in beacons_raw)
            or ("timeout" in beacons_raw)
            or ("invalid" in beacons_raw)
            or ("hcitool" in beacons_raw)):
        return False
    elif ((beacons_raw.strip() == b'')
          or not (beacons_raw and beacons_raw.strip())):
        return False
    return True


def json_default(value):
    """Return json timestamp format."""
    if isinstance(value, datetime.date):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
    return value.__dict__


def post_mqtt(client, current):
    """Post mqtt message."""
    global room
    client.publish("location/owner/%s/%s" % (room, current.mac),
                   json.dumps(current, ensure_ascii=False,
                              default=json_default).encode('utf-8'))


def init_watch():
    """Populate watched mac address list."""
    global watched
    global conf
    watched = {}

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

ble = False

init_watch()
for a in watched:
    print(watched[a].mac)
    if watched[a].bt_type == "ble":
        ble = True


mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_publish = on_publish
mqtt_client.on_disconnect = on_disconnect
mqtt_client.username_pw_set(conf["mqtt_user"], conf["mqtt_pwd"])
mqtt_client.connect(conf["mqtt_host"], conf["mqtt_port"], 60)
mqtt_client.loop_start()

while True:
    t_bt, t_ble, t_bles = 0, 0, 0
    if ble:
        print("Executing BLE scan...")
        t_ble_start = time.time()
        ble_raw = scan_ble()
        t_ble_end = time.time()
        t_ble += t_ble_end - t_ble_start
        # print('raw', ble_raw)

    for key in watched:
        print("Searching for %s [%s]" % (watched[key].name, watched[key].mac))

        found = False
        t_bles_start = time.time()
        if watched[key].bt_type != "bt":
            print("BLE Search")
            if search_ble(ble_raw, watched[key].mac):
                watched[key].bt_type = "ble"
                watched[key].confidence = 100
                watched[key].lastseen = datetime.datetime.now().strftime(
                                                        "%Y-%m-%d %H:%M:%S")
                found = True
        t_bles_end = time.time()
        t_bles += t_bles_end - t_bles_start

        t_bt_start = time.time()
        if watched[key].bt_type != "ble":
            print("BT Search")
            if search_bt(watched[key].mac):
                watched[key].bt_type = "bt"
                watched[key].confidence = 100
                watched[key].lastseen = datetime.datetime.now().strftime(
                                                        "%Y-%m-%d %H:%M:%S")
                found = True
        t_bt_end = time.time()
        t_bt += t_bt_end - t_bt_start

        if not found:
            print("Not found")
            watched[key].decrease_confidence()
        else:
            print("SUCCESS")

        post_mqtt(mqtt_client, watched[key])

    print("Total time: %s (BLE: %s, BT: %s)" % (
        round((t_bt + t_ble + t_bles), 4),
        round((t_ble + t_bles), 4),
        round(t_bt, 4)))
    # print("BLE Scan: %s" % (round(t_ble, 4)))
    # print("BLE Search: %s" % (round(t_bles, 4)))
    # print("BT Scan: %s" % (round(t_bt, 4)))

    time.sleep(5)
