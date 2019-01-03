import datetime
from Queue import Queue
from threading import Thread
import uuid
import os
import requests
from PIL import Image
from boto.s3.key import Key
import base64
from io import BytesIO
import logging


class FabricWorker:

    def __init__(self, maxsize, bucket, client, operation_configs):
        self.client = client
        self.bucket = bucket
        self.operationConfigs = operation_configs
        self.queue = Queue(maxsize=maxsize)
        self.thread = Thread(target=self.upload)
        self.thread.setDaemon(True)
        self.thread.start()

    def add_work(self, obj):
        logging.info("Adding object to worker queue! Queue has now " + str(self.queue.qsize()) + " elements!")
        self.queue.put(obj)

    def upload(self):
        while True:
            try:
                obj = self.queue.get()
                image_path = obj["path"]
                fabric = obj["fabric"]
                paths = self.upload_image(image_path)
                fabric["imageUrl"] = paths["img_url"]
                fabric["thumbUrl"] = paths["thumb_url"]
                self.upload_fabric(fabric)
                self.queue.task_done()
            except Exception as ex:
                logging.exception("Error uploading fabric object!")
                continue

    def upload_fabric(self, fabric):
        begin = datetime.datetime.now()
        r = self.client.post(self.operationConfigs['FABRIC_ENDPOINT'], data=fabric)
        elapsed = datetime.datetime.now() - begin
        logging.info("\nFabric object uploaded - elapsed time (s): {}".format(elapsed.total_seconds()))

    def upload_image(self, image_path):
        if self.operationConfigs['storage'] == "ONLINE":
            return self.upload_aws(image_path)
        else:
            return self.upload_local(image_path)

    def upload_aws(self, image_path):
        begin = datetime.datetime.now()
        fuuid = str(uuid.uuid4())
        k = Key(self.bucket)
        k.key = 'F_' + fuuid + '.png'
        k.set_contents_from_filename(image_path)
        img_url = 'https://' + self.operationConfigs['REGION_HOST'] + '/' + self.operationConfigs[
            'AWS_BUCKET'] + '/' + k.key
        k.set_acl('public-read')

        im = Image.open(image_path)
        im.thumbnail((128, 128), Image.ANTIALIAS)
        head, tail = os.path.split(image_path)
        thumb_path = head + "/T_" + tail
        im.save(thumb_path, "PNG")

        k = Key(self.bucket)
        k.key = "T_" + fuuid + '.png'
        k.set_contents_from_filename(thumb_path)
        thumb_url = 'https://' + self.operationConfigs['REGION_HOST'] + '/' + self.operationConfigs[
            'AWS_BUCKET'] + '/' + k.key
        k.set_acl('public-read')

        paths = {
            'img_url': img_url,
            'thumb_url': thumb_url
        }
        elapsed = datetime.datetime.now() - begin
        logging.info("Image uploaded - elapsed time (s): {}\n".format(elapsed.total_seconds()))

        return paths

    def upload_local(self, image_path):
        begin = datetime.datetime.now()
        fuuid = str(uuid.uuid4())
        name = 'F_' + fuuid + '.png'

        with open(image_path, "rb") as imageFile:
            b64Img = base64.b64encode(imageFile.read())

        img = {
            name: "data:image/png;base64, " + b64Img
        }
        r = requests.post("http://" + self.operationConfigs['STORAGE_ENDPOINT'] + "/" + name, json=img)

        img_url = self.operationConfigs['WS_ENDPOINT'] + 'fabrics/' + name

        im = Image.open(self.imagePath)
        im.thumbnail((128, 128), Image.ANTIALIAS)

        name = "T_" + fuuid + '.png'
        buff = BytesIO()
        im.save(buff, format="JPEG")
        b64Img = base64.b64encode(buff.getvalue()).decode("utf-8")

        img = {
            name: "data:image/png;base64, " + b64Img
        }
        r = requests.post("http://" + self.operationConfigs['STORAGE_ENDPOINT'] + "/" + name, json=img)

        thumb_url = self.operationConfigs['WS_ENDPOINT'] + 'fabrics/' + name

        paths = {
            'img_url': img_url,
            'thumb_url': thumb_url
        }
        elapsed = datetime.datetime.now() - begin
        logging.info("Image uploaded - elapsed time (s): {}\n".format(elapsed.total_seconds()))

        return paths

    def join(self):
        self.queue.join()
        self.thread.join()