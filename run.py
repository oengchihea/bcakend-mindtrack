import os
import sys
import logging
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_environment():
    """Validate required environment variables"""
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_ANON_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        return False
    
    logger.info("All required environment variables are present")
    return True

def create_application():
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Enable CORS for all domains and routes
    CORS(app, 
         origins=['*'], 
         methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
         allow_headers=['Content-Type', 'Authorization'])
    
    # App configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret-key')
    app.config['SUPABASE_URL'] = os.getenv('SUPABASE_URL')
    app.config['SUPABASE_ANON_KEY'] = os.getenv('SUPABASE_ANON_KEY')
    app.config['SUPABASE_SERVICE_ROLE_KEY'] = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    # Initialize Supabase client globally
    try:
        from supabase import create_client
        supabase_url = app.config['SUPABASE_URL']
        supabase_key = app.config['SUPABASE_ANON_KEY']
        
        if supabase_url and supabase_key:
            app.supabase = create_client(supabase_url, supabase_key)
            logger.info("✅ Supabase client initialized")
        else:
            app.supabase = None
            logger.error("❌ Missing Supabase configuration")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Supabase: {e}")
        app.supabase = None
    
    # Register blueprints with error handling
    try:
        from app.routes.auth import auth_bp
        from app.routes.mood import mood_bp
        from app.routes.journal import journal_bp
        from app.routes.user import user_bp
        from app.routes.posts import posts_bp
        from app.routes.analyze_journal import analyze_bp
        from app.routes.journal_prompt import journal_prompt_bp
        from app.routes.events import events_bp
        from app.routes.main import main_bp
        
        # Register with /api prefix
        app.register_blueprint(auth_bp, url_prefix='/api')
        app.register_blueprint(mood_bp, url_prefix='/api')
        app.register_blueprint(journal_bp, url_prefix='/api')
        app.register_blueprint(user_bp, url_prefix='/api')
        app.register_blueprint(posts_bp, url_prefix='/api')
        app.register_blueprint(analyze_bp, url_prefix='/api')
        app.register_blueprint(journal_prompt_bp, url_prefix='/api')
        app.register_blueprint(events_bp, url_prefix='/api')
        app.register_blueprint(main_bp, url_prefix='/api')
        
        logger.info("✅ All blueprints registered successfully")
        
    except ImportError as e:
        logger.error(f"❌ Failed to import blueprints: {e}")
        # Create fallback routes if blueprints fail
        create_fallback_routes(app)
    
    # Root route
    @app.route('/')
    def root():
        return jsonify({
            'message': 'MindTrack Backend API',
            'status': 'running',
            'version': '1.0.0',
            'supabase_connected': app.supabase is not None,
            'endpoints': {
                'health': '/api/health',
                'login': '/api/login',
                'signup': '/api/signup'
            }
        }), 200
    
    # Health check
    @app.route('/api/health', methods=['GET'])
    def health_check():
        env_valid = validate_environment()
        return jsonify({
            'status': 'healthy' if env_valid else 'unhealthy',
            'message': 'MindTrack Backend is running',
            'environment_valid': env_valid,
            'supabase_connected': app.supabase is not None,
            'environment': 'production' if os.getenv('VERCEL_ENV') == 'production' else 'development',
            'blueprints_loaded': len(app.blueprints) > 0
        }), 200 if env_valid else 503
    
    # Global error handler
    @app.errorhandler(Exception)
    def handle_exception(e):
        logger.error(f"Unhandled exception: {e}")
        return jsonify({
            'error': 'Internal server error',
            'message': str(e),
            'type': type(e).__name__
        }), 500
    
    return app

def create_fallback_routes(app):
    """Create fallback routes if blueprints fail to load"""
    logger.info("Creating fallback routes...")
    
    @app.route('/api/login', methods=['POST'])
    def fallback_login():
        return jsonify({
            'success': False,
            'error': 'Blueprint loading failed',
            'message': 'Backend routes are not properly configured'
        }), 500
    
    @app.route('/api/signup', methods=['POST'])
    def fallback_signup():
        return jsonify({
            'success': False,
            'error': 'Blueprint loading failed',
            'message': 'Backend routes are not properly configured'
        }), 500

# Validate environment on startup
env_valid = validate_environment()
if not env_valid:
    logger.error("❌ Environment validation failed")

app = create_application()

# For Vercel deployment
application = app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)