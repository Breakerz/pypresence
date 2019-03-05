"""Presence detection made in python."""
import subprocess
import signal
import time
import re
from datetime import datetime, date
import json
import argparse
import paho.mqtt.client as mqtt
from ruamel.yaml import YAML
from bluepy.btle import Scanner, DefaultDelegate
import bluetooth


__version__ = '0.1'


class WatchedMAC:
    """Watched bl/ble macs."""

    def __init__(self, name, bt_type, mac='', uuid=''):
        """Initialize class variables."""
        self.name = name
        self.mac = mac.upper()
        self.uuid = uuid
        self.bt_type = bt_type
        self.lastseen = ''
        self.confidence = 0

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
    pass


def on_disconnect(mqttc, userdata, rc):
    """Implement callback for mqtt disconnect."""
    mqttc.connected_flag = False
    if rc != 0:
        print("Unexpected disconnection. Reconnecting... [%i]" % (rc))
    else:
        print("Disconnected successfully")


def normalize_uuid(uuid):
    """Normalize UUID to only contain alphanumeric lower case characters."""
    return ''.join([i for i in uuid if i.isalnum()]).lower()


def search_mac(raw, mac):
    """Search for bluetooth low energy mac address."""
    if mac:
        return mac.lower() in [o.addr for o in raw]


def reverse_uuid(uuid):
    return ''.join([uuid[x:x+2] for x in range(0,len(uuid),2)][::-1])


def search_uuid(raw, uuid):
    """Search for bluetooth low energy uuid."""
    if uuid:
        for o in raw:
            sdid = 7
            if sdid in o.scanData.keys():
                if uuid == reverse_uuid(o.getValueText(sdid)):
                    return True


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

        self.room = self.conf['room']
        if self.room is None:
            self.room = 'room'

        signal.signal(signal.SIGTERM, self.exit_gracefully)
        signal.signal(signal.SIGINT, self.exit_gracefully)

    def init_watch(self):
        """Populate watched mac address list."""
        print(self.conf)
        for mac in self.conf['macs']:
            self.watched[mac['name']] = WatchedMAC(name=mac['name'],
                                                   bt_type=mac['bt_type'])
            if 'mac' in mac.keys():
                self.watched[mac['name']].mac = mac['mac']
            if 'uuid' in mac.keys():
                self.watched[mac['name']].uuid = mac['uuid']
            if self.watched[mac['name']].bt_type == 'ble':
                self.ble = True

    def init_mqtt(self):
        """Initialize mqtt client."""
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = on_connect
        self.mqtt_client.on_publish = on_publish
        self.mqtt_client.on_disconnect = on_disconnect
        self.mqtt_client.username_pw_set(self.conf['mqtt_user'],
                                         self.conf['mqtt_pwd'])
        try:
            self.mqtt_client.connect(self.conf['mqtt_host'],
                                     self.conf['mqtt_port'], 60)
            self.mqtt_client.loop_start()
        except:
            print("Connection to mqtt broker failed.")
            self.quit = True

    def init_timeouts(self):
        """Initialize timeouts."""
        self.ble_timeout = self.conf['ble_timeout']
        self.bt_timeout = self.conf['bt_timeout']
        self.scan_interval = self.conf['scan_interval']

    def exit_gracefully(self, signum, frame):
        """Exit the presence scanner gracefully."""
        self.quit = True

    def search_bt(self, mac):
        """Search for bluetooth mac address."""
        name = bluetooth.lookup_name(mac, self.bt_timeout)
        if name:
            return True
        return False

    def home_away(self, current):
        """Evaluate presence state."""
        if current.confidence > 0:
            return "home"
        return "not_home"

    def post_mqtt(self, current):
        """Post mqtt message."""
        self.mqtt_client.publish("location/owner/%s/%s" % (self.room,
                                                           current.mac.upper()),
                                 json.dumps(current, ensure_ascii=False,
                                            default=json_default).encode(
                                                'utf-8'))

        self.mqtt_client.publish("location/%s" % (current.name),
                                 self.home_away(current).encode('utf-8'))

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

                print("Searching for %s [%s] [%s]" % (self.watched[key].name,
                                                      self.watched[key].mac,
                                                      self.watched[key].uuid))

                found = False
                if self.watched[key].bt_type == "ble":
                    if (search_mac(ble_raw, self.watched[key].mac) or
                            search_uuid(ble_raw, self.watched[key].uuid)):
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
                else:
                    print("%s found" % (self.watched[key].name))

                self.post_mqtt(self.watched[key])


            if self.quit:
                break

            # calculate time left until next scan
            t_end = time.time()
            pause = self.scan_interval-(t_end - t_start)
            if pause > 0:
                print("Waiting %i seconds ..." % (pause))
                time.sleep(pause)


def main():
    """Main function."""
    args = parseArgs()

    yaml=YAML(typ='safe')

    if args.config:
        conf = yaml.load(open(args.config))
    else:
        conf = yaml.load(open('./presence.yaml'))

    tracker = Tracker(args, conf)
    tracker.run()


def parseArgs():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='Config path')
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    # execute only if run as a script
    try:
        main()
    except KeyboardInterrupt:
        print('keyboard interrupt')
    finally:
        print('exiting')
