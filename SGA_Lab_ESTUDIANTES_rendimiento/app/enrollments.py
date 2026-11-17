from flask import Blueprint,render_template,request,redirect,url_for,flash
from .db import get_db
from .utils import login_required,user
bp=Blueprint('enrollments',__name__)
@bp.route('/my')
@login_required
def mine():
    rows=get_db().execute("SELECT e.*,c.code,c.name,c.schedule,g.grade1,g.grade2,g.grade3,g.final_grade FROM enrollments e JOIN courses c ON c.id=e.course_id LEFT JOIN grades g ON g.enrollment_id=e.id WHERE e.student_id=? ORDER BY e.created_at DESC",(user()['id'],)).fetchall();return render_template('enrollments.html',rows=rows)
@bp.route('/enroll/<int:cid>',methods=['POST'])
@login_required
def enroll(cid):
    db=get_db();u=user();c=db.execute('SELECT * FROM courses WHERE id=?',(cid,)).fetchone()
    if not c:flash('Curso no encontrado.');return redirect(url_for('courses.index'))
    if c['status']!='active':flash('El curso no esta disponible.');return redirect(url_for('courses.index'))  # DEF-05
    if c['enrolled_count']>=c['max_quota']:flash('Sin cupos.');return redirect(url_for('courses.index'))
    if db.execute('SELECT id FROM enrollments WHERE student_id=? AND course_id=?',(u['id'],cid)).fetchone():flash('Ya matriculado.');return redirect(url_for('courses.index'))
    # DEF-15: reserva ATOMICA del cupo. El UPDATE condicional bloquea la escritura y solo avanza si aun hay cupo,
    # por lo que dos solicitudes simultaneas ya no pueden pasar ambas la verificacion de cupo.
    cur=db.execute("UPDATE courses SET enrolled_count=enrolled_count+1 WHERE id=? AND status='active' AND enrolled_count<max_quota",(cid,))
    if cur.rowcount==0:db.rollback();flash('Sin cupos.');return redirect(url_for('courses.index'))
    if db.execute('SELECT id FROM enrollments WHERE student_id=? AND course_id=?',(u['id'],cid)).fetchone():db.rollback();flash('Ya matriculado.');return redirect(url_for('courses.index'))
    db.execute('INSERT INTO enrollments(student_id,course_id) VALUES(?,?)',(u['id'],cid));db.commit()  # DEF-04 / DEF-15
    flash('Matricula registrada.');return redirect(url_for('enrollments.mine'))
