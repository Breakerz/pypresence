# -*- coding: utf-8 -*-
import paho.mqtt.client as mqtt
import subprocess
import json
import yaml
import time
import re
import datetime
from collections import OrderedDict

watched = {}

class Watchedmac:

    # def __init__(self, mac):
    #     """Constructeur de notre classe"""
    #     self.mac = mac
    #     self.lastseen = datetime.min
    #     self.confidence = 0
    #     self.is_ble = 0

    # def __init__(self, mac, is_ble):
    #     """Constructeur de notre classe"""
    #     self.mac = mac
    #     self.lastseen = datetime.min
    #     self.confidence = 0
    #    self.is_ble = is_ble

    def __init__(self, name, mac, lastseen, confidence, is_ble):
        """Constructeur de notre classe"""
        self.name = name
        self.mac = mac
        self.lastseen = lastseen
        self.confidence = confidence
        self.is_ble = is_ble
    
    def decrease_confidence(self):
        if(self.confidence != 0):
            self.confidence = self.confidence - 5


#https://gist.github.com/ghostbitmeta/694934062c0814680d52

# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flag, rc):
	print("Connected with result code %s" % (str(rc)))
    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
	client.subscribe("presence/#")


def on_message(client, userdata, msg):
    print("Topic: ", msg.topic+'\nMessage: '+str(msg.payload, encoding='ascii'))
    {
        "presence/get/exemple1": get_exemple1,
        "presence/set/exemple2": set_exemple2,		
    }.get(str(msg.topic), wrong_topic)(client, msg)


def get_exemple1(client, msg):
	print("get_exemple1")
	client.publish("presence/roomx/34234234", str(msg.payload, encoding='ascii'))	



def set_exemple2(client, msg):
	print("set_exemple2")
	client.publish("presence/roomx/34234234", str(msg.payload, encoding='ascii'))	


def wrong_topic(client, msg):
	print(str(msg.topic))


def scan_ble():
    beacons_raw = ''
    try:
        subprocess.call(['sudo','hciconfig','hci0','down'])
        time.sleep(1)
        subprocess.call(['sudo','hciconfig','hci0','up'])
        time.sleep(1)
        beacons_raw = subprocess.check_output(['sudo', 'timeout', '--signal','9','7', 'hcitool','lescan','--duplicate'])
    except subprocess.CalledProcessError as e:
        if (e.returncode == -9):
            return str(e.output)                                                                                                  
        return ("error code", e.returncode, e.output)
    return str(beacons_raw)
    # https://stackoverflow.com/questions/6341451/piping-together-several-subprocesses''

    #sudo timeout --signal SIGINT $beacon_scan_interval hcitool lescan --duplicates 2>&1


    #local result=$(timeout --signal SIGINT $name_scan_timeout hcitool -i hci0 name "$1" 2>&1 | grep -v 'not available' | grep -vE "hcitool|timeout|invalid|error" )

def get_scan_ble():
    raw = scan_ble()
    p = re.compile(r"(?:[0-9a-fA-F]:?){12}")
    cleanup = OrderedDict((x, True) for x in re.findall(p, raw)).keys()
    for a in cleanup:
        print(a)
    return cleanup

def search_ble(mac):
    scan_result = get_scan_ble()
    return ( mac in scan_result)

def scan_bt(mac):
    beacons_raw = ''
    try:
        subprocess.call(['sudo','hciconfig','hci0','down'])
        time.sleep(1)
        subprocess.call(['sudo','hciconfig','hci0','up'])
        time.sleep(1)
        beacons_raw = subprocess.check_output(['sudo', 'timeout', '--signal','9','7', 'hcitool','-i','hci0','name', mac])
    except subprocess.CalledProcessError as e:
        if (e.returncode == -9):
            return str(beacons_raw)
        return 'error'   
    return str(beacons_raw)

def search_bt(mac):
    beacons_raw = scan_bt(mac)
    print("result scan_bt {0}".format(beacons_raw))
    if("error" in beacons_raw):
        return False
    if("not available" in beacons_raw):
        return False
    if("timeout" in beacons_raw):
        return False
    if("invalid" in beacons_raw):
        return False
    if("hcitool" in beacons_raw):
        return False		
	if not beacons_raw:
		return False
    return True    


def json_default(value):
    if isinstance(value, datetime.date ):
        return str(value.strftime("%Y-%m-%d %H:%M:%S"))
        #return dict(year=value.year, month=value.month, day=value.day)
    else:
        return value.__dict__

def post_mqtt(client, current):
    print("post_mqtt")
    global room
    client.publish("presence/{0}/{1}".format(room, current.name ) , json.dumps(current, ensure_ascii=False, default=json_default).encode('utf-8'))  #str(json.dumps(current, default=lambda o: o.__dict__)), encoding='ascii')	

def init_watch():
    global watched
    global conf
    watched = {} #reset dictionnary
   # watched['EF:7C:D4:AE:ED:1F'] =  Watchedmac('EF:7C:D4:AE:ED:1F', 0, 0 ,0)
    print(conf)
    for mac in conf["macs"]:
        print(mac)
        watched[mac["name"]] =  Watchedmac(name=mac["name"], mac= mac["mac"], is_ble = mac["is_ble"], confidence = 0, lastseen = "")# datetime.date.min)

conf = yaml.load(open('./presence.yaml'))

room = conf["room"]
if(room is None) :
    room = "default"

init_watch()
for a in watched:
    print(watched[a].mac)



client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(conf["mqtt_host"], conf["mqtt_port"], 60)

while (True) :
    for key in watched:
        print("looping")
        print(watched[key])
        found = False
        if (watched[key].is_ble != 2):
            if (search_ble(watched[key].mac)):
                watched[key].is_ble = 1
                watched[key].confidence = 100
                watched[key].lastseen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                found = True

        if (watched[key].is_ble != 1):
            if (search_bt(watched[key].mac)):
                watched[key].is_ble = 2
                watched[key].confidence = 100
                watched[key].lastseen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                found = True
        
        if (found == False):
            watched[key].decrease_confidence()
        
        post_mqtt(client, watched[key])
        time.sleep( 5 )

