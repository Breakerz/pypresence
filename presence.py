#!/home/pi/pypresence/venv/bin/python
"""Presence detection made in python."""
import subprocess
import signal
import time
import re
from datetime import datetime, date
import json
import argparse
from collections import OrderedDict
import paho.mqtt.client as mqtt
import yaml


class WatchedMAC:
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


def on_connect(mqttc, userdata, flag, rc):
    """Implement callback on mqtt connect."""
    print("Connected with result code [%i]" % (rc))
    if rc != 0:
        mqttc.reconnect()
    mqttc.connected_flag = True


def on_publish(mqttc, userdata, mid):
    """Implement callback for mqtt publish."""
    print("Published")


def on_disconnect(mqttc, userdata, rc):
    """Implement callback for mqtt disconnect."""
    if rc != 0:
        print("Unexpected disconnection. Reconnecting... [%i]" % (rc))
        # mqttc.loop_stop()
        mqttc.connected_flag = False
        # mqttc.reconnect()
        # mqttc.loop_start()
    else:
        print("Disconnected successfully")


def scan_ble(timeout):
    """Execute bluetooth low energy scan."""
    beacons_raw = ''
    try:
        subprocess.call(['sudo', 'hciconfig', 'hci0', 'reset'])
        beacons_raw = subprocess.check_output(
            ['sudo', 'timeout', '--signal', '9', str(timeout),
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
    if isinstance(value, date):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
    return value.__dict__


def post_mqtt(client, current, room):
    """Post mqtt message."""
    client.publish("location/owner/%s/%s" % (room, current.mac),
                   json.dumps(current, ensure_ascii=False,
                              default=json_default).encode('utf-8'))


class Tracker:
    """Bluetooth tracker."""

    def __init__(self, args, conf):
        """Initialize BLE tracker."""
        self.args = args
        self.conf = conf
        self.ble = False
        self.watched = {}
        self.mqtt_client = None

        self.ble_timeout = 10
        self.bt_timeout = 6
        self.scan_interval = 20

        self.quit = False

        self.room = self.conf["room"]
        if self.room is None:
            self.room = "default"

        signal.signal(signal.SIGTERM, self.exit_gracefully)
        signal.signal(signal.SIGINT, self.exit_gracefully)

    def init_watch(self):
        """Populate watched mac address list."""
        print(self.conf)
        for mac in self.conf["macs"]:
            self.watched[mac["name"]] = WatchedMAC(name=mac["name"],
                                                   mac=mac["mac"],
                                                   bt_type=mac["bt_type"],
                                                   confidence=0, lastseen="")
            if self.watched[mac["name"]].bt_type == "ble":
                self.ble = True

    def init_mqtt(self):
        """Initialize mqtt client."""
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_publish = on_publish
        self.mqtt_client.on_disconnect = on_disconnect
        self.mqtt_client.username_pw_set(self.conf["mqtt_user"],
                                         self.conf["mqtt_pwd"])
        try:
            self.mqtt_client.connect(self.conf["mqtt_host"],
                                     self.conf["mqtt_port"], 60)
            self.mqtt_client.loop_start()
        except:
            print("Connection to mqtt broker failed.")
            self.quit = True

    def init_timeouts(self):
        """Initialize timeouts."""
        self.ble_timeout = self.conf["ble_timeout"]
        self.bt_timeout = self.conf["bt_timeout"]
        self.scan_interval = self.conf["scan_interval"]

    def exit_gracefully(self, signum, frame):
        self.quit = True

    def run(self):
        """Run."""
        self.init_watch()
        self.init_mqtt()
        self.init_timeouts()

        while (self.quit is False):
            t_bt, t_ble, t_bles = 0, 0, 0
            if self.ble:
                print("Executing BLE scan...")
                t_ble_start = time.time()
                ble_raw = scan_ble(self.ble_timeout)
                t_ble_end = time.time()
                t_ble += t_ble_end - t_ble_start

            if not self.mqtt_client.connected_flag:
                try:
                    self.mqtt_client.loop_stop()
                    self.mqtt_client.reconnect()
                    self.mqtt_client.loop_start()
                except:
                    print("Trying to reconnect to mqtt broker ...")
                    time.sleep(10)
                    continue

            for key in sorted(self.watched, key=lambda x: self.watched[x].bt_type):
                if self.quit: break

                print("Searching for %s [%s]" % (self.watched[key].name,
                                                 self.watched[key].mac))

                found = False
                t_bles_start = time.time()
                if self.watched[key].bt_type == "ble":
                    print("BLE Search")
                    if search_ble(ble_raw, self.watched[key].mac):
                        self.watched[key].confidence = 100
                        self.watched[key].lastseen = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S")
                        found = True
                t_bles_end = time.time()
                t_bles += t_bles_end - t_bles_start

                t_bt_start = time.time()
                if self.watched[key].bt_type == "bt":
                    print("BT Search")
                    if search_bt(self.watched[key].mac):
                        self.watched[key].confidence = 100
                        self.watched[key].lastseen = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S")
                        found = True
                t_bt_end = time.time()
                t_bt += t_bt_end - t_bt_start

                if not found:
                    print("Not found")
                    self.watched[key].decrease_confidence()
                else:
                    print("SUCCESS")

                post_mqtt(self.mqtt_client, self.watched[key], self.room)

            if self.quit: break

            print("Total time: %s (BLE: %s, BT: %s)" % (
                round((t_bt + t_ble + t_bles), 4),
                round((t_ble + t_bles), 4),
                round(t_bt, 4)))

            # calculate time left until next scan
            pause = self.scan_interval-(t_bt + t_ble + t_bles)
            if pause > 0:
                time.sleep(pause)


def main():
    """."""
    args = parseArgs()

    if args.config:
        conf = yaml.load(open(args.config))
    else:
        conf = yaml.load(open('./presence.yaml'))

    tracker = Tracker(args, conf)
    tracker.run()


def parseArgs():
    """."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='Config path')
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    # execute only if run as a script
    main()
