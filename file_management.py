from flask import flash, redirect, url_for, render_template
import re
import io
import os
import zipfile
import tempfile
import subprocess
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from models import File,Favorite
from extensions import db
from datetime import datetime

file_bp = Blueprint('file_management', __name__)
LIBREOFFICE_PATH = os.path.join(os.path.dirname(__file__), 'LibreOffice', 'program', 'soffice.exe')
RAR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'WinRAR', 'Rar.exe'))
UNRAR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'WinRAR', 'UnRAR.exe'))

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'mp4',
                          'avi', 'mkv', 'zip', 'rar', 'mp3'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_category(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'txt', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}:
        return 'documents'
    elif ext in {'png', 'jpg', 'jpeg', 'gif'}:
        return 'images'
    elif ext in {'mp4', 'avi', 'mkv'}:
        return 'videos'
    elif ext in {'mp3'}:
        return 'audio'
    else:
        return 'other'

def custom_secure_filename(filename):
    filename = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5\.\-\_]', '', filename)
    return filename

def add_folder_to_zip(folder, zipf, folder_path):
    sub_files = File.query.filter_by(parent_id=folder.id).all()
    for sub_file in sub_files:
        file_path = os.path.join(folder_path, sub_file.filename)
        if sub_file.is_folder:
            add_folder_to_zip(sub_file, zipf, file_path)
        else:
            zipf.writestr(file_path, sub_file.data)

@file_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part'})

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No selected file'})

    if file and allowed_file(file.filename):
        filename = custom_secure_filename(file.filename)
        parent_id = request.form.get('parent_id')

        if parent_id == '':
            parent_id = None

        existing_file = File.query.filter_by(filename=filename, parent_id=parent_id, uploader_id=current_user.id).first()
        if existing_file:
            return jsonify({'success': False, 'message': 'File with the same name already exists'}), 400

        file_data = file.read()
        category = get_file_category(filename)
        tags = request.form.get('tags')

        new_file = File(
            filename=filename,
            data=file_data,
            uploader_id=current_user.id,
            category=category,
            tags=tags,
            parent_id=parent_id,
            created_at=datetime.utcnow()
        )

        db.session.add(new_file)
        db.session.commit()

        all_files = File.query.filter_by(uploader_id=current_user.id).all()
        current_app.logger.info(f'All files after upload: {[file.to_dict() for file in all_files]}')

        return jsonify({'success': True, 'message': 'File uploaded successfully'})

    return jsonify({'success': False, 'message': 'File upload failed or invalid file type'})

@file_bp.route('/upload_folder', methods=['POST'])
@login_required
def upload_folder():
    current_app.logger.info('upload_folder called')
    if 'folder' not in request.files:
        current_app.logger.error('No folder part in request')
        return jsonify({'success': False, 'message': 'No folder part'})

    folder_files = request.files.getlist('folder')
    if not folder_files:
        current_app.logger.error('No selected folder')
        return jsonify({'success': False, 'message': 'No selected folder'})

    root_folder_path = folder_files[0].filename.split('/')[0]
    root_folder_name = custom_secure_filename(root_folder_path)

    tags = request.form.get('tags')
    parent_id = request.form.get('parent_id')

    if parent_id == '':
        parent_id = None

    existing_folder = File.query.filter_by(filename=root_folder_name, parent_id=parent_id, uploader_id=current_user.id, is_folder=True).first()
    if existing_folder:
        current_app.logger.error('Folder with the same name already exists')
        return jsonify({'success': False, 'message': 'Folder with the same name already exists'}), 400

    root_folder = File(
        filename=root_folder_name,
        data=None,
        uploader_id=current_user.id,
        tags=tags,
        is_folder=True,
        parent_id=parent_id,
        is_favorite_folder=False  # 标记为非收藏文件夹
    )

    db.session.add(root_folder)
    db.session.commit()

    def process_file_tree(file, parent_id):
        file_path_parts = file.filename.split('/')[1:]
        current_parent_id = parent_id
        for part in file_path_parts[:-1]:
            existing_folder = File.query.filter_by(filename=custom_secure_filename(part), parent_id=current_parent_id, uploader_id=current_user.id, is_folder=True).first()
            if existing_folder:
                current_parent_id = existing_folder.id
            else:
                new_folder = File(
                    filename=custom_secure_filename(part),
                    data=None,
                    uploader_id=current_user.id,
                    is_folder=True,
                    parent_id=current_parent_id,
                    is_favorite_folder=False  # 标记为非收藏文件夹
                )
                db.session.add(new_folder)
                db.session.commit()
                current_parent_id = new_folder.id

        filename = custom_secure_filename(file_path_parts[-1])
        file_data = file.read()
        category = get_file_category(filename)
        current_app.logger.info(f'Processing file: {filename}, Category: {category}')

        existing_file = File.query.filter_by(filename=filename, uploader_id=current_user.id, parent_id=current_parent_id).first()
        if existing_file:
            return

        new_file = File(
            filename=filename,
            data=file_data,
            uploader_id=current_user.id,
            category=category,
            tags=tags,
            parent_id=current_parent_id
        )

        db.session.add(new_file)

    for file in folder_files:
        if file.filename == '':
            continue

        process_file_tree(file, root_folder.id)

    db.session.commit()

    current_app.logger.info('Folder uploaded successfully')
    return jsonify({'success': True, 'message': 'Folder uploaded successfully'})

@file_bp.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    data = request.get_json()
    folder_name = data.get('folder_name')
    tags = data.get('tags')
    parent_id = data.get('parent_id')

    if not folder_name:
        return jsonify({'success': False, 'message': 'Folder name not provided'}), 400

    folder_name = custom_secure_filename(folder_name)

    existing_folder = File.query.filter_by(filename=folder_name, parent_id=parent_id, uploader_id=current_user.id, is_folder=True).first()
    if existing_folder:
        return jsonify({'success': False, 'message': 'Folder with the same name already exists'}), 400

    new_folder = File(
        filename=folder_name,
        data=None,
        uploader_id=current_user.id,
        is_folder=True,
        parent_id=parent_id,
        tags=tags,
        is_favorite_folder=False  # 标记为非收藏文件夹
    )

    db.session.add(new_folder)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Folder created successfully', 'folder_name': folder_name, 'parent_id': parent_id})

@file_bp.route('/main')
@login_required
def main_page():
    files = File.query.filter_by(uploader_id=current_user.id, parent_id=None).all()
    return render_template('main.html', files=files, category='all')

@file_bp.route('/get_favorite_folders', methods=['GET'])
@login_required
def get_favorite_folders():
    folders = File.query.filter_by(uploader_id=current_user.id, is_favorite_folder=True, is_folder=True).all()
    folder_list = [{'id': folder.id, 'filename': folder.filename} for folder in folders]
    return jsonify(folder_list)

@file_bp.route('/files', methods=['GET'])
@login_required
def file_list():
    category = request.args.get('category', 'all')
    parent_id = request.args.get('folder_id', None)

    current_app.logger.info(f'file_list called with category: {category}, parent_id: {parent_id}')

    files = []

    if category == 'favorites':
        favorite_files = Favorite.query.filter_by(folder_id=parent_id).all()
        for favorite in favorite_files:
            file = File.query.get(favorite.file_id)
            if file:
                files.append(file)
    else:
        if category == 'all':
            query = File.query.filter_by(uploader_id=current_user.id, parent_id=parent_id, is_favorite_folder=False)
            files = query.all()
        else:
            if parent_id:
                query = File.query.filter_by(uploader_id=current_user.id, parent_id=parent_id, is_favorite_folder=False)
                files = query.all()
            else:
                query = File.query.filter_by(uploader_id=current_user.id, is_favorite_folder=False, is_folder=False)
                files = [file for file in query.all() if file.category == category]

                # 递归获取所有子文件夹中的文件
                for folder in File.query.filter_by(uploader_id=current_user.id, is_favorite_folder=False, is_folder=True, parent_id=None).all():
                    files.extend(get_all_sub_files(folder, category))

    file_list = []
    seen_file_ids = set()
    for file in files:
        if file.id not in seen_file_ids:
            file_dict = file.to_dict()
            file_dict['is_favorite'] = Favorite.query.filter_by(file_id=file.id).first() is not None
            if file.parent_id:
                parent_folder = File.query.get(file.parent_id)
                file_dict['source'] = f'子文件夹：{parent_folder.filename}'
            else:
                file_dict['source'] = '单独上传'
            current_app.logger.info(f'Found file: {file_dict["filename"]}, Category: {file_dict["category"]}')
            file_list.append(file_dict)
            seen_file_ids.add(file.id)

    current_app.logger.info(f'Returning file list: {file_list}')
    return jsonify(file_list)

def get_all_sub_files(folder, category):
    sub_files = []
    for sub_file in File.query.filter_by(parent_id=folder.id).all():
        if sub_file.is_folder:
            sub_files.extend(get_all_sub_files(sub_file, category))
        elif sub_file.category == category:
            sub_files.append(sub_file)
    return sub_files

@file_bp.route('/delete', methods=['POST'])
@login_required
def delete_files():
    data = request.get_json()
    file_ids = data.get('file_ids', [])
    if not file_ids:
        return jsonify({'success': False, 'message': 'No files selected for deletion'}), 400

    files = File.query.filter(File.id.in_(file_ids), File.uploader_id == current_user.id).all()
    if not files:
        return jsonify({'success': False, 'message': 'No files found or insufficient permissions'}), 404

    parent_id = files[0].parent_id if files else None

    for file in files:
        delete_file_recursively(file)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Files deleted successfully', 'parent_id': parent_id})

def delete_file_recursively(file):
    if file.is_folder:
        sub_files = File.query.filter_by(parent_id=file.id).all()
        for sub_file in sub_files:
            delete_file_recursively(sub_file)
    db.session.delete(file)
    db.session.commit()

@file_bp.route('/preview/<int:file_id>')
@login_required
def preview_file(file_id):
    file = File.query.get_or_404(file_id)
    if file.uploader_id != current_user.id:
        flash('You do not have permission to access this file.', 'error')
        return redirect(url_for('file_management.main_page'))
    return render_template('preview.html', file_id=file_id, filename=file.filename)

@file_bp.route('/preview_content/<int:file_id>')
@login_required
def preview_file_content(file_id):
    file = File.query.get_or_404(file_id)
    if file.uploader_id != current_user.id:
        return "You do not have permission to access this file.", 403

    try:
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        if file_extension in ['txt']:
            return file.data.decode('utf-8')
        elif file_extension in ['pdf']:
            return send_file(io.BytesIO(file.data), mimetype='application/pdf')
        elif file_extension in ['png', 'jpg', 'jpeg', 'gif']:
            return send_file(io.BytesIO(file.data), mimetype=f'image/{file_extension}')
        elif file_extension in ['mp4', 'avi', 'mkv']:
            return send_file(io.BytesIO(file.data), mimetype=f'video/{file_extension}')
        elif file_extension in ['mp3']:
            return send_file(io.BytesIO(file.data), mimetype='audio/mpeg')
        elif file_extension in ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}") as temp_input:
                temp_input.write(file.data)
                temp_input_path = temp_input.name

            temp_output_path = temp_input_path.rsplit('.', 1)[0] + ".pdf"
            current_app.logger.info(f"Input file path: {temp_input_path}")
            current_app.logger.info(f"Output file path: {temp_output_path}")

            try:
                result = subprocess.run(
                    [LIBREOFFICE_PATH, '--headless', '--convert-to', 'pdf', '--outdir',
                     os.path.dirname(temp_input_path), temp_input_path],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                current_app.logger.info(f"LibreOffice stdout: {result.stdout}")
                current_app.logger.info(f"LibreOffice stderr: {result.stderr}")
                current_app.logger.info(f"LibreOffice conversion succeeded")
            except subprocess.CalledProcessError as e:
                current_app.logger.error(f"LibreOffice conversion failed: {e.stderr}")
                os.remove(temp_input_path)
                return "Error converting file", 500

            if not os.path.exists(temp_output_path):
                current_app.logger.error(f"Converted file does not exist: {temp_output_path}")
                os.remove(temp_input_path)
                return "Error converting file", 500

            with open(temp_output_path, 'rb') as temp_output:
                pdf_content = temp_output.read()

            os.remove(temp_input_path)
            os.remove(temp_output_path)

            return send_file(io.BytesIO(pdf_content), mimetype='application/pdf')

        elif file_extension in ['zip', 'rar']:
            return jsonify({'message': 'Compressed files are not supported for preview. Please download.'})
        else:
            return "File type not supported for preview", 415
    except Exception as e:
        current_app.logger.error(f"Error reading file: {e}")
        return "Error reading file", 500

@file_bp.route('/serve_file_for_download/<int:file_id>')
@login_required
def serve_file_for_download(file_id):
    file = File.query.get_or_404(file_id)
    if file.uploader_id != current_user.id:
        return "You do not have permission to access this file.", 403

    file_extension = file.filename.rsplit('.', 1)[-1].lower()
    mimetypes = {
        'txt': 'text/plain',
        'pdf': 'application/pdf',
        'png': 'image/png',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'mp4': 'video/mp4',
        'avi': 'video/x-msvideo',
        'mkv': 'video/x-matroska',
        'mp3': 'audio/mpeg',
        'doc': 'application/msword',
        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'xls': 'application/vnd.ms-excel',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'ppt': 'application/vnd.ms-powerpoint',
        'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'zip': 'application/zip',
        'rar': 'application/vnd.rar'
    }

    mimetype = mimetypes.get(file_extension, 'application/octet-stream')

    if file.is_folder:
        temp_dir = tempfile.mkdtemp()
        zip_path = os.path.join(temp_dir, f"{file.filename}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            add_folder_to_zip(file, zipf, file.filename)
        return send_file(zip_path, as_attachment=True, download_name=f"{file.filename}.zip", mimetype='application/zip')

    if file_extension == 'rar':
        return send_file(io.BytesIO(file.data), download_name=file.filename, as_attachment=True, mimetype=mimetype)

    return send_file(io.BytesIO(file.data), download_name=file.filename, as_attachment=True, mimetype=mimetype)

@file_bp.route('/download', methods=['POST'])
@login_required
def download_files():
    data = request.get_json()
    file_ids = data.get('file_ids', [])
    if not file_ids:
        return jsonify({'success': False, 'message': 'No files selected for download'}), 400

    files = File.query.filter(File.id.in_(file_ids), File.uploader_id == current_user.id).all()
    if not files:
        return jsonify({'success': False, 'message': 'No files found or insufficient permissions'}), 404

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, "files.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in files:
            if file.is_folder:
                add_folder_to_zip(file, zipf, file.filename)
            else:
                zipf.writestr(file.filename, file.data)

    return send_file(zip_path, as_attachment=True, download_name="files.zip", mimetype='application/zip')

@file_bp.route('/get_folders', methods=['GET'])
@login_required
def get_folders():
    folders = File.query.filter_by(uploader_id=current_user.id, is_folder=True).all()
    folder_list = [{'id': folder.id, 'filename': folder.filename, 'is_favorite_folder': folder.is_favorite_folder} for folder in folders]
    return jsonify(folder_list)

@file_bp.route('/move', methods=['POST'])
@login_required
def move_files():
    data = request.get_json()
    file_ids = data.get('file_ids', [])
    target_folder_id = data.get('target_folder_id')

    current_app.logger.info(f'Received file_ids: {file_ids}')
    current_app.logger.info(f'Received target_folder_id: {target_folder_id}')

    if not file_ids:
        current_app.logger.error('No files selected for moving')
        return jsonify({'success': False, 'message': 'No files selected for moving'}), 400

    files = File.query.filter(File.id.in_(file_ids), File.uploader_id == current_user.id).all()
    if not files:
        current_app.logger.error('No files found or insufficient permissions')
        return jsonify({'success': False, 'message': 'No files found or insufficient permissions'}), 404

    for file in files:
        if file.is_folder:
            subfolder_ids = get_subfolder_ids(file.id)
            current_app.logger.info(f'Subfolder IDs for file {file.id}: {subfolder_ids}')
            if file.id == target_folder_id or target_folder_id in subfolder_ids:
                current_app.logger.error('Cannot move folder into itself or its subfolder')
                return jsonify({'success': False, 'message': 'Cannot move folder into itself or its subfolder'}), 400

    for file in files:
        current_app.logger.info(f'Moving file {file.filename} (ID: {file.id}) to folder ID: {target_folder_id}')
        if file.is_favorite_folder:
            favorite = Favorite.query.filter_by(file_id=file.id).first()
            if favorite:
                favorite.folder_id = target_folder_id
            else:
                new_favorite = Favorite(file_id=file.id, folder_id=target_folder_id)
                db.session.add(new_favorite)
        else:
            file.parent_id = target_folder_id if target_folder_id is not None else None
            db.session.add(file)

    db.session.commit()

    target_folder_name = None
    if target_folder_id:
        target_folder = File.query.get(target_folder_id)
        target_folder_name = target_folder.filename if target_folder else None

    current_app.logger.info(f'Files moved successfully to folder: {target_folder_name}')
    return jsonify({'success': True, 'message': 'Files moved successfully', 'target_folder_name': target_folder_name})

def get_subfolder_ids(folder_id):
    subfolder_ids = []
    subfolders = File.query.filter_by(parent_id=folder_id).all()
    for subfolder in subfolders:
        subfolder_ids.append(subfolder.id)
        subfolder_ids.extend(get_subfolder_ids(subfolder.id))
    return subfolder_ids

@file_bp.route('/get_subfolders/<int:folder_id>', methods=['GET'])
@login_required
def get_subfolders(folder_id):
    def fetch_subfolder_ids(folder_id):
        subfolder_ids = []
        subfolders = File.query.filter_by(parent_id=folder_id).all()
        for subfolder in subfolders:
            subfolder_ids.append(subfolder.id)
            subfolder_ids.extend(fetch_subfolder_ids(subfolder.id))
        return subfolder_ids

    folder = File.query.filter_by(id=folder_id, uploader_id=current_user.id).first()
    if not folder or not folder.is_folder:
        return jsonify({'success': False, 'message': '未找到文件夹或权限不足'}), 404

    subfolder_ids = fetch_subfolder_ids(folder.id)
    return jsonify({'success': True, 'subfolder_ids': subfolder_ids})

@file_bp.route('/export_directory', methods=['GET'])
@login_required
def export_directory():
    files = File.query.filter_by(uploader_id=current_user.id).all()
    file_structure = []

    for file in files:
        path = build_file_path(file)
        file_structure.append(f'{path} (ID: {file.id})')

    file_structure_str = "\n".join(file_structure)
    return send_file(io.BytesIO(file_structure_str.encode('utf-8')), download_name='file_structure.txt',
                     as_attachment=True)

def build_file_path(file):
    parent = file.parent_id
    if parent:
        parent_file = File.query.get(parent)
        return parent_file.filename if parent_file else '单独上传'
    return '单独上传'

@file_bp.route('/rename', methods=['POST'])
@login_required
def rename_file():
    data = request.get_json()
    file_id = data.get('file_id')
    new_name = data.get('new_name')

    if not file_id or not new_name:
        return jsonify({'success': False, 'message': '文件 ID 或新名称未提供'}), 400

    file = File.query.filter_by(id=file_id, uploader_id=current_user.id).first()
    if not file:
        return jsonify({'success': False, 'message': '未找到文件或权限不足'}), 404

    new_name = custom_secure_filename(new_name)

    # 获取原始文件名的扩展名
    original_ext = file.filename.rsplit('.', 1)[-1] if '.' in file.filename else ''
    # 获取新文件名的名称部分
    new_base_name = new_name.rsplit('.', 1)[0] if '.' in new_name else new_name
    # 生成最终的新文件名，保留原始扩展名
    final_new_name = f"{new_base_name}.{original_ext}" if original_ext else new_base_name

    existing_file = File.query.filter_by(filename=final_new_name, parent_id=file.parent_id, uploader_id=current_user.id).first()
    if existing_file:
        return jsonify({'success': False, 'message': '文件或文件夹同名已存在'}), 400

    file.filename = final_new_name
    db.session.commit()

    return jsonify({'success': True, 'message': '文件重命名成功', 'new_name': file.filename})

@file_bp.route('/create_favorite_folder', methods=['POST'])
@login_required
def create_favorite_folder():
    data = request.get_json()
    folder_name = data.get('folder_name')

    if not folder_name:
        return jsonify({'success': False, 'message': '未提供收藏夹名称'}), 400

    folder_name = custom_secure_filename(folder_name)

    existing_folder = File.query.filter_by(filename=folder_name, uploader_id=current_user.id, is_folder=True, parent_id=None, is_favorite_folder=True).first()
    if existing_folder:
        return jsonify({'success': False, 'message': '同名收藏夹已存在'}), 400

    new_folder = File(
        filename=folder_name,
        data=None,
        uploader_id=current_user.id,
        is_folder=True,
        parent_id=None,
        is_favorite_folder=True
    )

    db.session.add(new_folder)
    db.session.commit()

    return jsonify({'success': True, 'message': '收藏夹创建成功', 'folder_id': new_folder.id})

@file_bp.route('/add_to_favorites', methods=['POST'])
@login_required
def add_to_favorites():
    data = request.get_json()
    file_ids = data.get('file_ids')
    folder_id = data.get('folder_id')

    if not file_ids or not folder_id:
        current_app.logger.error('未提供文件ID或收藏夹ID')
        return jsonify({'success': False, 'message': '未提供文件ID或收藏夹ID'}), 400

    if not isinstance(file_ids, list):
        current_app.logger.error('文件ID应为列表')
        return jsonify({'success': False, 'message': '文件ID应为列表'}), 400

    folder = File.query.filter_by(id=folder_id, uploader_id=current_user.id, is_folder=True, is_favorite_folder=True).first()
    if not folder:
        current_app.logger.error('未找到收藏夹或权限不足')
        return jsonify({'success': False, 'message': '未找到收藏夹或权限不足'}), 404

    for file_id in file_ids:
        file = File.query.filter_by(id=file_id, uploader_id=current_user.id).first()
        if not file:
            current_app.logger.error(f'未找到文件 ID {file_id} 或权限不足')
            return jsonify({'success': False, 'message': f'未找到文件 ID {file_id} 或权限不足'}), 404

        favorite = Favorite.query.filter_by(file_id=file.id, folder_id=folder.id).first()
        if not favorite:
            new_favorite = Favorite(file_id=file.id, folder_id=folder.id)
            db.session.add(new_favorite)

    db.session.commit()

    current_app.logger.info(f'文件已添加到收藏夹: {file_ids} 到收藏夹 {folder_id}')
    return jsonify({'success': True, 'message': '文件已添加到收藏夹'})

@file_bp.route('/search_files', methods=['GET'])
@login_required
def search_files():
    filename_query = request.args.get('filename', '').strip()
    tags_query = request.args.get('tags', '').strip()

    filters = [File.is_favorite_folder == False]

    if filename_query:
        filters.append(File.filename.ilike(f"%{filename_query}%"))
    if tags_query:
        filters.append(File.tags.ilike(f"%{tags_query}%"))

    if not filters:
        return jsonify([])

    files = File.query.filter(db.and_(*filters), File.uploader_id == current_user.id).all()

    def build_file_dict(file):
        file_dict = {
            'id': file.id,
            'filename': file.filename,
            'is_folder': file.is_folder,
            'created_at': file.created_at,
            'tags': file.tags,
            'is_favorite': Favorite.query.filter_by(file_id=file.id).first() is not None,
            'source': build_file_path(file)
        }
        return file_dict

    return jsonify([build_file_dict(file) for file in files])

@file_bp.route('/remove_from_favorites', methods=['POST'])
@login_required
def remove_from_favorites():
    data = request.get_json()
    file_ids = data.get('file_ids', [])

    if not file_ids:
        return jsonify({'success': False, 'message': '未提供文件ID'}), 400

    for file_id in file_ids:
        favorite = Favorite.query.filter_by(file_id=file_id).first()
        if favorite:
            db.session.delete(favorite)

    db.session.commit()
    return jsonify({'success': True, 'message': '文件已移出收藏夹'})

@file_bp.route('/delete_favorite_folder_and_contents', methods=['POST'])
@login_required
def delete_favorite_folder_and_contents():
    data = request.get_json()
    folder_id = data.get('folder_id')

    if not folder_id:
        return jsonify({'success': False, 'message': '未提供收藏夹ID'}), 400

    folder = File.query.filter_by(id=folder_id, uploader_id=current_user.id, is_folder=True, is_favorite_folder=True).first()
    if not folder:
        return jsonify({'success': False, 'message': '未找到收藏夹或权限不足'}), 404

    def delete_folder_and_contents(folder):
        sub_files = File.query.filter_by(parent_id=folder.id).all()
        for sub_file in sub_files:
            delete_folder_and_contents(sub_file)
        favorites = Favorite.query.filter_by(file_id=folder.id).all()
        for favorite in favorites:
            db.session.delete(favorite)
        db.session.delete(folder)

    delete_folder_and_contents(folder)
    db.session.commit()

    return jsonify({'success': True, 'message': '收藏夹及其内容删除成功'})