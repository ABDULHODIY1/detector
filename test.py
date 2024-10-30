import cv2

username = "admin"
password = "19900627AZIZ"
cam_ip = "192.168.1.64"
cap = cv2.VideoCapture(f"rtsp://{username}:{password}@{cam_ip}:554/Streaming/Channels/101")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Kadrni ushlashda xatolik.")
        break

    cv2.imshow('frame', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
