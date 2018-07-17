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
from bluepy.btle import Scanner, DefaultDelegate
import bluetooth


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


class BLEScanDelegate(DefaultDelegate):
    """BLE scan."""

    def __init__(self):
        """Initialize."""
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        """Post mqtt message on discovery."""
        return
        # if isNewDev:
        #     # print("Discovered device", dev.addr, dev.rssi)
        #     pass


def on_connect(mqttc, userdata, flag, rc):
    """Implement callback on mqtt connect."""
    print("Connected with result code [%i]" % (rc))
    if rc != 0:
        mqttc.reconnect()
    mqttc.connected_flag = True


def on_publish(mqttc, userdata, mid):
    """Implement callback for mqtt publish."""
    # print("Published")
    pass


def on_disconnect(mqttc, userdata, rc):
    """Implement callback for mqtt disconnect."""
    mqttc.connected_flag = False
    if rc != 0:
        print("Unexpected disconnection. Reconnecting... [%i]" % (rc))
    else:
        print("Disconnected successfully")


def search_ble(raw, mac):
    """Search for bluetooth low energy mac address."""
    return mac in [o.addr for o in raw]


def json_default(value):
    """Return json timestamp format."""
    if isinstance(value, date):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
    return value.__dict__


class Tracker:
    """Bluetooth tracker."""

    def __init__(self, args, conf):
        """Initialize BLE tracker."""
        self.args = args
        self.conf = conf
        self.ble = False
        self.watched = {}
        self.mqtt_client = None
        self.scanner = Scanner().withDelegate(BLEScanDelegate())

        self.ble_timeout = 10
        self.bt_timeout = 6
        self.scan_interval = 20

        self.quit = False

        self.room = self.conf["room"]
        if self.room is None:
            self.room = "room"

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
        """Exit the presence scanner gracefully."""
        self.quit = True

    def search_bt(self, mac):
        """Search for bluetooth mac address."""
        name = bluetooth.lookup_name(mac, self.bt_timeout)
        if name:
            return True
        return False

    def post_mqtt(self, current):
        """Post mqtt message."""
        self.mqtt_client.publish("location/owner/%s/%s" % (self.room,
                                                           current.mac),
                                 json.dumps(current, ensure_ascii=False,
                                            default=json_default).encode(
                                                'utf-8'))

    def run(self):
        """Run."""
        self.init_watch()
        self.init_mqtt()
        self.init_timeouts()

        while self.quit is False:
            t_start = time.time()
            if self.ble:
                ble_raw = self.scanner.scan(self.ble_timeout)

            if not self.mqtt_client.connected_flag:
                try:
                    self.mqtt_client.loop_stop()
                    self.mqtt_client.reconnect()
                    self.mqtt_client.loop_start()
                except:
                    print("Trying to reconnect to mqtt broker ...")
                    time.sleep(10)
                    continue

            for key in sorted(self.watched,
                              key=lambda x: self.watched[x].bt_type):
                if self.quit:
                    break

                print("Searching for %s [%s]" % (self.watched[key].name,
                                                 self.watched[key].mac))

                found = False
                if self.watched[key].bt_type == "ble":
                    if search_ble(ble_raw, self.watched[key].mac):
                        self.watched[key].confidence = 100
                        self.watched[key].lastseen = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S")
                        found = True

                if self.watched[key].bt_type == "bt":
                    if self.search_bt(self.watched[key].mac):
                        self.watched[key].confidence = 100
                        self.watched[key].lastseen = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S")
                        found = True

                if not found:
                    self.watched[key].decrease_confidence()

                self.post_mqtt(self.watched[key])

            if self.quit:
                break

            # calculate time left until next scan
            t_end = time.time()
            pause = self.scan_interval-(t_end - t_start)
            if pause > 0:
                print("Waiting %i" % (pause))
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
