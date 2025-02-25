from flask import Flask, render_template
from config import Config
from extensions import db, login_manager, migrate

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)  
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    from models import User
    from auth import auth_bp
    from file_management import file_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(file_bp, url_prefix='/file_management')

    @login_manager.user_loader
    def load_user(user_id):
        return  db.session.get(User, int(user_id))

    @app.errorhandler(404)
    def page_not_found(e):
        return '404 Error: Page not found. Please check the URL.', 404

    @app.route('/')
    def index():
        return render_template('index.html')

    with app.app_context():
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
