import subprocess
from time import sleep

def powerOffUSBs():
    proc = subprocess.Popen('echo \'lycralycra\n\' | sudo -S echo \'1-1\' | sudo tee /sys/bus/usb/drivers/usb/unbind',
                        shell=True, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
    print('Shutted down USB ports.')

def powerOnUSBs():
    proc = subprocess.Popen('echo \'lycralycra\n\' | sudo -S echo \'1-1\' | sudo tee /sys/bus/usb/drivers/usb/bind',
                        shell=True, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
    print('Booted on USB ports.')

if __name__ == "__main__":
    pass
    #powerOffUSBs()
    #sleep(8)
    #powerOnUSBs()
