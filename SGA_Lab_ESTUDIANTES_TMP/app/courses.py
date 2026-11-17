from flask import Blueprint,render_template,request,redirect,url_for,flash
from .db import get_db
from .utils import roles
bp=Blueprint('courses',__name__)
@bp.route('/')
def index():
    rows=get_db().execute("SELECT c.*,u.first_name||' '||u.last_name teacher_name FROM courses c JOIN users u ON u.id=c.teacher_id ORDER BY c.name").fetchall();return render_template('courses.html',courses=rows)
@bp.route('/new',methods=['GET','POST'])
@roles('admin')
def new():
    if request.method=='POST':
        db=get_db()
        try:
            t=db.execute('SELECT id FROM users WHERE email=?',(request.form['teacher_email'],)).fetchone()
            if not t:raise ValueError('Docente no encontrado')
            db.execute('INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES(?,?,?,?,?,?,?)',(request.form['code'],request.form['name'],request.form['description'],t['id'],request.form['schedule'],int(request.form['max_quota']),request.form['status']));db.commit();flash('Curso creado.');return redirect(url_for('courses.index'))
        except Exception as ex:flash(str(ex))
    return render_template('course_form.html')
