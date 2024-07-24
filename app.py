from flask import Flask, request, redirect, url_for, send_from_directory, render_template
import os
import subprocess
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

# Sprawdza czy plik ma dozwolone rozszerzenie
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Strona główna z formularzem do przesyłania plików
@app.route('/')
def upload_form():
    return render_template('upload.html')

# Obsługa przesłanych plików
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        # Wykonywanie OCR za pomocą ocrmypdf
        processed_filepath = os.path.join(app.config['PROCESSED_FOLDER'], filename)
        subprocess.run(['ocrmypdf', filepath, processed_filepath])
        return redirect(url_for('download_file', filename=filename))

# Pobieranie przetworzonego pliku
@app.route('/processed/<filename>')
def download_file(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    app.run(host='172.17.17.34', port=5000, debug=True)