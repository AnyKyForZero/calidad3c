from functools import wraps
from flask import session,redirect,url_for,flash,g
from .db import get_db
def user():
    if 'user_id' not in session:return None
    if not hasattr(g,'u'):g.u=get_db().execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    return g.u
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not user(): flash('Debe iniciar sesion.'); return redirect(url_for('auth.login'))
        return f(*a,**k)
    return w
def roles(*rs):
    def d(f):
        @wraps(f)
        def w(*a,**k):
            u=user()
            if not u:return redirect(url_for('auth.login'))
            if u['role'] not in rs:flash('Sin permisos.');return redirect(url_for('main.index'))
            return f(*a,**k)
        return w
    return d
