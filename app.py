from flask import Flask, request, redirect, url_for, send_from_directory, render_template, flash
import os
import subprocess
import img2pdf
import threading
import time
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # wymagane dla flash messages
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['PROCESSED_FOLDER'] = PROCESSED_FOLDER

# Sprawdza czy plik ma dozwolone rozszerzenie
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Konwertuje obraz na PDF
def convert_image_to_pdf(image_path, output_path):
    with open(image_path, 'rb') as f:
        image_data = f.read()
    with open(output_path, 'wb') as f:
        f.write(img2pdf.convert(image_data))

# Usuwa pliki po 30 sekundach
def delete_files(*filepaths):
    time.sleep(30)
    for filepath in filepaths:
        if filepath:
            try:
                os.remove(filepath)
                print(f"Deleted {filepath}")
            except Exception as e:
                print(f"Error deleting file {filepath}: {e}")

# Strona główna z formularzem do przesyłania plików
@app.route('/')
def upload_form():
    return render_template('upload.html')

# Obsługa przesłanych plików
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Brak części pliku')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('Nie wybrano pliku')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        original_filepath = filepath  # Zachowaj ścieżkę do oryginalnego pliku

        # Sprawdza rozszerzenie pliku i konwertuje na PDF jeśli to obraz
        if filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}:
            pdf_filename = filename.rsplit('.', 1)[0] + '.pdf'
            pdf_filepath = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)
            convert_image_to_pdf(filepath, pdf_filepath)
            filepath = pdf_filepath

        # Wykonywanie OCR za pomocą ocrmypdf
        processed_filepath = os.path.join(app.config['PROCESSED_FOLDER'], os.path.basename(filepath))
        try:
            subprocess.run(['ocrmypdf', '--skip-text', filepath, processed_filepath], check=True)
            threading.Thread(target=delete_files, args=(original_filepath, filepath, processed_filepath)).start()
            return redirect(url_for('download_file', filename=os.path.basename(processed_filepath)))
        except subprocess.CalledProcessError:
            try:
                subprocess.run(['ocrmypdf', '--force-ocr', filepath, processed_filepath], check=True)
                threading.Thread(target=delete_files, args=(original_filepath, filepath, processed_filepath)).start()
                return redirect(url_for('download_file', filename=os.path.basename(processed_filepath)))
            except subprocess.CalledProcessError:
                flash('Błąd przetwarzania pliku za pomocą OCR')
                return redirect(request.url)
    else:
        flash('Plik niedozwolony')
        return redirect(request.url)

# Pobieranie przetworzonego pliku
@app.route('/processed/<filename>')
def download_file(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

# Obsługa błędu 404 - przekierowanie na stronę główną
@app.errorhandler(404)
def page_not_found(e):
    return redirect(url_for('upload_form'))

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(PROCESSED_FOLDER, exist_ok=True)
    app.run(host='172.17.17.34', port=5000, debug=True)