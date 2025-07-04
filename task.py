from flask import Flask, request, render_template_string
import pandas as pd
import joblib

app = Flask(__name__)

# Load your ML model
model = joblib.load('caterpillar_task_time_model.joblib')

# HTML page (embedded as string)
html_page = '''
<!DOCTYPE html>
<html>
<head>
    <title>Heavy Vehicle Task Time Predictor</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #f2f2f2; padding: 20px; }
        form { background-color: #fff; padding: 20px; border-radius: 8px; max-width: 500px; margin: auto; }
        h1 { text-align: center; }
        label { display: block; margin-top: 10px; }
        input, select { width: 95%; padding: 8px; margin-top: 5px; }
        button { margin-top: 15px; padding: 10px 15px; background-color: #4CAF50; color: white; border: none; cursor: pointer; }
        .result { text-align: center; font-size: 1.5em; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>Heavy Vehicle Task Time Predictor</h1>
    <form method="POST">
        <label>Machine Type:</label>
        <input type="text" name="machine_type" required>

        <label>Task Type:</label>
        <input type="text" name="task_type" required>

        <label>Material Type:</label>
        <input type="text" name="material_type" required>

        <label>Payload Weight (kg):</label>
        <input type="number" step="0.01" name="payload_weight" required>

        <label>Distance (m):</label>
        <input type="number" step="0.01" name="distance" required>

        <label>Terrain Slope (%):</label>
        <input type="number" step="0.01" name="terrain_slope" required>

        <label>Average Engine RPM:</label>
        <input type="number" step="0.01" name="avg_engine_rpm" required>

        <label>Average Fuel Rate (L/h):</label>
        <input type="number" step="0.01" name="avg_fuel_rate" required>

        <label>Operator ID:</label>
        <input type="text" name="operator_id" required>

        <label>Weather Conditions:</label>
        <input type="text" name="weather_conditions" required>

        <button type="submit">Predict Task Time</button>
    </form>

    {% if prediction %}
        <div class="result">Predicted Task Time: <strong>{{ prediction }}</strong></div>
    {% endif %}
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def index():
    prediction = None

    if request.method == 'POST':
        try:
            # Collect form data into a DataFrame
            input_data = pd.DataFrame({
                'machine_type': [request.form['machine_type']],
                'task_type': [request.form['task_type']],
                'material_type': [request.form['material_type']],
                'payload_weight': [float(request.form['payload_weight'])],
                'distance': [float(request.form['distance'])],
                'terrain_slope': [float(request.form['terrain_slope'])],
                'avg_engine_rpm': [float(request.form['avg_engine_rpm'])],
                'avg_fuel_rate': [float(request.form['avg_fuel_rate'])],
                'operator_id': [request.form['operator_id']],
                'weather_conditions': [request.form['weather_conditions']]
            })

            # Prediction
            predicted_time = model.predict(input_data)
            total_minutes = round(predicted_time[0], 2)

            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)

            if hours > 0:
                prediction = f"{hours} hours {minutes} minutes"
            else:
                prediction = f"{minutes} minutes"

        except Exception as e:
            prediction = f"Error in prediction: {str(e)}"

    return render_template_string(html_page, prediction=prediction)


if __name__ == '__main__':
    app.run(debug=True,port=5002)
