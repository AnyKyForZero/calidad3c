from flask import Blueprint,render_template,request,redirect,url_for,flash
from .db import get_db
from .utils import roles,user
bp=Blueprint('grades',__name__)
@bp.route('/')
@roles('teacher','admin')
def index():
    u=user();sql="SELECT e.id,u.first_name||' '||u.last_name student,c.code,g.grade1,g.grade2,g.grade3,g.final_grade FROM enrollments e JOIN users u ON u.id=e.student_id JOIN courses c ON c.id=e.course_id LEFT JOIN grades g ON g.enrollment_id=e.id"
    args=()
    if u['role']=='teacher':sql+=' WHERE c.teacher_id=?';args=(u['id'],)  # DEF-13
    rows=get_db().execute(sql+' ORDER BY c.code,student',args).fetchall();return render_template('grades.html',rows=rows)
@bp.route('/save/<int:eid>',methods=['POST'])
@roles('teacher','admin')
def save(eid):
    db=get_db();u=user()
    info=db.execute('SELECT c.teacher_id FROM enrollments e JOIN courses c ON c.id=e.course_id WHERE e.id=?',(eid,)).fetchone()
    if not info:flash('Matricula no encontrada.');return redirect(url_for('grades.index'))
    if u['role']=='teacher' and info['teacher_id']!=u['id']:flash('No puede calificar cursos de otro docente.');return redirect(url_for('grades.index'))  # DEF-13
    try:vals=[float(request.form[f'grade{i}']) for i in range(1,4)]
    except (KeyError,ValueError):flash('Las notas deben ser numericas.');return redirect(url_for('grades.index'))  # DEF-09
    if not all(0<=v<=5 for v in vals):flash('Las notas deben estar entre 0.0 y 5.0.');return redirect(url_for('grades.index'))  # DEF-03
    final=sum(vals)/3  # DEF-02
    ex=db.execute('SELECT id FROM grades WHERE enrollment_id=?',(eid,)).fetchone()
    if ex:db.execute('UPDATE grades SET grade1=?,grade2=?,grade3=?,final_grade=? WHERE enrollment_id=?',(*vals,final,eid))
    else:db.execute('INSERT INTO grades(enrollment_id,grade1,grade2,grade3,final_grade) VALUES(?,?,?,?,?)',(eid,*vals,final))  # DEF-06
    db.commit();flash('Notas guardadas.');return redirect(url_for('grades.index'))
