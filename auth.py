from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models import User, File

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

def create_default_favorite_folder(user_id):
    default_folder = File.query.filter_by(uploader_id=user_id, is_favorite_folder=True, parent_id=None).first()
    if not default_folder:
        new_folder = File(
            filename='默认收藏夹',
            data=None,
            uploader_id=user_id,
            is_folder=True,
            parent_id=None,
            is_favorite_folder=True
        )
        db.session.add(new_folder)
        db.session.commit()

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error='Username already exists')

        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        # 创建默认收藏夹
        create_default_favorite_folder(new_user.id)

        return render_template('register.html', success='Registration successful! You can now log in.')

    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)

            # 创建默认收藏夹
            create_default_favorite_folder(user.id)

            return redirect(url_for('file_management.main_page'))
        else:
            return render_template('login.html', error='Invalid username or password')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return render_template('login.html', success='You have been logged out.')
