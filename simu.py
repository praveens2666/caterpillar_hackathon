from flask import Flask, request
from ultralytics import YOLO
import cv2
import numpy as np
import base64

app = Flask(__name__)

# Load YOLOv8 model
model = YOLO("yolov8n.pt")
allowed_classes = ['person', 'car', 'truck', 'bus', 'motorcycle']

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Heavy Vehicle Proximity Detection</title>
        <style>
            body { font-family: Arial; text-align: center; }
            video, img { width: 640px; height: 480px; margin: 10px; border: 2px solid #333; }
            .alert { color: red; font-weight: bold; }
        </style>
    </head>
    <body>
        <h1>Heavy Vehicle Proximity Detection</h1>
        <video id="video" autoplay muted></video>
        <canvas id="canvas" width="640" height="480" style="display:none;"></canvas>
        <img id="output">
        <div id="alerts"></div>

        <script>
            const video = document.getElementById('video');
            const canvas = document.getElementById('canvas');
            const output = document.getElementById('output');
            const alertsDiv = document.getElementById('alerts');
            const ctx = canvas.getContext('2d');

            navigator.mediaDevices.getUserMedia({ video: true })
                .then(stream => { video.srcObject = stream; })
                .catch(err => { console.error(err); });

            function captureAndSend() {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const image = canvas.toDataURL('image/jpeg');

                fetch('/detect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ image: image })
                })
                .then(response => response.json())
                .then(data => {
                    output.src = data.image;
                    alertsDiv.innerHTML = data.alerts.map(alert => `<p class="alert">${alert}</p>`).join('');
                    
                    // Use browser text-to-speech
                    data.alerts.forEach(alert => {
                        const utterance = new SpeechSynthesisUtterance(alert);
                        utterance.rate = 1.2;
                        utterance.volume = 1.0;
                        speechSynthesis.speak(utterance);
                    });
                })
                .catch(console.error);
            }

            setInterval(captureAndSend, 1000);
        </script>
    </body>
    </html>
    '''

@app.route('/detect', methods=['POST'])
def detect():
    data = request.json['image']
    image_bytes = base64.b64decode(data.split(',')[1])
    np_arr = np.frombuffer(image_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    results = model.predict(source=frame, imgsz=640, conf=0.5, verbose=False)

    alerts = []
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

            label = f"{class_name} {conf:.2f}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            if bbox_ratio > 0.5:
                alert_message = f"Alert! {class_name} very near!"
                alerts.append(alert_message)

    _, buffer = cv2.imencode('.jpg', frame)
    frame_base64 = base64.b64encode(buffer).decode('utf-8')

    return {'alerts': alerts, 'image': f"data:image/jpeg;base64,{frame_base64}"}

if __name__ == '__main__':
    app.run(debug=True)
