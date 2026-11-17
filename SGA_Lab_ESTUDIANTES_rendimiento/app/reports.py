from flask import Blueprint,render_template
from .db import get_db
from .utils import roles
bp=Blueprint('reports',__name__)
@bp.route('/')
@roles('admin','teacher')
def index():
 db=get_db();q=lambda s:db.execute(s).fetchone()['n'];return render_template('reports.html',students=q("SELECT COUNT(*) n FROM users WHERE role='student'"),courses=q('SELECT COUNT(*) n FROM courses'),enrollments=q('SELECT COUNT(*) n FROM enrollments'),grades=q('SELECT COUNT(*) n FROM grades'))
