from flask import Flask
from pathlib import Path
from .config import Config
from .db import init_db
def create_app():
    app=Flask(__name__); app.config.from_object(Config); Path(app.instance_path).mkdir(exist_ok=True)
    init_db(app)
    from .main import bp as main; from .auth import bp as auth; from .courses import bp as courses; from .enrollments import bp as enrollments; from .grades import bp as grades; from .reports import bp as reports
    app.register_blueprint(main); app.register_blueprint(auth,url_prefix='/auth'); app.register_blueprint(courses,url_prefix='/courses'); app.register_blueprint(enrollments,url_prefix='/enrollments'); app.register_blueprint(grades,url_prefix='/grades'); app.register_blueprint(reports,url_prefix='/reports')
    return app
