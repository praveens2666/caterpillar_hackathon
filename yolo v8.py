from ultralytics import YOLO
import cv2
import winsound
import pyttsx3
import threading

# Initialize Text-to-Speech engine
engine = pyttsx3.init()
engine.setProperty('rate', 250)  # Increase speed
engine.setProperty('volume', 1.0)  # Max volume

# Speak in a separate thread to avoid blocking
def speak_text(text):
    def run():
        engine.say(text)
        engine.runAndWait()
    threading.Thread(target=run, daemon=True).start()

# Allowed classes
allowed_classes = ['person', 'car', 'truck', 'bus', 'motorcycle']

# Load the pre-trained YOLOv8 Nano model
model = YOLO("yolov8n.pt")

# Open the webcam
cap = cv2.VideoCapture(0)

if not cap.isOpened():
    error_message = "Error: Cannot open webcam"
    print(f"❌ {error_message}")
    speak_text(error_message)
    exit()

startup_message = "Webcam initialized. Press Q to quit."
print(f"✅ {startup_message}")
speak_text(startup_message)

while True:
    ret, frame = cap.read()
    if not ret:
        error_message = "Failed to grab frame"
        print(f"❌ {error_message}")
        speak_text(error_message)
        break

    # Run YOLOv8 detection
    results = model.predict(source=frame, imgsz=640, conf=0.5, verbose=False)

    for r in results:
        for box in r.boxes:
            cls = int(box.cls[0])
            class_name = model.names[cls]

            if class_name not in allowed_classes:
                continue

            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            bbox_width = x2 - x1
            bbox_ratio = bbox_width / frame.shape[1]

            # Draw bounding box and label
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, f"{class_name} {conf:.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            # Alert if object is too close
            if bbox_ratio > 0.5:
                alert_message = f"Alert! {class_name} very near!"
                print(f"⚠️ {alert_message}")
                winsound.Beep(1000, 500)
                speak_text(alert_message)

    # Show the annotated frame
    cv2.imshow("Heavy Vehicle Proximity Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
