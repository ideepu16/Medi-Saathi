# Save this as app.py
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from datetime import datetime, date
import os
import json
import requests
import base64

# =====================================================================
# 🔴 AAKHRI TRY: APNI FRESH GEMINI KEY YAHAN DAALEIN 🔴
API_KEY = "AIzaSyCoO1zlfnu9vYUNg5JRkpMvDfwJXIOTvhMg"
# =====================================================================

app = Flask(__name__)
app.secret_key = 'medicine_reminder_secret_key'
DATABASE = 'database.db'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            time TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            taken INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    conn = get_db_connection()
    today = date.today().isoformat()
    current_time = datetime.now().strftime('%H:%M')

    medicines = conn.execute(
        'SELECT * FROM medicines WHERE ? BETWEEN start_date AND end_date ORDER BY time',
        (today,)
    ).fetchall()

    total_today = len(medicines)
    taken_today = sum(1 for med in medicines if med['taken'] == 1)
    pending_today = total_today - taken_today

    due_medicines = []
    for med in medicines:
        med_time = med['time']
        if med_time.startswith(current_time[:2]) and med['taken'] == 0:
            due_medicines.append(med)

    conn.close()

    return render_template('index.html',
                           medicines=medicines,
                           due_medicines=due_medicines,
                           stats={'total': total_today, 'taken': taken_today, 'pending': pending_today},
                           current_time=current_time,
                           today=today)

@app.route('/add', methods=['GET', 'POST'])
def add_medicine():
    if request.method == 'POST':
        name = request.form['name']
        dosage = request.form['dosage']
        time = request.form['time']
        start_date = request.form['start_date']
        end_date = request.form['end_date']

        if not all([name, dosage, time, start_date, end_date]):
            flash('All fields are required!', 'error')
            return redirect(url_for('add_medicine'))

        try:
            start_obj = datetime.strptime(start_date, '%Y-%m-%d')
            end_obj = datetime.strptime(end_date, '%Y-%m-%d')
            if start_obj > end_obj:
                flash('Start date cannot be after end date!', 'error')
                return redirect(url_for('add_medicine'))
        except ValueError:
            flash('Invalid date format!', 'error')
            return redirect(url_for('add_medicine'))

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO medicines (name, dosage, time, start_date, end_date) VALUES (?, ?, ?, ?, ?)',
            (name, dosage, time, start_date, end_date)
        )
        conn.commit()
        conn.close()

        flash(f'Medicine "{name}" added successfully!', 'success')
        return redirect(url_for('index'))

    today = date.today().isoformat()
    return render_template('add_medicine.html', today=today)

@app.route('/view')
def view_medicines():
    conn = get_db_connection()
    medicines = conn.execute('SELECT * FROM medicines ORDER BY start_date DESC, time').fetchall()
    conn.close()
    return render_template('view_medicine_reminder.html', medicines=medicines)

@app.route('/delete/<int:id>')
def delete_medicine(id):
    conn = get_db_connection()
    medicine = conn.execute('SELECT * FROM medicines WHERE id = ?', (id,)).fetchone()
    if medicine:
        conn.execute('DELETE FROM medicines WHERE id = ?', (id,))
        conn.commit()
        flash(f'Medicine "{medicine["name"]}" deleted!', 'info')
    else:
        flash('Medicine not found!', 'error')
    conn.close()
    return redirect(url_for('view_medicines'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_medicine(id):
    conn = get_db_connection()
    medicine = conn.execute('SELECT * FROM medicines WHERE id = ?', (id,)).fetchone()

    if not medicine:
        flash('Medicine not found!', 'error')
        conn.close()
        return redirect(url_for('view_medicines'))

    if request.method == 'POST':
        name = request.form['name']
        dosage = request.form['dosage']
        time = request.form['time']
        start_date = request.form['start_date']
        end_date = request.form['end_date']

        conn.execute(
            '''UPDATE medicines SET name = ?, dosage = ?, time = ?, start_date = ?, end_date = ?
               WHERE id = ?''',
            (name, dosage, time, start_date, end_date, id)
        )
        conn.commit()
        conn.close()
        flash(f'Medicine "{name}" updated successfully!', 'success')
        return redirect(url_for('view_medicines'))

    conn.close()
    return render_template('edit_medicine.html', medicine=medicine)

@app.route('/mark_taken/<int:id>')
def mark_taken(id):
    conn = get_db_connection()
    medicine = conn.execute('SELECT * FROM medicines WHERE id = ?', (id,)).fetchone()
    if medicine:
        new_status = 1 if medicine['taken'] == 0 else 0
        conn.execute('UPDATE medicines SET taken = ? WHERE id = ?', (new_status, id))
        conn.commit()
        status_text = "taken" if new_status == 1 else "not taken"
        flash(f'Marked "{medicine["name"]}" as {status_text}!', 'success')
    conn.close()
    return redirect(url_for('index'))

@app.route('/api/check_reminders')
def check_reminders():
    conn = get_db_connection()
    today = date.today().isoformat()
    current_time = datetime.now().strftime('%H:%M')

    due = conn.execute(
        '''SELECT id, name, dosage, time FROM medicines
           WHERE ? BETWEEN start_date AND end_date AND time LIKE ? || '%' AND taken = 0''',
        (today, current_time[:2])
    ).fetchall()
    conn.close()
    return jsonify({'current_time': current_time, 'due_medicines': [dict(med) for med in due]})

@app.route('/api/scan_prescription', methods=['POST'])
def scan_prescription():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    try:
        img_bytes = file.read()
        base64_image = base64.b64encode(img_bytes).decode('utf-8')
        mime_type = file.mimetype if file.mimetype else 'image/jpeg'

        prompt = """
        Analyze this medicine strip or doctor's prescription. Extract the Medicine Name and the Dosage.
        Return ONLY a raw JSON object exactly in this format: {"name": "Extracted Name", "dosage": "Extracted Dosage"}
        """

        # 🔥 NAYA ACTIVE MODEL: gemini-2.0-flash 🔥
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": base64_image}}
                ]
            }]
        }

        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()

        if response.status_code == 200:
            clean_text = response_data['candidates'][0]['content']['parts'][0]['text'].strip().replace('```json', '').replace('```', '')
            return jsonify(json.loads(clean_text))
        else:
            return jsonify({'error': f"API Error: {response_data.get('error', {}).get('message', 'Unknown Error')}"}), 500

    except Exception as e:
        return jsonify({'error': 'Failed to scan image. Please try again.'}), 500

@app.route('/api/chat', methods=['POST'])
def chat_assistant():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'reply': "No message received."}), 400

    user_message = data.get('message', '')
    if not user_message:
        return jsonify({'reply': "Please ask a question."})

    try:
        system_instruction = """
        You are 'Medi Saathi', a highly intelligent, caring, and helpful AI health assistant for a medicine app.
        Your job is to answer user questions about medicines, side effects, and general health tips.
        IMPORTANT: If a user asks what medicine to take for common symptoms like fever, headache, body ache, or cold, YOU CAN SUGGEST safe, common over-the-counter (OTC) medicines.
        HOWEVER, whenever you suggest a medicine, you MUST end your response with a short disclaimer like: "Note: I am an AI assistant. Please consult a doctor if your symptoms are severe."
        Keep your answers concise, empathetic, and use a friendly mix of Hindi and English (Hinglish).
        """
        full_prompt = system_instruction + "\n\nUser: " + user_message

        # 🔥 NAYA ACTIVE MODEL: gemini-2.0-flash 🔥
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}]
        }

        response = requests.post(url, headers=headers, json=payload)
        response_data = response.json()

        if response.status_code == 200:
            reply_text = response_data['candidates'][0]['content']['parts'][0]['text']
            return jsonify({'reply': reply_text})
        else:
            error_msg = response_data.get('error', {}).get('message', 'Unknown Error')
            return jsonify({'reply': f"Google Server Error: {error_msg}"}), 500

    except Exception as e:
        return jsonify({'reply': "Unable to connect to the server. Please try again."}), 500

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)