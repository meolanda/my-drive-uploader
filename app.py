import os
from flask import Flask, request, render_template
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
import datetime
from io import BytesIO
from PIL import Image # <-- เพิ่มเครื่องมือย่อขนาดรูปภาพ

app = Flask(__name__)

# --- ตั้งค่า (เหมือนเดิม) ---
SERVICE_ACCOUNT_FILE = 'service_account.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
API_SERVICE_NAME = 'drive'
API_VERSION = 'v3'
ROOT_FOLDER_NAME = "รูปหน้างาน Handyman 2568" 
SHARED_DRIVE_ID = "YOUR_SHARED_DRIVE_ID_HERE" # <-- ใส่ ID ของคุณ

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build(API_SERVICE_NAME, API_VERSION, credentials=credentials)

# --- ฟังก์ชันผู้ช่วย (เหมือนเดิม) ---
def search_folder(service, folder_name, parent_id=None):
    query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    response = service.files().list(
        q=query, driveId=SHARED_DRIVE_ID, corpora='drive',
        includeItemsFromAllDrives=True, supportsAllDrives=True,
        spaces='drive', fields='files(id, name)'
    ).execute()
    files = response.get('files', [])
    return files[0]['id'] if files else None

def create_folder(service, folder_name, parent_id=None):
    file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
    if parent_id:
        file_metadata['parents'] = [parent_id]
    
    folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
    return folder.get('id')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    # ส่วนรับข้อมูลจากฟอร์ม (เหมือนเดิม)
    uploader_name = request.form.get('uploader_name')
    project_name = request.form.get('project_name')
    submission_date = request.form.get('submission_date')
    main_category = request.form.get('main_category')
    sub_category_1_select = request.form.get('sub_category_1')
    sub_category_1_text = request.form.get('sub_category_1_text')
    sub_category_1 = sub_category_1_select or sub_category_1_text
    sub_category_2 = request.form.get('sub_category_2')
    uploaded_files = request.files.getlist('file')

    if not all([uploader_name, project_name, submission_date, main_category]) or not uploaded_files:
        return "กรุณากรอกข้อมูลและเลือกไฟล์ให้ครบถ้วน", 400

    try:
        # ส่วนสร้างโฟลเดอร์ (เหมือนเดิม)
        current_parent_id = search_folder(service, ROOT_FOLDER_NAME)
        if not current_parent_id:
            current_parent_id = create_folder(service, ROOT_FOLDER_NAME, parent_id=SHARED_DRIVE_ID)
        
        thai_months = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
        submission_date_obj = datetime.datetime.strptime(submission_date, '%Y-%m-%d')
        year, month, day = submission_date_obj.year, submission_date_obj.month, submission_date_obj.day
        month_folder_name = f"{year} {month:02d} {thai_months[month-1]}"
        
        path_parts = [month_folder_name, submission_date, project_name, main_category, sub_category_1, sub_category_2]
        folders_to_process = [part for part in path_parts if part]

        final_folder_path = ROOT_FOLDER_NAME
        for folder_name in folders_to_process:
            final_folder_path += f" / {folder_name}"
            folder_id = search_folder(service, folder_name, parent_id=current_parent_id)
            if not folder_id:
                folder_id = create_folder(service, folder_name, parent_id=current_parent_id)
            current_parent_id = folder_id
        final_upload_folder_id = current_parent_id
        
        # วนลูปอัปโหลดไฟล์
        successful_uploads = []
        for file_to_upload in uploaded_files:
            # --- ส่วนที่เพิ่มเข้ามา: การย่อขนาดและบีบอัดรูปภาพ ---
            in_memory_file = BytesIO(file_to_upload.read())
            img = Image.open(in_memory_file)

            # กำหนดขนาดใหญ่สุดที่ต้องการ (เช่น 1920x1080 pixels)
            max_width = 1920
            max_height = 1080
            
            # ย่อขนาดรูปภาพถ้ามันใหญ่เกินไป โดยยังรักษาสัดส่วนเดิม
            img.thumbnail((max_width, max_height))
            
            # บันทึกรูปภาพที่ย่อแล้วลงในหน่วยความจำ เป็นไฟล์ JPEG คุณภาพ 85%
            output_stream = BytesIO()
            img.save(output_stream, format='JPEG', quality=85)
            output_stream.seek(0)
            # --- จบส่วนของการย่อขนาด ---

            # เปลี่ยนชื่อไฟล์ให้ลงท้ายด้วย .jpg และมีชื่อผู้อัปโหลด
            original_filename = file_to_upload.filename
            name_part, extension = os.path.splitext(original_filename)
            new_filename = f"{name_part} (อัปโหลดโดย {uploader_name}).jpg"

            file_metadata = {'name': new_filename, 'parents': [final_upload_folder_id]}
            
            # อัปโหลดไฟล์ที่ย่อขนาดแล้วจากหน่วยความจำ
            media = MediaIoBaseUpload(output_stream, mimetype='image/jpeg', resumable=True)
            
            service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
            successful_uploads.append(original_filename)

        return f"อัปโหลดไฟล์ {len(successful_uploads)} ไฟล์ ({', '.join(successful_uploads)}) ไปยังโฟลเดอร์ '{final_folder_path}' สำเร็จ! (ไฟล์ถูกย่อขนาดและบีบอัดแล้ว)"

    except HttpError as error:
        print(f"An error occurred: {error}")
        return "เกิดข้อผิดพลาดในการอัปโหลดไฟล์", 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)