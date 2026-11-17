import sqlite3
from flask import current_app
from werkzeug.security import generate_password_hash
SCHEMA='''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,document TEXT UNIQUE NOT NULL,first_name TEXT NOT NULL,last_name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,phone TEXT,password_hash TEXT NOT NULL,role TEXT NOT NULL,active INTEGER DEFAULT 1,failed_attempts INTEGER DEFAULT 0,locked_until TEXT);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY AUTOINCREMENT,code TEXT NOT NULL,name TEXT NOT NULL,description TEXT,teacher_id INTEGER NOT NULL,schedule TEXT NOT NULL,max_quota INTEGER NOT NULL,enrolled_count INTEGER DEFAULT 0,status TEXT DEFAULT 'active',FOREIGN KEY(teacher_id) REFERENCES users(id));
CREATE TABLE IF NOT EXISTS enrollments(id INTEGER PRIMARY KEY AUTOINCREMENT,student_id INTEGER NOT NULL,course_id INTEGER NOT NULL,created_at TEXT DEFAULT CURRENT_TIMESTAMP,FOREIGN KEY(student_id) REFERENCES users(id),FOREIGN KEY(course_id) REFERENCES courses(id));
CREATE TABLE IF NOT EXISTS grades(id INTEGER PRIMARY KEY AUTOINCREMENT,enrollment_id INTEGER NOT NULL,grade1 REAL NOT NULL,grade2 REAL NOT NULL,grade3 REAL NOT NULL,final_grade REAL,FOREIGN KEY(enrollment_id) REFERENCES enrollments(id));'''
def get_db():
    db=sqlite3.connect(current_app.config['DATABASE']); db.row_factory=sqlite3.Row; return db
def init_db(app):
    with app.app_context():
        db=get_db(); db.executescript(SCHEMA)
        if db.execute('SELECT COUNT(*) n FROM users').fetchone()['n']==0: seed(db)
        db.commit(); db.close()
def seed(db):
    users=[('1001','Administrador','SGA','admin@sga.local','3000000001',generate_password_hash('Admin123!'),'admin'),('2001','Maria','Docente','docente@sga.local','3000000002',generate_password_hash('Docente123!'),'teacher'),('3001','Carlos','Estudiante','estudiante@sga.local','3000000003',generate_password_hash('Estudiante123!'),'student'),('3002','Laura','Estudiante','laura@sga.local','3000000004',generate_password_hash('Laura123!'),'student')]
    db.executemany('INSERT INTO users(document,first_name,last_name,email,phone,password_hash,role) VALUES(?,?,?,?,?,?,?)',users)
    tid=db.execute("SELECT id FROM users WHERE email='docente@sga.local'").fetchone()['id']
    courses=[('ING101','Ingenieria de Software I','Fundamentos',tid,'Lunes 18:00-20:00',30,'active'),('CAL201','Calidad del Software II','Pruebas y calidad',tid,'Miercoles 18:00-20:00',7,'active'),('SEC201','Seguridad Informatica','Controles y pruebas',tid,'Viernes 18:00-20:00',20,'active'),('OLD001','Curso Inactivo','Curso de prueba',tid,'Martes 16:00-18:00',10,'inactive')]
    db.executemany('INSERT INTO courses(code,name,description,teacher_id,schedule,max_quota,status) VALUES(?,?,?,?,?,?,?)',courses)
