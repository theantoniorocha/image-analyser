import os
from time import sleep
import datetime
from tracadelas_deteccao import funcao_deteccao_lycra_tracadelas
from detecao_agulha_v02 import funcao_detecao_agulhas
import RPi.GPIO as GPIO
from pijuice import PiJuice
from pyueye import ueye
import numpy as np
from scipy import misc, ndimage
import ctypes
from control_usb import powerOffUSBs, powerOnUSBs
import logging
import json
import sys
import pigpio

from workers import FabricWorker
from ws_connectivity import WebSockets, AWS, WebServer


reload(sys)
sys.setdefaultencoding('utf-8')


class Smartex:
    OP_OK = 0
    OP_ERR = -1
    pijuice = PiJuice(1, 0x14)

    def __init__(self, configsFile='/home/smartex/image-analyser/new_gen/configs.json'):
        if not os.path.exists(configsFile):
            print("Config file does not exist.")
            exit()
        print "Starting..."
        self.configsFile = configsFile
        self.operationConfigs = json.loads(open(configsFile).read())
        print "Configurations loaded from " + configsFile

        logging.basicConfig(filename='/home/smartex/image-analyser/new_gen/smartex_main.log', level=logging.INFO, \
                            format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger().addHandler(logging.StreamHandler())

        if(self.operationConfigs['CAMERA_TYPE'] == "ids"):
            print "IDS"
            from ids_camera import Camera
        else:
            print "Ardu cam"
            from ardu_camera import Camera

        self.camera = Camera(self.operationConfigs)
        self.webServer = WebServer(self.operationConfigs)
        self.aws = AWS(self.operationConfigs)

        self.authEverything()
        self.fabricWorker = FabricWorker(20, self.aws.bucket, self.webServer.client, self.operationConfigs)

        if self.authenticated:
            self.webSockets = WebSockets(self.operationConfigs, self.webServer.session_id)
            self.webSockets.startWSockService()
            self.deffectDetection()
            self.webSockets.join()
            self.fabricWorker.join()
        else:
            logging.warning("You need to authenticate first!")

    def updateJsonFile(self):
        jsonFile = open(self.configsFile, "w+")
        jsonFile.write(json.dumps(self.operationConfigs))
        jsonFile.close()

    def setLEDParams(self, pi, i, j):
        i = (i % 26)
        j = (j % 26)
        valFront = min((i * 10), 255)
        valBack = min((j * 10), 255)
        self.operationConfigs['frontledint'] = valFront
        WebSockets.changeLEDInt(pi, self.operationConfigs['frontledgpio'], self.operationConfigs['frontledint'])
        self.operationConfigs['backledint'] = valBack
        WebSockets.changeLEDInt(pi, self.operationConfigs['backledgpio'], self.operationConfigs['backledint'])

    def deffectDetection(self):
        i = 1
        j = 1
        pi = pigpio.pi()
        WebSockets.changeLEDInt(pi, self.operationConfigs['frontledgpio'], self.operationConfigs['frontledint'])
        WebSockets.changeLEDInt(pi, self.operationConfigs['backledgpio'], self.operationConfigs['backledint'])

        while True:
            begin = datetime.datetime.now()
            logging.info('Beginning iteration # ' + str(i))
            self.UPSpowerInput = self.pijuice.status.GetStatus()['data']['powerInput']

            if i == 1:
                self.USBpowerOutput = 'OFF'

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
                sleep(2.5)

            now = datetime.datetime.now()
            elapsed = now - begin

            logging.info("USB ports are up - elapsed time (s): {}".format(elapsed.total_seconds()))

            if i != 1:
                self.camera.initCamera()

            now_ant = now
            now = datetime.datetime.now()
            elapsed = now - now_ant

            logging.info("Camera is ready - elapsed time (s): {}".format(elapsed.total_seconds()))

            try:
                logging.info('Taking image!')
                #self.setLEDParams(pi, i - 1, j - 1)
                self.camera.saveImage()
                #self.setLEDParams(pi, 1, 1)
                now_ant = now
                now = datetime.datetime.now()
                elapsed = now - now_ant
                logging.info("Image taken and saved - elapsed time (s): {}".format(elapsed.total_seconds()))
            except Exception as ex:
                logging.exception("Error taking/saving image! Continuing to next iteration..")
                continue

            defect = 'None'

            if self.operationConfigs['deffectDetectionMode']:
                logging.info("Analyzing images for defect..")
                lycraDeffectDetected = funcao_deteccao_lycra_tracadelas(self.camera.image)
                agulhaDeffectDetected = funcao_detecao_agulhas(self.camera.image)

                if agulhaDeffectDetected:
                    defect = 'Agulha'
                    logging.info("Defeito agulha detectado!")

                if lycraDeffectDetected[0]:
                    defect = lycraDeffectDetected[1]
                    logging.info("Defeito lycra detectado!")

                if self.operationConfigs['stopMachineMode'] and (lycraDeffectDetected[0] or agulhaDeffectDetected):
                    logging.info("Stoping the machine!")
                    GPIO.setmode(GPIO.BCM)
                    GPIO.setup(self.operationConfigs['outputPort'], GPIO.OUT, initial=GPIO.LOW)
                    GPIO.output(self.operationConfigs['outputPort'], GPIO.LOW)
                    sleep(1)
                    GPIO.setup(self.operationConfigs['outputPort'], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

                now_ant = now
                now = datetime.datetime.now()
                elapsed = now - now_ant
                logging.info("Detection modules finished -elapsed time (s): {}\n".format(elapsed.total_seconds()))

            fabric = {
                '_id': self.lastID + i,
                'defect': defect,
                'date': self.camera.rawImageTimeStamp,
                'imageUrl': "",
                'thumbUrl': "",
                'deviceID': self.operationConfigs['DEVICE_ID'],
                'LEDBack':  self.operationConfigs['backledint'],
                'LEDFront':  self.operationConfigs['frontledint']
            }

            obj = {
                'path': self.camera.imagePath,
                'fabric': fabric
            }
            self.fabricWorker.add_work(obj)

            elapsed = datetime.datetime.now() - begin
            sleep_time = max(self.operationConfigs['interval'] - elapsed.total_seconds(), 0)

            logging.info('Iteration # ' + str(i) + " finished!")
            logging.info("\nTotal elapsed time (s): {}".format(elapsed.total_seconds()))
            logging.info("Will sleep for (s): {}".format(sleep_time))

            sleep(sleep_time)
            i += 1
            if i % 26 == 0:
                j += 1

    def authEverything(self):
        while self.webServer.authWS() != self.OP_OK:
            logging.warning("Reconnecting WebServer!")
        self.lastID = self.webServer.getLastID()

        if self.operationConfigs['storage'] == "ONLINE":
            while self.aws.connectAWSS3() != self.OP_OK:
                logging.warning("Reconnecting AWS!")
        self.authenticated = True


    def blinkLED(self):
        pass
        self.pijuice.status.SetLedBlink('D2', 2, [255, 0, 0], 50, [255, 0, 0], 50)
        sleep(.1)
        self.pijuice.status.SetLedState('D2', [0, 0, 0])

if __name__ == "__main__":
    s = Smartex()