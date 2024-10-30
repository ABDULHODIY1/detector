import cv2
from datetime import datetime
import requests
import snap7.client as client
from snap7.util import *
import tkinter as tk
import numpy as np
import tkinter.messagebox as messagebox
import serial
import serial.tools.list_ports
import snap7

class HumanDetector:
    """
    Odamlarni aniqlash uchun klass
    """
    def __init__(self, camera_index=0, usb_ports=None, plc_ip=None, max_people=None, ip_camera_url=None):
        """
        Detektorni boshlash
        """
        # MobileNet modelini yuklash
        self.net = cv2.dnn.readNetFromCaffe(
            'deploy.prototxt',  # Prototxt fayli yo'li
            'mobilenet_iter_73000.caffemodel'  # Model fayli yo'li
        )

        if ip_camera_url:
            username = "admin"
            password = "19900627AZIZ"
            cam_ip = "192.168.2.64"
            self.cap = cv2.VideoCapture(f"rtsp://{username}:{password}@{cam_ip}:554/Streaming/Channels/101")
            print("Check")
        else:
            self.cap = cv2.VideoCapture(camera_index)


        self.out = cv2.VideoWriter(
            'output.avi',
            cv2.VideoWriter_fourcc(*'MJPG'),
            15.,
            (320, 240))
        self.people_count = 0
        self.usb_ports = usb_ports if usb_ports else []
        self.plc_ip = plc_ip

        # PLC ni ulash
        if self.plc_ip:
            self.plc = client.Client()
            self.plc.set_connection_type(3)
            try:
                self.plc.connect(self.plc_ip, 0, 1)
                self.plc_state = self.plc.get_connected()
                print(f"PLC ulandi: {self.plc_state}")
            except Exception as e:
                print(f"PLC ga ulanishda xatolik: {e}")
                self.plc = False
                self.send_signal(False, method="plc")
                self.send_signal(0, method="plc")
        else:
            self.plc = False
            self.send_signal(False, method="plc")
            self.send_signal(0, method="plc")
            print(f'{self.plc}')

        self.max_people = max_people if max_people else {
            "6-17": 8,
            "17-18": 4,
            "18-24": 1
        }

        for key in self.max_people:
            if not isinstance(self.max_people[key], int):
                self.max_people[key] = 0

    def mWriteBool(self, byte, bit, value):
        """
        PLC ga boolean qiymat yozish
        """
        if self.plc:
            data = self.plc.read_area(snap7.types.Areas.MK, 0, byte, 1)
            set_bool(data, 0, bit, value)
            self.plc.write_area(snap7.types.Areas.MK, 0, byte, data)

    def detect(self):
        """
        Odamlarni aniqlash
        """
        while True:
            # Kadrni ushlash
            ret, frame = self.cap.read()
            if not ret:
                print("Kameradan kadrni ushlashda xatolik.")
                break

            # Joriy soatni olish
            now = datetime.now()
            hour = now.hour

            # Aniqlashni tezlashtirish uchun o'lchamini o'zgartirish
            frame_resized = cv2.resize(frame, (300, 300))
            blob = cv2.dnn.blobFromImage(frame_resized, 0.007843, (300, 300), 127.5)

            self.net.setInput(blob)
            detections = self.net.forward()

            self.people_count = 0
            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                if confidence > 0.2:
                    idx = int(detections[0, 0, i, 1])
                    if idx == 15:  # 'person' klassi uchun
                        self.people_count += 1
                        box = detections[0, 0, i, 3:7] * np.array([frame.shape[1], frame.shape[0], frame.shape[1], frame.shape[0]])
                        (startX, startY, endX, endY) = box.astype("int")
                        cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)

            if self.signal(hour, self.people_count):
                print(f"Signal yuborildi: {now.strftime('%Y-%m-%d %H:%M:%S')} da {self.people_count} odam aniqlangan.")
                self.people_count = 0
                self.send_signal(False, method="plc")
                self.send_signal(0, method="plc")

            cv2.putText(frame, f'People Count: {self.people_count}', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
            self.out.write(frame.astype('uint8'))
            frame = cv2.resize(frame, (800, 600))
            cv2.imshow('frame', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        self.cap.release()
        self.out.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)

    def send_signal(self, value, method="serial", port_name='/dev/ttyUSB0'):
        """
        Signal yuborish
        """
        if method == "network":
            try:
                response = requests.post(f"http://{self.url}:{self.port}/signal", json={"signal": value})
                if response.status_code == 200:
                    print("Signal tarmoq orqali yuborildi.")
                else:
                    print(f"Signal tarmoq orqali yuborishda xatolik: {response.status_code}")
            except Exception as e:
                print(f"Tarmoq xatosi: {e}")

        elif method == "serial":
            try:
                ser = serial.Serial(port_name, 9600, timeout=1)
                ser.write(f"{value}\n".encode())
                ser.close()
                print("Signal serial port orqali yuborildi.")
            except Exception as e:
                print(f"Serial port xatosi: {e}")

        elif method == "plc" and self.plc:
            try:
                self.mWriteBool(5, 0, value)
                print("Signal PLC orqali yuborildi.")
            except Exception as e:
                print(f"PLC xatosi: {e}")

    def signal(self, hour, count):
        """
        Odamlar soni va vaqtni tahlil qilish
        """
        if 6 <= hour < 17 and count >= self.max_people["6-17"]:
            self.send_signal(True, method="plc")
            print(True)
            return True
        elif 17 <= hour < 18 and count >= self.max_people["17-18"]:
            self.send_signal(True, method="plc")
            print(True)
            return True
        elif hour >= 18 and count >= self.max_people["18-24"]:
            self.send_signal(True, method="plc")
            print(True)
            return True
        else:
            self.send_signal(False, method="plc")
            print(False)
            return False

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Odamlarni Aniqlash Dasturi")

        self.camera_var = tk.StringVar(root)
        self.camera_var.set("0")
        self.camera_label = tk.Label(root, text="Kamera raqamini kiriting:")
        self.camera_label.pack()
        self.camera_entry = tk.Entry(root, textvariable=self.camera_var)
        self.camera_entry.pack()

        self.usb_ports = [port.device for port in serial.tools.list_ports.comports()]
        self.usb_var = tk.StringVar(root)
        default_usb_ports = self.usb_ports if self.usb_ports else ["USB port topilmadi"]
        self.usb_var.set(default_usb_ports[0])
        self.usb_dropdown = tk.OptionMenu(root, self.usb_var, *default_usb_ports)
        self.usb_dropdown.pack()

        self.plc_ip_label = tk.Label(root, text="PLC IP manzilini kiriting:")
        self.plc_ip_label.pack()
        self.plc_ip_entry = tk.Entry(root)
        self.plc_ip_entry.pack()

        self.max_people_label = tk.Label(root, text="Maksimal odamlar sonini kiriting (soat oralig'iga qarab):")
        self.max_people_label.pack()
        self.max_people_6_17_label = tk.Label(root, text="6:00-17:00 oralig'i:")
        self.max_people_6_17_label.pack()
        self.max_people_6_17_entry = tk.Entry(root)
        self.max_people_6_17_entry.pack()
        self.max_people_17_18_label = tk.Label(root, text="17:00-18:00 oralig'i:")
        self.max_people_17_18_label.pack()
        self.max_people_17_18_entry = tk.Entry(root)
        self.max_people_17_18_entry.pack()
        self.max_people_18_24_label = tk.Label(root, text="18:00-24:00 oralig'i:")
        self.max_people_18_24_label.pack()
        self.max_people_18_24_entry = tk.Entry(root)
        self.max_people_18_24_entry.pack()

        self.ip_camera_label = tk.Label(root, text="IP Kamera URL ni kiriting:")
        self.ip_camera_label.pack()
        self.ip_camera_entry = tk.Entry(root)
        self.ip_camera_entry.pack()

        self.start_button = tk.Button(root, text="Boshlash", command=self.start_detection)
        self.start_button.pack()

    def start_detection(self):
        camera_index = int(self.camera_var.get())
        usb_ports = self.usb_ports
        plc_ip = self.plc_ip_entry.get()
        max_people = {
            "6-17": int(self.max_people_6_17_entry.get()),
            "17-18": int(self.max_people_17_18_entry.get()),
            "18-24": int(self.max_people_18_24_entry.get())
        }
        ip_camera_url = self.ip_camera_entry.get()
        detector = HumanDetector(camera_index, usb_ports, plc_ip, max_people, ip_camera_url)
        detector.detect()

root = tk.Tk()
app = App(root)
root.mainloop()
