from flask import Flask
from flask_cors import CORS
from supabase import create_client
import os

def create_app():
    app = Flask(__name__)
    
    # Configure app
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'fallback-secret-key'),
        SUPABASE_URL=os.environ.get('SUPABASE_URL'),
        SUPABASE_KEY=os.environ.get('SUPABASE_KEY'),
        SUPABASE_SERVICE_ROLE_KEY=os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    )
    
    # Validate required environment variables
    if not app.config['SUPABASE_URL'] or not app.config['SUPABASE_KEY']:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    # Initialize Supabase client
    app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
    
    # Enable CORS
    CORS(app)
    
    # Register blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.user import user_bp
    from app.routes.mood import mood_bp
    from app.routes.posts import posts_bp  # Add this import
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(mood_bp)
    app.register_blueprint(posts_bp)  # Add this registration
    
    # Log warning if service role key is missing
    if not app.config['SUPABASE_SERVICE_ROLE_KEY']:
        app.logger.warning("SUPABASE_SERVICE_ROLE_KEY not set. Storage operations may fail due to RLS policies.")
    
    return app