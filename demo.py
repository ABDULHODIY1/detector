import cv2
import torch
from datetime import datetime
import requests
import snap7.client as client
from snap7.util import *
import customtkinter as ctk
import serial
import serial.tools.list_ports
import snap7
import numpy as np
import os

class HumanDetector:
    """
    Odamlarni aniqlash uchun klass
    """
    def __init__(self, camera_index=0, usb_ports=None, plc_ip=None, max_people=None, ip_camera_url=None):
        """
        Detektorni boshlash
        """
        # Get the directory of the current script
        base_dir = os.path.dirname(os.path.abspath(__file__))

        # Construct the full path to the model files
        prototxt_path = os.path.join(base_dir, 'deploy.prototxt')
        model_path = os.path.join(base_dir, 'mobilenet_iter_73000.caffemodel')

        # Load the model
        self.model = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)

        if ip_camera_url:
            # Update the RTSP URL format with proper authentication
            username = "admin"
            password = "19900627AZIZ"
            cam_ip = "192.168.1.64"
            self.cap = cv2.VideoCapture(f"rtsp://{username}:{password}@{cam_ip}:554/Streaming/Channels/101")
        else:
            self.cap = cv2.VideoCapture(camera_index)

        self.out = cv2.VideoWriter(
            'output.avi',
            cv2.VideoWriter_fourcc(*'MJPG'),
            15.,
            (960, 720))
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

        # max_people lug'atida barcha qiymatlar integer ekanligini tekshirish
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
            frame = cv2.resize(frame, (960, 720))

            # Model yordamida aniqlash
            blob = cv2.dnn.blobFromImage(frame, 0.007843, (300, 300), 127.5)
            self.model.setInput(blob)
            detections = self.model.forward()

            # Annotatsiyalarni olish
            h, w = frame.shape[:2]

            # Aniqlangan odamlar sonini sanash
            self.people_count = 0
            for i in range(detections.shape[2]):
                confidence = detections[0, 0, i, 2]
                if confidence > 0.2:
                    idx = int(detections[0, 0, i, 1])
                    if idx == 15:  # 15 - 'person' klassi
                        self.people_count += 1
                        box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
                        (startX, startY, endX, endY) = box.astype("int")
                        cv2.rectangle(frame, (startX, startY), (endX, endY), (0, 255, 0), 2)

            # Signal yuborishni tekshirish
            if self.signal(hour, self.people_count):
                print(f"Signal yuborildi: {now.strftime('%Y-%m-%d %H:%M:%S')} da {self.people_count} odam aniqlangan.")
                self.people_count = 0  # Signal yuborilgandan keyin sanashni qayta boshlash
                self.send_signal(False, method="plc")  # Bu yerda False qiymatni yuborish
                self.send_signal(0, method="plc")  # Bu yerda 0 qiymatni yuborish

            # Kadrda odamlar sonini ko'rsatish
            cv2.putText(frame, f'People Count: {self.people_count}', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)

            # Chiqarish videosini yozish
            self.out.write(frame.astype('uint8'))

            # Kadrni ko'rsatish
            cv2.imshow('frame', frame)

            # 'q' tugmasi bosilganda siklni to'xtatish
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        # Hammasi tugagandan keyin, kadrni va oynani chiqarish
        self.cap.release()
        self.out.release()
        cv2.destroyAllWindows()
        cv2.waitKey(1)

    def send_signal(self, value, method="network", port_name='/dev/ttyUSB0'):
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

        # Kamera uchun variantlar
        self.camera_var = ctk.StringVar(root)
        self.camera_var.set("0")
        self.camera_label = ctk.CTkLabel(root, text="Kamera raqamini kiriting:")
        self.camera_label.pack()
        self.camera_entry = ctk.CTkEntry(root, textvariable=self.camera_var)
        self.camera_entry.pack()

        # USB portlar uchun variantlar
        self.usb_ports = [port.device for port in serial.tools.list_ports.comports()]
        self.usb_var = ctk.StringVar(root)
        self.usb_var.set(self.usb_ports[0] if self.usb_ports else "")
        self.usb_label = ctk.CTkLabel(root, text="USB portni tanlang:")
        self.usb_label.pack()
        self.usb_menu = ctk.CTkOptionMenu(root, variable=self.usb_var, values=self.usb_ports)
        self.usb_menu.pack()

        # PLC IP manzili uchun variantlar
        self.plc_var = ctk.StringVar(root)
        self.plc_var.set("192.168.0.1")
        self.plc_label = ctk.CTkLabel(root, text="PLC IP manzilini kiriting:")
        self.plc_label.pack()
        self.plc_entry = ctk.CTkEntry(root, textvariable=self.plc_var)
        self.plc_entry.pack()

        # Maksimal odamlar soni uchun variantlar
        self.max_people_6_17_var = ctk.IntVar(root)
        self.max_people_6_17_var.set(8)
        self.max_people_6_17_label = ctk.CTkLabel(root, text="6:00-17:00 uchun maksimal odamlar soni:")
        self.max_people_6_17_label.pack()
        self.max_people_6_17_entry = ctk.CTkEntry(root, textvariable=self.max_people_6_17_var)
        self.max_people_6_17_entry.pack()

        self.max_people_17_18_var = ctk.IntVar(root)
        self.max_people_17_18_var.set(4)
        self.max_people_17_18_label = ctk.CTkLabel(root, text="17:00-18:00 uchun maksimal odamlar soni:")
        self.max_people_17_18_label.pack()
        self.max_people_17_18_entry = ctk.CTkEntry(root, textvariable=self.max_people_17_18_var)
        self.max_people_17_18_entry.pack()

        self.max_people_18_24_var = ctk.IntVar(root)
        self.max_people_18_24_var.set(1)
        self.max_people_18_24_label = ctk.CTkLabel(root, text="18:00-24:00 uchun maksimal odamlar soni:")
        self.max_people_18_24_label.pack()
        self.max_people_18_24_entry = ctk.CTkEntry(root, textvariable=self.max_people_18_24_var)
        self.max_people_18_24_entry.pack()

        # Tugma
        self.start_button = ctk.CTkButton(root, text="Boshlash", command=self.start_detection)
        self.start_button.pack()

    def start_detection(self):
        camera_index = int(self.camera_var.get())
        usb_ports = self.usb_var.get()
        plc_ip = self.plc_var.get()
        max_people = {
            "6-17": int(self.max_people_6_17_var.get()),
            "17-18":int(self.max_people_17_18_var.get()),
            "18-24": int(self.max_people_18_24_var.get())
        }

        detector = HumanDetector(camera_index=camera_index, usb_ports=usb_ports, plc_ip=plc_ip, max_people=max_people)
        detector.detect()


if __name__ == "__main__":
    root = ctk.CTk()
    app = App(root)
    root.mainloop()
