import csv
import os
from datetime import datetime
import cv2
from ultralytics import YOLO
import winsound
import time
import requests
import threading

# ---------------- TELEGRAM CONFIG ----------------
TOKEN = "8669261469:AAF15gMqpUbCq3y_tbLwu5kZfud3XkxDtiU"
CHAT_ID = "6901570952"

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.get(url, params=params, timeout=3)
    except:
        pass

# ---------------- CSV LOGGING ----------------
def log_detection(person_id, height, duration, risk, alert):
    file_path = "data/detection_logs.csv"
    os.makedirs("data", exist_ok=True)

    file_exists = os.path.isfile(file_path)

    with open(file_path, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "date", "time", "person_id", "height", "duration", "risk", "alert"
            ])

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d"),
            datetime.now().strftime("%H:%M:%S"),
            person_id,
            height,
            round(duration, 2),
            risk,
            alert
        ])

# ---------------- RISK LOGIC ----------------
def calculate_risk(height, duration):
    if height >= 380 or duration >= 10:
        return "HIGH", "YES"
    elif height >= 300 or duration >= 5:
        return "MEDIUM", "NO"
    else:
        return "LOW", "NO"

# ---------------- ALARM CONFIG ----------------
alarm_on = False

def continuous_beep():
    global alarm_on
    while alarm_on:
        winsound.Beep(1000, 500)
        time.sleep(0.1)

def start_alarm():
    global alarm_on
    if not alarm_on:
        alarm_on = True
        threading.Thread(target=continuous_beep, daemon=True).start()

def stop_alarm():
    global alarm_on
    alarm_on = False

# ---------------- MODEL ----------------
model = YOLO("yolov8n.pt")

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FPS, 15)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

person_timer = {}
last_log_time = {}

frame_count = 0
last_alert_time = 0
alert_cooldown = 8
log_interval = 5

cv2.namedWindow("Intruder Detection", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Intruder Detection", 1000, 700)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1

    if frame_count % 2 != 0:
        continue

    frame = cv2.flip(frame, 1)

    results = model.track(frame, persist=True, conf=0.5)

    current_ids = []
    high_risk_active = False

    for r in results:
        if r.boxes is not None:
            for box in r.boxes:
                cls = int(box.cls[0])

                if cls == 0:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    if box.id is None:
                        continue

                    person_id = int(box.id[0])
                    current_ids.append(person_id)

                    height = y2 - y1

                    if person_id not in person_timer:
                        person_timer[person_id] = time.time()

                    elapsed = time.time() - person_timer[person_id]

                    risk, alert = calculate_risk(height, elapsed)

                    if risk == "LOW":
                        color = (0, 255, 0)
                    elif risk == "MEDIUM":
                        color = (0, 255, 255)
                    else:
                        color = (0, 0, 255)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                    cv2.putText(frame, f"ID: {person_id}",
                                (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, color, 2)

                    cv2.putText(frame, f"Height: {height}",
                                (x1, y2 + 20),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, color, 2)

                    cv2.putText(frame, f"Time: {int(elapsed)}s",
                                (x1, y2 + 40),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, color, 2)

                    cv2.putText(frame, f"Risk: {risk}",
                                (x1, y2 + 60),
                                cv2.FONT_HERSHEY_SIMPLEX,
                                0.7, color, 2)

                    current_time = time.time()

                    if person_id not in last_log_time:
                        log_detection(person_id, height, elapsed, risk, alert)
                        last_log_time[person_id] = current_time

                    elif current_time - last_log_time[person_id] > log_interval:
                        log_detection(person_id, height, elapsed, risk, alert)
                        last_log_time[person_id] = current_time

                    if risk == "HIGH":
                        high_risk_active = True
                        start_alarm()

                        if current_time - last_alert_time > alert_cooldown:
                            send_telegram_alert("⚠️ person detected near the door take actions!!!")
                            last_alert_time = current_time

    person_timer = {pid: person_timer[pid] for pid in current_ids if pid in person_timer}
    last_log_time = {pid: last_log_time[pid] for pid in current_ids if pid in last_log_time}

    if not high_risk_active:
        stop_alarm()

    cv2.imshow("Intruder Detection", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

stop_alarm()
cap.release()
cv2.destroyAllWindows()