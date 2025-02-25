import logging
from app import create_app
from extensions import db


def clear_database():
    app = create_app()

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    with app.app_context():
        try:
            db.drop_all()
            db.create_all()
            db.session.commit()
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            db.session.rollback()
