import os
from flask import Flask, request, redirect, url_for, render_template, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import ocrmypdf
import threading
import time
import requests
from PyPDF2 import PdfMerger

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER
app.config['SECRET_KEY'] = 'supersecretkey'

headers = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNjc2NTA1OGItYTlkMi00MTQyLTljNmQtZTYwODA1NGJiY2M2IiwidHlwZSI6ImFwaV90b2tlbiJ9.pA9vNXL3xsSgDfUaz7JaLqIqPHfgUKxQS6a"
}
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

def delete_file_later(*file_paths, delay=30):
    def delete_files():
        time.sleep(delay)
        for file_path in file_paths:
            if os.path.exists(file_path):
                os.remove(file_path)
    threading.Thread(target=delete_files).start()

def merge_pdfs(paths, output):
    merger = PdfMerger()
    for pdf in paths:
        merger.append(pdf)
    merger.write(output)
    merger.close()

@app.route('/')
def index():
    return render_template('uploads.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'files' not in request.files:
        return redirect(request.url)

    files = request.files.getlist('files')

    # Check if files were uploaded
    if not files or len(files) == 0:
        return redirect(request.url)

    pdf_files = []
    for file in files:
        if file.filename == '':
            continue
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            # Convert images to PDF
            if filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}:
                image = Image.open(file_path)
                if image.mode in ("RGBA", "P"):  # Convert to RGB if necessary
                    image = image.convert("RGB")
                pdf_path = file_path.rsplit('.', 1)[0] + '.pdf'
                image.save(pdf_path, 'PDF')
                file_path = pdf_path

            pdf_files.append(file_path)

    # Merge PDFs
    if pdf_files:
        merged_pdf_path = os.path.join(app.config['PROCESSED_FOLDER'], 'merged.pdf')
        merge_pdfs(pdf_files, merged_pdf_path)

        processed_filename = 'processed_merged.pdf'
        processed_path = os.path.join(app.config['PROCESSED_FOLDER'], processed_filename)

        # Perform OCR
        skip_ocr = 'skip_ocr' in request.form

        if not skip_ocr:
            try:
                ocrmypdf.ocr(merged_pdf_path, processed_path, skip_text=True)
            except ocrmypdf.exceptions.MissingDependencyError:
                ocrmypdf.ocr(merged_pdf_path, processed_path, force_ocr=True)
        else:
            os.rename(merged_pdf_path, processed_path)
       
        delete_file_later(*pdf_files, merged_pdf_path, processed_path)
        
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
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            pdf_path = file_path.rsplit('.', 1)[0] + '.pdf'
            image.save(pdf_path, 'PDF')
            file_path = pdf_path

        try:
            ocrmypdf.ocr(file_path, processed_path, skip_text=True)
        except ocrmypdf.exceptions.MissingDependencyError:
            ocrmypdf.ocr(file_path, processed_path, force_ocr=True)
        except Exception as e:
            return jsonify({"error": f"OCR failed: {str(e)}"}), 500

        try:
            with open(processed_path, 'rb') as f:
                response = requests.post(edenai_url, data=edenai_data, files={'file': f}, headers=headers)
                response.raise_for_status()  # Check for HTTP errors
                result = response.json()
        except requests.exceptions.RequestException as e:
            return jsonify({"error": f"Request failed: {str(e)}"}), 500
        except ValueError:
            return jsonify({"error": "Invalid JSON response from API"}), 500

        delete_file_later(file_path, processed_path)

        return jsonify(result)

    return jsonify({"error": "File type not allowed"}), 400

if __name__ == '__main__':
    app.run(host='172.17.17.34', port=5000)
