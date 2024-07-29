import os
from flask import Flask, request, redirect, url_for, render_template, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image
import ocrmypdf
import threading
import time
import json
import requests
import xml.etree.ElementTree as ET

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
JPK_FOLDER = 'jpk'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['JPK_FOLDER'] = JPK_FOLDER
app.config['SECRET_KEY'] = 'supersecretkey'

headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjc2NTA1OGItYTlkMi00MTQyLTljNmQtZTYwODA1NGJiY2M2IiwidHlwZSI6ImFwaV90b2tlbiJ9.pA9vNXL3xsSgDfUaz7JaLqIqPHfgUKxQS6a"}
edenai_url = "https://api.edenai.run/v2/ocr/financial_parser"
edenai_data = {
    "providers": "microsoft",
    "document_type" : "invoice",
    "language": "pl",
}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if not os.path.exists(PROCESSED_FOLDER):
    os.makedirs(PROCESSED_FOLDER)

if not os.path.exists(JPK_FOLDER):
    os.makedirs(JPK_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def delete_file_later(files, delay=30):
    def delete_files():
        time.sleep(delay)
        for file in files:
            if os.path.exists(file):
                os.remove(file)
    threading.Thread(target=delete_files).start()

def create_jpk(data, jpk_path):
    root = ET.Element("JPK")
    faktura = ET.SubElement(root, "Faktura")
    
    # Add extracted data to XML
    for key, value in data.items():
        if isinstance(value, dict):
            sub_elem = ET.SubElement(faktura, key)
            for sub_key, sub_value in value.items():
                if sub_value:
                    ET.SubElement(sub_elem, sub_key).text = str(sub_value)
        elif value:
            ET.SubElement(faktura, key).text = str(value)

    tree = ET.ElementTree(root)
    tree.write(jpk_path, encoding='utf-8', xml_declaration=True)

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
            pdf_path = file_path.rsplit('.', 1)[0] + '.pdf'
            image.save(pdf_path, 'PDF')
            file_path = pdf_path

        try:
            ocrmypdf.ocr(file_path, processed_path, skip_text=True)
        except ocrmypdf.exceptions.MissingDependencyError:
            ocrmypdf.ocr(file_path, processed_path, force_ocr=True)

        files_to_delete = [file_path, processed_path]

        delete_file_later(files_to_delete)

        with open(processed_path, 'rb') as f:
            response = requests.post(edenai_url, data=edenai_data, files={'file': f}, headers=headers)
            result = response.json()

        return render_template('upload.html', result=result)

    return redirect(url_for('index'))

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
        jpk_filename = 'JPK_' + filename.rsplit('.', 1)[0] + '.xml'
        jpk_path = os.path.join(app.config['JPK_FOLDER'], jpk_filename)

        if filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}:
            image = Image.open(file_path)
            pdf_path = file_path.rsplit('.', 1)[0] + '.pdf'
            image.save(pdf_path, 'PDF')
            file_path = pdf_path

        try:
            ocrmypdf.ocr(file_path, processed_path, skip_text=True)
        except ocrmypdf.exceptions.MissingDependencyError:
            ocrmypdf.ocr(file_path, processed_path, force_ocr=True)

        files_to_delete = [file_path, processed_path, jpk_path]
        delete_file_later(files_to_delete)

        with open(processed_path, 'rb') as f:
            response = requests.post(edenai_url, data=edenai_data, files={'file': f}, headers=headers)
            result = response.json()

        if 'extracted_data' in result:
            create_jpk(result['extracted_data'][0], jpk_path)
            return send_file(jpk_path, as_attachment=True)
        else:
            return jsonify({"error": "Failed to extract data"}), 500

    return jsonify({"error": "File type not allowed"}), 400

if __name__ == '__main__':
    app.run(host='172.17.17.34', port=5000)
