from app import create_app
from dotenv import load_dotenv
import os
import sys
import logging

# Configure logging for better debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def validate_environment():
    """Validate required environment variables and provide detailed feedback"""
    logger.info("🔍 Validating environment variables...")
    
    required_vars = {
        'SUPABASE_URL': os.getenv('SUPABASE_URL'),
        'SUPABASE_KEY': os.getenv('SUPABASE_KEY'),
    }
    
    optional_vars = {
        'SUPABASE_ANON_KEY': os.getenv('SUPABASE_ANON_KEY'),
        'SUPABASE_SERVICE_ROLE_KEY': os.getenv('SUPABASE_SERVICE_ROLE_KEY'),
        'SECRET_KEY': os.getenv('SECRET_KEY'),
        'FLASK_ENV': os.getenv('FLASK_ENV'),
        'VERCEL_ENV': os.getenv('VERCEL_ENV'),
    }
    
    # Check required variables
    missing_required = []
    for var_name, var_value in required_vars.items():
        if var_value:
            if var_name == 'SUPABASE_URL':
                logger.info(f"✅ {var_name}: {var_value}")
            else:
                logger.info(f"✅ {var_name}: {'*' * 10}...{var_value[-4:] if len(var_value) > 4 else '****'}")
        else:
            logger.error(f"❌ {var_name}: NOT SET")
            missing_required.append(var_name)
    
    # Check optional variables
    for var_name, var_value in optional_vars.items():
        if var_value:
            if 'KEY' in var_name or 'SECRET' in var_name:
                logger.info(f"ℹ️ {var_name}: {'*' * 10}...{var_value[-4:] if len(var_value) > 4 else '****'}")
            else:
                logger.info(f"ℹ️ {var_name}: {var_value}")
        else:
            logger.warning(f"⚠️ {var_name}: NOT SET (optional)")
    
    if missing_required:
        logger.error("🚨 CRITICAL: Missing required environment variables!")
        logger.error("To fix this in Vercel:")
        logger.error("1. Go to your Vercel project dashboard")
        logger.error("2. Navigate to Settings → Environment Variables")
        logger.error("3. Add the missing variables:")
        for var in missing_required:
            if var == 'SUPABASE_URL':
                logger.error(f"   - {var}: https://your-project.supabase.co")
            elif var == 'SUPABASE_KEY':
                logger.error(f"   - {var}: your_supabase_anon_key")
        logger.error("4. Redeploy your application")
        return False
    
    logger.info("✅ All required environment variables are set")
    return True

def create_application():
    """Create Flask application with comprehensive error handling"""
    try:
        logger.info("🚀 Starting MindTrack Backend...")
        
        # Validate environment before creating app
        if not validate_environment():
            logger.error("❌ Environment validation failed")
            # Still try to create app for better error reporting
        
        logger.info("🔧 Creating Flask application...")
        app = create_app()
        
        logger.info("✅ Flask application created successfully")
        
        # Test Supabase connection if available
        if hasattr(app, 'supabase') and app.supabase:
            logger.info("✅ Supabase client is available")
        else:
            logger.warning("⚠️ Supabase client is NOT available - some features will be disabled")
        
        return app
        
    except Exception as e:
        logger.error(f"❌ Failed to create Flask application: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        
        # Import traceback for detailed error info
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        
        # Create a minimal app for error reporting
        from flask import Flask, jsonify
        error_app = Flask(__name__)
        
        @error_app.route('/')
        @error_app.route('/api/health')
        def error_handler():
            return jsonify({
                'error': 'Application failed to initialize',
                'details': str(e),
                'type': type(e).__name__,
                'status': 'failed',
                'message': 'Check server logs for detailed error information'
            }), 500
        
        return error_app

# Create the Flask app using the factory pattern
logger.info("🔄 Initializing MindTrack Backend Application...")
app = create_application()

# Add a test route for Vercel deployment verification
@app.route('/api/vercel-test')
def vercel_test():
    """Test endpoint specifically for Vercel deployment verification"""
    return {
        'status': 'ok',
        'message': 'Vercel deployment is working',
        'environment': os.environ.get('VERCEL_ENV', 'not_vercel'),
        'python_version': sys.version,
        'app_created': True,
        'timestamp': logging.Formatter().formatTime(logging.LogRecord('', 0, '', 0, '', (), None))
    }

if __name__ == '__main__':
    logger.info("🏃 Running Flask app in development mode...")
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    logger.info("🌐 Flask app ready for production (Vercel)...")

logger.info("🎯 MindTrack Backend initialization complete")