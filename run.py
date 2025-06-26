from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import sys
import logging
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging for better debugging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

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
    """Create Flask application with direct routes (simplified structure)"""
    try:
        logger.info("🚀 Starting MindTrack Backend...")
        
        # Validate environment before creating app
        validate_environment()
        
        logger.info("🔧 Creating Flask application...")
        
        # Create Flask app directly
        app = Flask(__name__)
        CORS(app)
        
        # Initialize Supabase client
        SUPABASE_URL = os.environ.get('SUPABASE_URL')
        SUPABASE_KEY = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_ANON_KEY')
        
        supabase = None
        if SUPABASE_URL and SUPABASE_KEY:
            try:
                from supabase import create_client
                supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info("✅ Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Supabase client: {e}")
                supabase = None
        else:
            logger.warning("⚠️ Supabase environment variables not set")
        
        # Store supabase client in app for access in routes
        app.supabase = supabase
        
        # ROOT ROUTE
        @app.route('/')
        def root():
            return jsonify({
                'message': 'MindTrack Backend API', 
                'status': 'online',
                'supabase_connected': supabase is not None,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # HEALTH CHECK ROUTE
        @app.route('/api/health', methods=['GET'])
        def health_check():
            return jsonify({
                'status': 'healthy', 
                'message': 'Backend is working',
                'supabase_connected': supabase is not None,
                'environment': {
                    'SUPABASE_URL': 'Set' if SUPABASE_URL else 'Missing',
                    'SUPABASE_KEY': 'Set' if SUPABASE_KEY else 'Missing'
                },
                'timestamp': datetime.utcnow().isoformat()
            })
        
        # LOGIN ROUTE
        @app.route('/api/login', methods=['POST'])
        def login():
            try:
                # Check if Supabase is available
                if not supabase:
                    return jsonify({
                        'error': 'Database connection not available',
                        'details': 'Supabase client not initialized. Check environment variables.'
                    }), 500
                
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'Request body is required'}), 400
                    
                email = data.get('email')
                password = data.get('password')
                
                if not email or not password:
                    return jsonify({'error': 'Email and password are required'}), 400
                
                # Authenticate with Supabase
                try:
                    response = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })
                    
                    if response and response.user and response.session:
                        user = response.user
                        session = response.session
                        
                        # Get user metadata for display name
                        display_name = user.user_metadata.get('name', 'User') if user.user_metadata else 'User'
                        
                        # Check/create user in database
                        try:
                            existing = supabase.table('user').select('user_id').eq('user_id', user.id).execute()
                            if not existing.data:
                                # Insert user into users table
                                supabase.table('user').insert({
                                    "user_id": user.id,
                                    "email": user.email,
                                    "phone": user.phone or '',
                                    "name": display_name,
                                    "join_date": datetime.utcnow().isoformat()
                                }).execute()
                        except Exception as e:
                            logger.warning(f"Could not check/create user in database: {e}")
                        
                        return jsonify({
                            'success': True,
                            'message': 'Login successful',
                            'access_token': session.access_token,
                            'refresh_token': session.refresh_token,
                            'user': {
                                'id': user.id,
                                'email': user.email,
                                'phone': user.phone,
                                'display_name': display_name
                            }
                        }), 200
                    else:
                        return jsonify({'error': 'Invalid email or password'}), 401
                        
                except Exception as auth_error:
                    error_msg = str(auth_error).lower()
                    if "invalid login credentials" in error_msg:
                        return jsonify({'error': 'Invalid email or password'}), 401
                    elif "email not confirmed" in error_msg:
                        return jsonify({'error': 'Please verify your email first'}), 403
                    else:
                        logger.error(f"Authentication error: {auth_error}")
                        return jsonify({'error': 'Authentication failed'}), 401
                
            except Exception as e:
                logger.error(f"Login error: {e}")
                return jsonify({
                    'error': 'A server error has occurred',
                    'details': str(e)
                }), 500
        
        # SIGNUP ROUTE
        @app.route('/api/signup', methods=['POST'])
        def signup():
            try:
                # Check if Supabase is available
                if not supabase:
                    return jsonify({
                        'error': 'Database connection not available',
                        'details': 'Supabase client not initialized. Check environment variables.'
                    }), 500
                
                data = request.get_json()
                if not data:
                    return jsonify({'error': 'Request body is required'}), 400
                    
                email = data.get('email')
                password = data.get('password')
                name = data.get('name', 'User')
                
                if not email or not password:
                    return jsonify({'error': 'Email and password are required'}), 400
                
                # Sign up with Supabase
                try:
                    response = supabase.auth.sign_up({
                        "email": email,
                        "password": password,
                        "options": {
                            "data": {
                                "name": name
                            }
                        }
                    })
                    
                    if response and response.user:
                        user = response.user
                        session = response.session
                        
                        return jsonify({
                            'success': True,
                            'message': 'Signup successful',
                            'confirmation_required': not user.email_confirmed_at,
                            'user': {
                                'id': user.id,
                                'email': user.email,
                                'display_name': name
                            }
                        }), 201
                    else:
                        return jsonify({'error': 'Signup failed'}), 400
                        
                except Exception as auth_error:
                    error_msg = str(auth_error).lower()
                    if "user already registered" in error_msg or "email already exists" in error_msg:
                        return jsonify({'error': 'Email already registered'}), 409
                    else:
                        logger.error(f"Signup error: {auth_error}")
                        return jsonify({'error': 'Signup failed', 'details': str(auth_error)}), 400
                
            except Exception as e:
                logger.error(f"Signup error: {e}")
                return jsonify({
                    'error': 'A server error has occurred',
                    'details': str(e)
                }), 500

        # LOGOUT ROUTE
        @app.route('/api/logout', methods=['POST'])
        def logout():
            """Simple logout endpoint"""
            return jsonify({
                'success': True,
                'message': 'Logged out successfully',
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        
        # TOKEN VERIFICATION ROUTE
        @app.route('/api/verify-token-status', methods=['GET'])
        def verify_token_status():
            """Verify if a token is valid"""
            if not supabase:
                return jsonify({'valid': False, 'error': 'Database connection not available'}), 503
                
            try:
                auth_header = request.headers.get('Authorization')
                if not auth_header or not auth_header.startswith('Bearer '):
                    return jsonify({'valid': False, 'error': 'No token provided'}), 401

                access_token = auth_header.split(' ')[1]
                
                # Try to get user with the token
                user_response = supabase.auth.get_user(access_token)
                
                if user_response.user:
                    return jsonify({
                        'valid': True,
                        'user': {
                            'id': user_response.user.id,
                            'email': user_response.user.email,
                            'display_name': user_response.user.user_metadata.get('name', 'User')
                        }
                    }), 200
                else:
                    return jsonify({'valid': False, 'error': 'Invalid token'}), 401
                    
            except Exception as e:
                logger.error(f"Token verification error: {e}")
                return jsonify({'valid': False, 'error': str(e)}), 401
        
        # GLOBAL ERROR HANDLER
        @app.errorhandler(Exception)
        def handle_exception(e):
            logger.error(f"Unhandled exception: {e}")
            return jsonify({
                'error': 'A server error has occurred',
                'details': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }), 500
        
        logger.info("✅ Flask application created successfully")
        
        # Test Supabase connection if available
        if supabase:
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

# Create the Flask app using the simplified structure
logger.info("🔄 Initializing MindTrack Backend Application...")
app = create_application()

# Make sure we're not importing the blueprint-based app from __init__.py
# This ensures we only use the direct routes defined above

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
        'timestamp': datetime.utcnow().isoformat()
    }

if __name__ == '__main__':
    logger.info("🏃 Running Flask app in development mode...")
    app.run(host='0.0.0.0', port=5000, debug=True)
else:
    logger.info("🌐 Flask app ready for production (Vercel)...")

logger.info("🎯 MindTrack Backend initialization complete")