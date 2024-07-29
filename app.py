import os
from flask import Flask, request, redirect, url_for, render_template, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import ocrmypdf
import threading
import time
import json
import requests

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['SECRET_KEY'] = 'supersecretkey'

headers = {"Authorization": "Bearer YOUR_EDENAI_API_KEY"}
edenai_url = "https://api.edenai.run/v2/ocr/financial_parser"
edenai_data = {
    "providers": "microsoft",
    "document_type": "invoice",
    "language": "pl",
}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(PROCESSED_FOLDER):
    os.makedirs(PROCESSED_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def delete_file_later(files, delay=30):
    def delete_files():
        time.sleep(delay)
        for file in files:
            if os.path.exists(file):
                os.remove(file)
    threading.Thread(target=delete_files).start()

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        processed_filename = 'processed_' + filename.rsplit('.', 1)[0] + '.pdf'
        processed_path = os.path.join(app.config['PROCESSED_FOLDER'], processed_filename)

        if filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}:
            image = Image.open(file_path)
            if image.mode in ("RGBA", "P"):  # Convert to RGB if necessary
                image = image.convert("RGB")
            pdf_path = file_path.rsplit('.', 1)[0] + '.pdf'
            image.save(pdf_path, 'PDF')
            file_path = pdf_path

        try:
            ocrmypdf.ocr(file_path, processed_path, skip_text=True)
        except ocrmypdf.exceptions.MissingDependencyError:
            ocrmypdf.ocr(file_path, processed_path, force_ocr=True)

        delete_file_later([file_path, processed_path])

        return redirect(url_for('download_file', filename=processed_filename))

    return redirect(url_for('index'))

@app.route('/processed/<filename>')
def download_file(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('index'))

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        processed_filename = 'processed_' + filename.rsplit('.', 1)[0] + '.pdf'
        processed_path = os.path.join(app.config['PROCESSED_FOLDER'], processed_filename)

        if filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}:
            image = Image.open(file_path)
            if image.mode in ("RGBA", "P"):  # Convert to RGB if necessary
                image = image.convert("RGB")
            pdf_path = file_path.rsplit('.', 1)[0] + '.pdf'
            image.save(pdf_path, 'PDF')
            file_path = pdf_path

        try:
            ocrmypdf.ocr(file_path, processed_path, skip_text=True)
        except ocrmypdf.exceptions.MissingDependencyError:
            ocrmypdf.ocr(file_path, processed_path, force_ocr=True)

        with open(processed_path, 'rb') as f:
            response = requests.post(edenai_url, data=edenai_data, files={'file': f}, headers=headers)
            result = response.json()

        delete_file_later([file_path, processed_path])

        return jsonify(result)

    return jsonify({"error": "File type not allowed"}), 400

if __name__ == '__main__':
    app.run(host='172.17.17.34', port=5000)