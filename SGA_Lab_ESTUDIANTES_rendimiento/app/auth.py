import re,sqlite3
from datetime import datetime,timedelta
from flask import Blueprint,render_template,request,redirect,url_for,flash,session
from werkzeug.security import check_password_hash,generate_password_hash
from .db import get_db
from .utils import user
bp=Blueprint('auth',__name__)
def valid_email(e): return re.fullmatch(r'[^@\s]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+',e) is not None  # DEF-01
@bp.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        e=request.form['email'].strip().lower(); p=request.form['password']; db=get_db(); u=db.execute('SELECT * FROM users WHERE email=?',(e,)).fetchone()
        if not u:flash('Credenciales invalidas.');return render_template('login.html')
        if u['locked_until']:
            try:
                if datetime.fromisoformat(u['locked_until'])>datetime.now():flash('Cuenta bloqueada.');return render_template('login.html')
            except ValueError:pass
        if check_password_hash(u['password_hash'],p):db.execute('UPDATE users SET failed_attempts=0,locked_until=NULL WHERE id=?',(u['id'],));db.commit();session['user_id']=u['id'];return redirect(url_for('main.index'))
        n=u['failed_attempts']+1; lock=(datetime.now()+timedelta(minutes=5)).isoformat() if n>=5 else None;db.execute('UPDATE users SET failed_attempts=?,locked_until=? WHERE id=?',(n,lock,u['id']));db.commit();flash('Credenciales invalidas.')
    return render_template('login.html')
@bp.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        d={k:request.form.get(k,'').strip() for k in ['document','first_name','last_name','email','phone','password']}
        d['email']=d['email'].lower()  # DEF-07
        if not valid_email(d['email']):flash('Correo invalido.');return render_template('register.html')
        try:
            db=get_db();db.execute('INSERT INTO users(document,first_name,last_name,email,phone,password_hash,role) VALUES(?,?,?,?,?,?,?)',(d['document'],d['first_name'],d['last_name'],d['email'],d['phone'],generate_password_hash(d['password']),'student'));db.commit();flash('Registro exitoso.');return redirect(url_for('auth.login'))
        except sqlite3.IntegrityError:flash('El correo o el documento ya esta registrado.')  # DEF-08
        except Exception:flash('No fue posible completar el registro.')
    return render_template('register.html')
@bp.route('/logout')
def logout():
    session.pop('user_id',None);return redirect(url_for('main.index'))
@bp.app_context_processor
def inject():return {'current_user':user()}
