from flask import Blueprint,render_template
from .utils import user
bp=Blueprint('main',__name__)
@bp.route('/')
def index():return render_template('index.html',user=user())
