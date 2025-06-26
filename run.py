import os
import sys
import logging
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
    # Check for Supabase URL
    supabase_url = os.getenv('SUPABASE_URL')
    if not supabase_url:
        logger.error("Missing SUPABASE_URL environment variable")
        return False
    
    # Check for Supabase key (support multiple variable names) - FIXED
    supabase_key = (
        os.getenv('SUPABASE_ANON_KEY') or 
        os.getenv('SUPABASE_KEY') or 
        os.getenv('SUPABASE_ROLE_SERVICE') or
        os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    )
    if not supabase_key:
        logger.error("Missing Supabase key environment variable")
        return False
    
    logger.info("All required environment variables are present")
    return True

# Validate environment on startup
try:
    env_valid = validate_environment()
    if not env_valid:
        logger.error("❌ Environment validation failed")
    
    # Import and use the create_app function from __init__.py
    from app import create_app
    app = create_app()
    logger.info("✅ Flask application created successfully using create_app()")
    
except Exception as e:
    logger.error(f"❌ Critical error during app creation: {e}", exc_info=True)
    # Create minimal fallback app for debugging
    from flask import Flask, jsonify
    from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app, origins=['*'])
    
    @app.route('/')
    def fallback_root():
        return jsonify({
            'error': 'App creation failed',
            'message': str(e),
            'status': 'critical_error'
        }), 500
    
    @app.route('/api/health')
    def fallback_health():
        return jsonify({
            'status': 'critical_error',
            'error': str(e),
            'message': 'Application failed to initialize properly'
        }), 500

# For Vercel deployment
application = app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)