from time import sleep
import datetime
import os
from tracadelas_deteccao import funcao_deteccao_lycra_tracadelas
from detecao_agulha_v02 import funcao_detecao_agulhas
import RPi.GPIO as GPIO
from scipy import misc
from pijuice import PiJuice
from pyueye import ueye
import ctypes
import sys, getopt
from control_usb import powerOffUSBs, powerOnUSBs
import logging
import json
import boto
from boto.s3.key import Key
import uuid
import requests
from PIL import Image
from socketIO_client_nexus import SocketIO, LoggingNamespace, BaseNamespace, ConnectionError
import sys
reload(sys)
sys.setdefaultencoding('utf-8')
from random import randint

try:
    import thread
except ImportError:
    import _thread as thread
import time
from threading import Thread

class Smartex:
    OP_OK = 0
    OP_ERR = -1
    # CAMERA_RETRYS = 10
    pijuice = PiJuice(1, 0x14)

    def __init__(self, configsFile='configs.json'):
        print "Starting..."
        self.configsFile = configsFile
        global operationConfigs 
	operationConfigs = json.loads(open(configsFile).read())
        print "Configurations loaded from " + configsFile
        while self.initCamera() != self.OP_OK and operationConfigs['CAMERA_RETRYS'] > 0:
            logging.warning('Error in initCamera()')
            self.pijuice.status.SetLedBlink('D2', 2, [255, 0, 0], 50, [255, 0, 0], 50)
            sleep(1)
            self.pijuice.status.SetLedState('D2', [0, 0, 0])
            operationConfigs['CAMERA_RETRYS'] -= 1

        self.DEVICE_ID = id
        print "Setting up logging configs..."
       # logging.getLogger('socketIO-client-nexus').setLevel(logging.DEBUG)
        logging.basicConfig(filename='smartex_main.log', level=logging.INFO, \
                            format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger().addHandler(logging.StreamHandler())
        print "Smartex module initiated with success!"

    def updateJsonFile(self):

        jsonFile = open(self.configsFile, "w+")
        jsonFile.write(json.dumps(operationConfigs))
        jsonFile.close()

    def initCamera(self):
        try:
            self.hcam = ueye.HIDS(0)
            self.pccmem = ueye.c_mem_p()
            self.memID = ueye.c_int()
            self.hWnd = ctypes.c_voidp()
            ueye.is_InitCamera(self.hcam, self.hWnd)
            ueye.is_SetDisplayMode(self.hcam, 0)
            self.sensorinfo = ueye.SENSORINFO()
            ueye.is_GetSensorInfo(self.hcam, self.sensorinfo)

            return self.OP_OK
        except:
	    print "\n\nERR\n\n"
            return self.OP_ERR

    def connectAWSS3(self):
	global operationConfigs
        print "Connecting AWS3..."
	try:
            con = boto.connect_s3(operationConfigs['AWS_ACCESS_KEY'], operationConfigs['AWS_SECRET_KEY'], host=operationConfigs['REGION_HOST'])
            self.bucket = con.get_bucket(operationConfigs['AWS_BUCKET'])
        except:
            logging.warning('Error in connectAWSS3!\n')
            self.blinkLED()

    def authWS(self):
	global operationConfigs
        try:
            time1 = datetime.datetime.now()
            logging.info("Authenticating in WS!")
            self.client = requests.session()

            # Retrieve the CSRF token first
            self.client.get('http://192.168.1.107:3000/login')  # sets cookie

            if 'csrftoken' in self.client.cookies:
                self.csrftoken = self.client.cookies['csrftoken']
            elif '_csrf' in self.client.cookies:
                self.csrftoken = self.client.cookies['_csrf']
            elif 'sessionId' in self.client.cookies:
                self.csrftoken = self.client.cookies['sessionId']
            else:
                self.csrftoken = self.client.cookies['csrf']

            login_data = dict(username='admin', password='admin1234', csrfmiddlewaretoken=self.csrftoken, next='/')
            r = self.client.post(operationConfigs['AUTH_ENDPOINT'], data=login_data, headers=dict(Referer='http://192.168.1.107:3000/login'))

            time2 = datetime.datetime.now()
            elapsed_time = time2 - time1
            logging.info("\nAuthentication status code: {}".format(r.status_code))
            #logging.info("Authentication response headers: {}".format(r.headers))
            #logging.info("Authentication response cookies: {}\n".format(r.cookies))
            logging.info("Authenticated in WS!! Elapsed time (ms): {}\n".format(elapsed_time.microseconds / 1000))
            self.blinkLED()
        except:
            logging.warning('Error authenticating with WS\n')
            self.blinkLED()
            pass
        pass

    def saveImage(self):
	global operationConfigs
        try:
            time1 = datetime.datetime.now()
            ueye.is_AllocImageMem(self.hcam, self.sensorinfo.nMaxWidth, self.sensorinfo.nMaxHeight, 24, self.pccmem,
                                  self.memID)
            ueye.is_SetImageMem(self.hcam, self.pccmem, self.memID)
            ueye.is_SetDisplayPos(self.hcam, 100, 100)

            self.nret = ueye.is_FreezeVideo(self.hcam, ueye.IS_WAIT)
            self.rawImageTimeStamp = datetime.datetime.now()
            self.imageTimeStamp = datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            self.imageName = 'imagem_%s.jpg' % self.imageTimeStamp
            self.imagePath = operationConfigs['savingDirectory'] + self.imageName

            self.FileParams = ueye.IMAGE_FILE_PARAMS()
            self.FileParams.pwchFileName = self.imagePath
            self.FileParams.nFileType = ueye.IS_IMG_BMP
            self.FileParams.ppcImageMem = None
            self.FileParams.pnImageID = None

            self.nret = ueye.is_ImageFile(self.hcam, ueye.IS_IMAGE_FILE_CMD_SAVE, self.FileParams,
                                          ueye.sizeof(self.FileParams))
            ueye.is_FreeImageMem(self.hcam, self.pccmem, self.memID)
            sleep(.01)
            ueye.is_ExitCamera(self.hcam)

            time2 = datetime.datetime.now()
            elapsed_time = time2 - time1
            logging.info('Saved: {}! Elasped time (ms): {}'.format(self.imageName, elapsed_time.microseconds / 1000))
            self.blinkLED()
        except:
            logging.warning('NOT SAVED: {}!\n'.format(self.imageName))
            self.blinkLED()
            pass

    def percent_cb(self, complete, total):
    	sys.stdout.write('.')
    	sys.stdout.flush()

    def uploadImages(self):
	global operationConfigs
        logging.info("#upload full res: " + self.imagePath)
        fuuid = str(uuid.uuid4())
        k = Key(self.bucket)
        k.key = 'F_' + fuuid + '.png'
        print("set contents")
	#k.set_contents_from_filename(self.imagePath, cb=self.percent_cb, num_cb=10)
        #self.imgUrl = 'https://' + operationConfigs['REGION_HOST'] + '/' + operationConfigs['AWS_BUCKET'] + '/' + k.key
        #k.set_acl('public-read')

        logging.info("#generate 128*128 thumbnail")
        im = Image.open(self.imagePath)
        im.thumbnail((128, 128), Image.ANTIALIAS)
        head, tail = os.path.split(self.imagePath)
        thumb_path = head + "/T_" + tail
        im.save(thumb_path, "PNG")

        logging.info("#upload thumbnail")
        k = Key(self.bucket)
        k.key = "T_" + fuuid + '.png'
        k.set_contents_from_filename(thumb_path, cb=self.percent_cb, num_cb=10)
        self.thumbUrl = 'https://' + operationConfigs['REGION_HOST'] + '/' + operationConfigs['AWS_BUCKET'] + '/' + k.key
        self.imgUrl = 'https://' + operationConfigs['REGION_HOST'] + '/' + operationConfigs['AWS_BUCKET'] + '/' + k.key
	k.set_acl('public-read')

    def deffectDetection(self):
        i = 1
	global operationConfigs
        while True:

            self.UPSpowerInput = self.pijuice.status.GetStatus()['data']['powerInput']

            if i == 1:
                self.USBpowerOutput = 'ON'

            if self.UPSpowerInput == 'NOT_PRESENT' and self.USBpowerOutput == 'ON':
                logging.warning('UPS not being charged - shutting down camera.\n')
                powerOffUSBs()
                self.USBpowerOutput = 'OFF'
                sleep(1)
                continue

            elif self.UPSpowerInput == 'NOT_PRESENT' and self.USBpowerOutput == 'OFF':
                logging.warning('UPS not being charged - trying again.\n')
                sleep(1)
                continue

            elif self.UPSpowerInput == 'PRESENT' and self.USBpowerOutput == 'OFF':
                logging.info('UPS just started being charged - booting camera.\n')
                powerOnUSBs()
                self.USBpowerOutput = 'ON'
                sleep(5)

            if i != 1:
                self.initCamera()

            logging.info('Taking image # ' + str(i))
            self.saveImage()
	    logging.info("Uploading image!")
	    self.uploadImages()
	    
	    self.fabric = {
                '_id': i,
                'defect': 'None',
                'date': self.rawImageTimeStamp,
                'imageUrl': self.imgUrl,
                'thumbUrl': self.thumbUrl,
                'deviceID': operationConfigs['DEVICE_ID'],
            }

            if operationConfigs['deffectDetectionMode']:
		logging.info("Starting detection modules!")
                lycraDeffectDetected = funcao_deteccao_lycra_tracadelas(self.imagePath)
                agulhaDeffectDetected = funcao_detecao_agulhas(self.imagePath)

                if agulhaDeffectDetected:
                    self.fabric['defect'] = 'Agulha'
                    logging.info("Defeito agulha!")

                if lycraDeffectDetected[0]:
                    self.fabric['defect'] = lycraDeffectDetected[1]
                    logging.info("Defeito lycra!")

                if operationConfigs['stopMachineMode'] and (lycraDeffectDetected[0] or agulhaDeffectDetected):
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setup(operationConfigs['outputPort'], GPIO.OUT, initial=GPIO.LOW)
                    GPIO.output(operationConfigs['outputPort'], GPIO.LOW)
                    sleep(1)
                    GPIO.setup(operationConfigs['outputPort'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            # por try except
            try:
                time1 = datetime.datetime.now()
                logging.info("Sending to WS!")
                r = self.client.post(operationConfigs['FABRIC_ENDPOINT'], data=self.fabric)
                time2 = datetime.datetime.now()
                elapsed_time = time2 - time1
                logging.info("Fabric post status code: {}".format(r.status_code))
                logging.info("Sent to WS!! Elapsed time (ms): {}\n".format(elapsed_time.microseconds / 1000))
                self.blinkLED()
            except:
                logging.warning('Error communicating with WS\n')
                self.blinkLED()
                pass

            sleep(1)
            i += 1

    def blinkLED(self):
        pass
        self.pijuice.status.SetLedBlink('D2', 2, [255, 0, 0], 50, [255, 0, 0], 50)
        sleep(.1)
        self.pijuice.status.SetLedState('D2', [0, 0, 0])


def connectWSock():
	global operationConfigs
	global sessionID
	try:
		socketIO = SocketIO(operationConfigs['SOCK_ENDPOINT'], 3000, cookies={'sessionId': sessionID},
                                wait_for_connection=False)
		socketIO.on('connect', on_connect)
		socketIO.on('/devices/updated', on_updated)
		socketIO.on('disconnect', on_disconnect)
		socketIO.on('reconnect', on_reconnect)
		socketIO.wait()
	except ConnectionError:
		logging.warning('Error connecting WebSockets\n')

def on_connect(self):
	print('[Connected]')

def on_reconnect(self):
	print('[Reconnected]')

def on_disconnect():
	logging.warning('Error connecting WebSockets\n')

def on_connect():
	print('[Connected]')

def on_reconnect():
	print('[Reconnected]')

def on_disconnect():
	print('[Disconnected]')

def on_updated(*args):
	#print('\n\non_updated\n\n')
	global operationConfigs
	try:
		configs = args[0]['data']
		if(configs['code'] == operationConfigs['DEVICE_ID']):

			if(configs.get('stop', -1) >= 0):
				operationConfigs['stopMachineMode'] = (configs['stop'] == 1)

			if (configs.get('detection', -1) >= 0):
				operationConfigs['deffectDetectionMode'] = (configs['detection'] == 1)
			if (configs.get('gpio', -1) >= 0):
				operationConfigs['outputPort'] = configs['gpio']

			#self.updateJsonFile()
			print operationConfigs
	except ValueError:
		logging.warning("Error parsing configs: " + ValueError) 

if __name__ == "__main__":
    global sessionID
    s = Smartex()
    s.authWS()
    s.connectAWSS3()
    sessionID = s.csrftoken
    t1 = Thread(target = connectWSock)    
    t1.setDaemon(True)
    t1.start()
    #t1.join()
    #s.connectWSock()
    s.deffectDetection()
    t1.join()
