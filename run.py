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
    issues = []
    
    # Check for Supabase URL
    supabase_url = os.getenv('SUPABASE_URL')
    if not supabase_url:
        issues.append("Missing SUPABASE_URL environment variable")
    elif not supabase_url.startswith('https://'):
        issues.append(f"Invalid SUPABASE_URL format: {supabase_url}")
    
    # Check for Supabase key (support multiple variable names)
    supabase_key = (
        os.getenv('SUPABASE_ANON_KEY') or 
        os.getenv('SUPABASE_KEY') or 
        os.getenv('SUPABASE_ROLE_SERVICE') or
        os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    )
    if not supabase_key:
        issues.append("Missing Supabase key environment variable")
    
    # Check SECRET_KEY
    secret_key = os.getenv('SECRET_KEY')
    if not secret_key:
        issues.append("Missing SECRET_KEY environment variable")
    
    if issues:
        for issue in issues:
            logger.error(issue)
        return False
    
    logger.info("✅ All required environment variables are present and valid")
    return True

# Diagnostic version with step-by-step imports
try:
    logger.info("🔍 DIAGNOSTIC MODE: Starting step-by-step import testing...")
    
    # Step 1: Validate environment
    logger.info("Step 1: Validating environment variables...")
    env_valid = validate_environment()
    if not env_valid:
        logger.error("❌ Environment validation failed")
    
    # Step 2: Test basic Flask import
    logger.info("Step 2: Testing basic Flask import...")
    from flask import Flask, jsonify
    from flask_cors import CORS
    logger.info("✅ Basic Flask imports successful")
    
    # Step 3: Test Supabase import
    logger.info("Step 3: Testing Supabase import...")
    from supabase import create_client
    logger.info("✅ Supabase import successful")
    
    # Step 4: Test Supabase client creation
    logger.info("Step 4: Testing Supabase client creation...")
    if env_valid:
        test_url = os.getenv('SUPABASE_URL')
        test_key = (
            os.getenv('SUPABASE_ANON_KEY') or 
            os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        )
        test_client = create_client(test_url, test_key)
        logger.info("✅ Supabase client creation successful")
    
    # Step 5: Import the app creation function
    logger.info("Step 5: Testing app module import...")
    from app import create_app
    logger.info("✅ App module import successful")
    
    # Step 6: Create the app
    logger.info("Step 6: Creating Flask application...")
    app = create_app()
    logger.info("✅ Flask application created successfully using create_app()")
    
except ImportError as e:
    logger.error(f"❌ IMPORT ERROR: {e}", exc_info=True)
    # Create minimal fallback app for debugging
    from flask import Flask, jsonify
    from flask_cors import CORS
    
    app = Flask(__name__)
    CORS(app, origins=['*'])
    
    @app.route('/')
    def fallback_root():
        return jsonify({
            'error': 'Import Error',
            'message': f'Failed to import required modules: {str(e)}',
            'status': 'import_error',
            'type': 'ImportError'
        }), 500
    
    @app.route('/api/health')
    def fallback_health():
        return jsonify({
            'status': 'import_error',
            'error': str(e),
            'message': 'Application failed to import required modules'
        }), 500

except Exception as e:
    logger.error(f"❌ CRITICAL ERROR during app creation: {e}", exc_info=True)
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
            'status': 'critical_error',
            'type': type(e).__name__
        }), 500
    
    @app.route('/api/health')
    def fallback_health():
        return jsonify({
            'status': 'critical_error',
            'error': str(e),
            'message': 'Application failed to initialize properly',
            'type': type(e).__name__
        }), 500

# For Vercel deployment
application = app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)