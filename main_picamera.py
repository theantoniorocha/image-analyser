#import ids
from time import sleep
import datetime
import os
from picamera import PiCamera
from tracadelas_deteccao import funcao_deteccao_lycra_tracadelas
from detecao_agulha_v02 import funcao_detecao_agulhas
import RPi.GPIO as GPIO

import pymongo
from pymongo import MongoClient
connection = MongoClient()
db = connection['boilerplate-test']

camera = PiCamera()

#for shutters in range(2000, 10*500, 500):
#    print(shutters)
#    camera.shutter_speed = shutters
#    directory = 'imagens/imagens_shutter%s' % shutters
#    if not os.path.exists(directory):
#        os.makedirs(directory)
#    for i in range(100):
#        sleep(0.2)
#        camera.capture(directory +'/image%s.jpg' % i)
def cam_deffect_detection():
    detectionOn = str(raw_input('Deffect detection mode: (on/off)')) or 'on'
    if detectionOn == 'on':
        print('Detection mode: ON')
    elif detectionOn == 'off':
        print('Detection mode: OFF')
    else:
        print('Input not recognized, not gonna detect.')
    stopMachineOn = str(raw_input('Stop machine mode: (on/off)')) or 'on'
    if stopMachineOn == 'on':
        print('Stop mode: ON')
        output_port = int(raw_input('RPi low voltage GPIO port: (27)')) or 27
    elif stopMachineOn == 'off':
        print('Stop mode: OFF')
    else:
        print('Input not recognized, not gonna stop.')    
   

    #cam = ids.Camera()
    #cam.color_mode = ids.ids_core.COLOR_RGB8    # Get images in RGB format

    #cam.auto_exposure = True
    #cam.continuous_capture = True               # Start image capture

    #for shutters in range(115, 150 ,5):
    #for shutters in range(50,60,5):
    #shutters /= 10.
    #cam.exposure = shutters                            # Set initial exposure to 5ms
    directory = 'teste_domingo_migusta/'
    if not os.path.exists(directory):
        os.makedirs(directory)
    #directory2 = 'imagens/%s' %  now.strftime('%Y_%m_%d_%H_%M_%S') 
    #if not os.path.exists(directory2):
    #    os.makedirs(directory2)
    #print(shutters)
    N = int(raw_input('Number of photos: ')) or 15
    for i in range(N):
	now = datetime.datetime.now()   
	imgName = 'image%s.jpg' % now.strftime('%Y_%m_%d_%H_%M_%S') 
	path1 = directory + imgName
        camera.capture(path1)
        print('Saved: ' + path1) 
        #img, meta = cam.next()                      # Get image as a Numpy array
        #pil_img = Image.fromarray(img)
	#nome_imagem = 'imagem_%s.jpg' % datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S') 
        #path2 = directory + nome_imagem
        #pil_img.save(path1, quality = 100)
        #pil_img.save('teste_domingo_migusta/last_image.jpg', quality = 100)
        #print('Saved: ' + path2)

        fabric = {
            '_id': (i+15),
            'defect': 'None',
            'date': datetime.datetime.now(),
            'imageUrl': 'imgs/'+imgName,
            'deviceID' : 'GJjybzAy5V'
        }

        if detectionOn == 'on':
            deffect_lycra = funcao_deteccao_lycra_tracadelas(path1)
            deffect_agulha = funcao_detecao_agulhas(path1)

            if stopMachineOn == 'on' and (deffect_lycra[0] or deffect_agulha):

                if deffect_agulha:
                    fabric['defect'] = 'agulha'
                if deffect_lycra[0]:
                    fabric['defect'] = deffect_lycra[1]

                GPIO.setmode(GPIO.BCM)
                GPIO.setup(output_port, GPIO.OUT, initial=GPIO.LOW)
                GPIO.output(output_port,GPIO.HIGH)
                sleep(1)
                GPIO.setup(output_port, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                #break

        db['fabrics'].insert_one(fabric)
        sleep(.8)

if __name__ == "__main__":
    cam_deffect_detection()
