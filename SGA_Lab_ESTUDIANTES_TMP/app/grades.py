from flask import Blueprint,render_template,request,redirect,url_for,flash
from .db import get_db
from .utils import roles
bp=Blueprint('grades',__name__)
@bp.route('/')
@roles('teacher','admin')
def index():
    rows=get_db().execute("SELECT e.id,u.first_name||' '||u.last_name student,c.code,g.grade1,g.grade2,g.grade3,g.final_grade FROM enrollments e JOIN users u ON u.id=e.student_id JOIN courses c ON c.id=e.course_id LEFT JOIN grades g ON g.enrollment_id=e.id ORDER BY c.code,student").fetchall();return render_template('grades.html',rows=rows)
@bp.route('/save/<int:eid>',methods=['POST'])
@roles('teacher','admin')
def save(eid):
    vals=[float(request.form[f'grade{i}']) for i in range(1,4)]; final=sum(vals)/2 # INTENCIONAL: divisor incorrecto
    db=get_db();ex=db.execute('SELECT id FROM grades WHERE enrollment_id=?',(eid,)).fetchone()
    if ex:db.execute('UPDATE grades SET grade1=?,grade2=?,grade3=?,final_grade=? WHERE enrollment_id=?',(*vals,final,eid))
    else:db.execute('INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,?,?,?,?)',(*vals,final))
    db.commit();flash('Notas guardadas.');return redirect(url_for('grades.index'))
