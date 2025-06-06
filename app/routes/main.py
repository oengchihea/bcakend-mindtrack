# app/routes/main.py
from flask import Blueprint

# Create the Blueprint instance
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    return "Welcome to mindtrack api"  # Or render_template('index.html')