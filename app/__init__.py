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

    try:
        app.supabase_client = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
    except Exception as e:
        raise ValueError(f"Failed to initialize Supabase client: {e}") from e

    CORS(app, resources={r"/api/*": {"origins": "*"}}) # Keep this for overall API CORS

    # Import blueprints
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp      # Routes like /api/login are defined within this BP
    from app.routes.user import user_bp      # Routes like /api/user/profile are defined within this BP
    from app.routes.journal import journal_bp as journal_routes_bp # Assumes routes like /mood (needs /api prefix)
    from app.routes.mood import mood_bp      # Assumes routes like /mood-entries (needs /api prefix)

    # Register Blueprints
    app.register_blueprint(main_bp) # For root routes, no /api prefix

    # For auth_bp and user_bp, since their routes already include /api/,
    # do NOT add url_prefix='/api' here.
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)

    # For journal_routes_bp and mood_bp, assuming their internal routes
    # do NOT start with /api/ (e.g., @journal_bp.route('/mood', ...)),
    # they DO need the url_prefix.
    app.register_blueprint(journal_routes_bp, url_prefix='/api')
    app.register_blueprint(mood_bp, url_prefix='/api')

    return app