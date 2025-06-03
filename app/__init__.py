from flask import Flask
from flask_cors import CORS
from supabase import create_client
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-secret-key')
    app.config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL')
    app.config['SUPABASE_KEY'] = os.environ.get('SUPABASE_KEY')
    
    if not app.config['SUPABASE_URL'] or not app.config['SUPABASE_KEY']:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
    CORS(app)
    
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.user import user_bp
    from app.routes.mood import mood_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(mood_bp)
    
    return app