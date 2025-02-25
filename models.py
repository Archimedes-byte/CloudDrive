from datetime import datetime
from extensions import db
from flask_login import UserMixin

class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    data = db.Column(db.LargeBinary, nullable=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    tags = db.Column(db.String(255), nullable=True)
    is_folder = db.Column(db.Boolean, default=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('files.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_favorite_folder = db.Column(db.Boolean, default=False)

    parent = db.relationship('File', remote_side=[id], backref='children')

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'uploader_id': self.uploader_id,
            'category': self.category,
            'tags': self.tags,
            'is_folder': self.is_folder,
            'parent_id': self.parent_id,
            'created_at': self.created_at.isoformat() + 'Z',
            'updated_at': self.updated_at.isoformat() + 'Z',
            'is_favorite_folder': self.is_favorite_folder
        }


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    files = db.relationship('File', backref='uploader', lazy=True)

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey('files.id'), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('files.id'), nullable=False)

    file = db.relationship('File', foreign_keys=[file_id], backref=db.backref('favorites', cascade='all, delete-orphan'))
    folder = db.relationship('File', foreign_keys=[folder_id], backref=db.backref('favorite_folders', cascade='all, delete-orphan'))
