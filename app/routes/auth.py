from flask import Blueprint, jsonify, request, g
from supabase import Client, create_client
import os
from datetime import datetime
from functools import wraps
import logging
import jwt
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logger
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Get environment variables with validation - DO NOT RAISE EXCEPTIONS HERE
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")

# Log environment variable status instead of raising exceptions
if not SUPABASE_URL:
    logger.error("CRITICAL: SUPABASE_URL environment variable is missing")
    print("❌ SUPABASE_URL environment variable is missing")
else:
    print(f"✅ SUPABASE_URL found: {SUPABASE_URL}")

if not SUPABASE_KEY:
    logger.error("CRITICAL: SUPABASE_ANON_KEY or SUPABASE_KEY environment variable is missing")
    print("❌ SUPABASE_ANON_KEY or SUPABASE_KEY environment variable is missing")
else:
    print(f"✅ SUPABASE_KEY found: {'*' * 10}...{SUPABASE_KEY[-4:] if SUPABASE_KEY else 'None'}")

# Initialize Supabase client with graceful error handling
supabase = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY
        )
        print("✅ Supabase client initialized successfully")
    else:
        print("❌ Cannot initialize Supabase client: Missing required environment variables")
        supabase = None
except Exception as e:
    print(f"❌ Failed to initialize Supabase client: {e}")
    logger.error(f"Failed to initialize Supabase client: {e}")
    supabase = None

auth_bp = Blueprint('auth', __name__)

def auth_required(f):
    """
    Decorator to ensure a user is authenticated.
    Verifies the JWT token from the Authorization header, sets the
    Supabase client's auth context for RLS, and stores the user
    object in Flask's request context `g`.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import current_app
        logger.info(f"Auth required: Checking supabase client - current_app.supabase: {getattr(current_app, 'supabase', None)}, global supabase: {supabase}")
        
        # Use global supabase as fallback if current_app.supabase is None
        supabase_client = getattr(current_app, 'supabase', None) or supabase
        
        if not supabase_client:
            logger.error("Authentication failed: No Supabase client available")
            return jsonify({'error': 'Internal server error: Database connection not available', 'code': 'NO_SUPABASE'}), 500

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Authentication failed: No or invalid Authorization header")
            return jsonify({'error': 'Authorization header is required', 'code': 'AUTH_HEADER_MISSING'}), 401

        try:
            token = auth_header.split(' ')[1]
            
            # Set auth for the request-bound supabase client for RLS
            if hasattr(supabase_client, 'postgrest'):
                supabase_client.postgrest.auth(token)
            
            user_response = supabase_client.auth.get_user(token)

            if not user_response or not user_response.user:
                # Clear potentially invalid auth token
                if hasattr(current_app, 'supabase') and hasattr(current_app.supabase, 'postgrest'):
                    current_app.supabase.postgrest.auth(None)
                return jsonify({'error': 'Invalid or expired token', 'code': 'INVALID_TOKEN'}), 401

            # Store user and token in the request context `g` for use in the route
            g.user = user_response.user
            g.token = token
            logger.info(f"Authentication successful for user {g.user.id}")

        except Exception as e:
            # Ensure auth context is cleared on any failure
            if hasattr(current_app, 'supabase') and hasattr(current_app.supabase, 'postgrest'):
                current_app.supabase.postgrest.auth(None)
            return jsonify({'error': 'Token verification failed', 'details': str(e), 'code': 'TOKEN_VERIFICATION_FAILED'}), 401

        return f(*args, **kwargs)
    return decorated_function

@auth_bp.route('/change-password', methods=['POST'])
@auth_required
def change_password():
    """Change user password with current password verification"""
    if not supabase:
        return jsonify({"error": "Database connection not available"}), 500
        
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    current_password = data.get('currentPassword')
    new_password = data.get('newPassword')
    confirm_password = data.get('confirmPassword')

    # Validate input
    if not current_password:
        return jsonify({"error": "Current password is required"}), 400
    if not new_password:
        return jsonify({"error": "New password is required"}), 400
    if not confirm_password:
        return jsonify({"error": "Password confirmation is required"}), 400
    
    # Check if new passwords match
    if new_password != confirm_password:
        return jsonify({"error": "New passwords do not match"}), 400
    
    # Validate new password strength
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters long"}), 400
    
    # Check if new password is different from current password
    if current_password == new_password:
        return jsonify({"error": "New password must be different from current password"}), 400

    try:
        # Get current user email
        current_user = g.user
        user_email = current_user.email
        
        if not user_email:
            return jsonify({"error": "User email not found"}), 400

        # Verify current password by attempting to sign in
        try:
            verification_response = supabase.auth.sign_in_with_password({
                "email": user_email,
                "password": current_password
            })
            
            if not verification_response or not verification_response.user:
                return jsonify({"error": "Current password is incorrect"}), 401
                
        except Exception as verify_error:
            error_msg = str(verify_error).lower()
            if "invalid login credentials" in error_msg or "invalid" in error_msg:
                return jsonify({"error": "Current password is incorrect"}), 401
            else:
                return jsonify({"error": "Password verification failed"}), 500

        # Update password using the session from verification
        try:
            # Get the session from the verification response
            session = verification_response.session
            
            if not session or not session.access_token:
                return jsonify({"error": "Failed to get valid session"}), 500
            
            # Create a new client with the fresh session token
            session_supabase = create_client(
                supabase_url=SUPABASE_URL,
                supabase_key=SUPABASE_KEY
            )
            
            # Set the auth token from the fresh session
            session_supabase.auth.set_session(session.access_token, session.refresh_token)
            
            # Update the password using the authenticated session
            update_response = session_supabase.auth.update_user({
                "password": new_password
            })
            
            if not update_response or not update_response.user:
                return jsonify({"error": "Failed to update password"}), 500
            
            return jsonify({
                "message": "Password updated successfully",
                "success": True
            }), 200
            
        except Exception as update_error:
            error_msg = str(update_error).lower()
            if "weak password" in error_msg:
                return jsonify({"error": "Password is too weak. Please choose a stronger password"}), 400
            elif "same password" in error_msg:
                return jsonify({"error": "New password must be different from current password"}), 400
            else:
                return jsonify({"error": f"Failed to update password: {str(update_error)}"}), 500
                
    except Exception as e:
        return jsonify({
            "error": "Password change failed",
            "details": str(e)
        }), 500

@auth_bp.route('/signup', methods=['POST'])
def api_signup():
    if not supabase:
        return jsonify({"error": "Database connection not available"}), 500
        
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    phone = data.get('phone')

    # Validate input
    if not email:
        return jsonify({"error": "Email is required"}), 400
    if not password:
        return jsonify({"error": "Password is required"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not name:
        return jsonify({"error": "Name is required"}), 400
    if not phone:
        return jsonify({"error": "Phone is required"}), 400

    # Check if email already exists
    try:
        existing_user = supabase.table('user').select('email').eq('email', email).execute()
        if existing_user.data:
            return jsonify({"error": "Email is already registered"}), 400
    except Exception as e:
        return jsonify({"error": "Error checking email", "details": str(e)}), 500

    try:
        # Sign up with email and OTP verification
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"verify_via": "otp", "name": name, "phone": phone},
                "email_redirect_to": "http://your-app.com/verify"
            }
        })

        # Insert user data into the users table
        supabase.table('user').insert({
            "user_id": response.user.id,
            "email": email,
            "name": name,
            "phone": phone,
            "join_date": datetime.utcnow().isoformat()
        }).execute()
        
        return jsonify({
            "message": "OTP sent to your email for verification",
            "user_id": response.user.id
        }), 201
        
    except Exception as e:
        return jsonify({
            "error": "Signup failed",
            "details": str(e)
        }), 400

@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    if not supabase:
        return jsonify({"error": "Database connection not available"}), 500
        
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    email = data.get('email')
    token = data.get('token')

    if not email or not token:
        return jsonify({"error": "Email and OTP token are required"}), 400

    try:
        response = supabase.auth.verify_otp({
            "email": email,
            "token": token,
            "type": "signup"
        })
        
        if not response or not response.session:
            return jsonify({"error": "Verification failed"}), 400
            
        return jsonify({
            "message": "Email verification successful",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": response.user.id,
                "email": response.user.email
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            "error": "Verification failed",
            "details": str(e)
        }), 400

@auth_bp.route('/login', methods=['POST'])
def login():
    """Enhanced login endpoint with better error handling"""
    # Check if Supabase is available
    if not supabase:
        return jsonify({
            "error": "Database connection not available",
            "details": "Supabase client not initialized. Check environment variables."
        }), 500
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
        
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')

    if not password or not (email or phone):
        return jsonify({"error": "Email or phone and password required"}), 400

    try:
        # Create a fresh Supabase client for this request
        fresh_supabase = create_client(
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY
        )
        
        # Attempt login with email
        if email:
            try:
                response = fresh_supabase.auth.sign_in_with_password({
                    "email": email,
                    "password": password
                })
            except Exception as e:
                error_msg = str(e).lower()
                if "invalid login credentials" in error_msg:
                    return jsonify({"error": "Invalid email or password"}), 401
                elif "email not confirmed" in error_msg:
                    return jsonify({"error": "Please verify your email first"}), 403
                else:
                    logger.error(f"Login error with email: {e}")
                    return jsonify({"error": "Authentication failed"}), 401
        else:
            # Phone login (if implemented)
            try:
                response = fresh_supabase.auth.sign_in_with_password({
                    "phone": phone,
                    "password": password
                })
            except Exception as e:
                error_msg = str(e).lower()
                if "invalid login credentials" in error_msg:
                    return jsonify({"error": "Invalid phone or password"}), 401
                else:
                    logger.error(f"Login error with phone: {e}")
                    return jsonify({"error": "Authentication failed"}), 401

        if not response or not hasattr(response, 'session') or not hasattr(response, 'user'):
            return jsonify({"error": "Unexpected response from authentication service"}), 500

        session = response.session
        user = response.user

        if not session or not user:
            return jsonify({"error": "Authentication failed"}), 401

        user_id = user.id
        user_email = user.email
        user_phone = user.phone

        # Get user metadata for display name
        display_name = user.user_metadata.get('name', 'User') if user.user_metadata else 'User'
        
        # Check if user exists in the users table, create if not
        try:
            existing = fresh_supabase.table('user').select('user_id').eq('user_id', user_id).execute()
            if not existing.data:
                # Insert user into users table
                fresh_supabase.table('user').insert({
                    "user_id": user_id,
                    "email": user_email,
                    "phone": user_phone or '',
                    "name": display_name,
                    "join_date": datetime.utcnow().isoformat()
                }).execute()
        except Exception as e:
            logger.warning(f"Could not check/create user in database: {e}")
            # Continue with login even if database operation fails
        
        return jsonify({
            "success": True,
            "message": "Login successful",
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "user": {
                "id": user_id,
                "email": user_email,
                "phone": user_phone,
                "display_name": display_name
            }
        }), 200

    except Exception as e:
        logger.error(f"Unexpected login error: {e}", exc_info=True)
        return jsonify({
            "error": "A server error has occurred",
            "details": str(e)
        }), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    if not supabase:
        return jsonify({"error": "Database connection not available"}), 500
        
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    email = data.get('email')
    new_password = data.get('new_password')
    otp = data.get('otp')

    # Step 1: Request password reset (send OTP)
    if not otp and not new_password:
        if not email:
            return jsonify({"error": "Email is required to reset password"}), 400

        try:
            supabase.auth.reset_password_for_email(
                email,
                {
                    "redirect_to": "http://your-app.com/reset-password"
                }
            )
            
            return jsonify({
                "message": "If an account exists, an OTP has been sent",
                "next_step": "verify_otp",
                "email": email
            }), 200
            
        except Exception:
            # Don't reveal if email exists or not
            return jsonify({
                "message": "If an account exists, an OTP has been sent",
                "next_step": "verify_otp",
                "email": email
            }), 200

    # Step 2: Verify OTP and update password
    elif email and otp and new_password:
        try:
            otp_response = supabase.auth.verify_otp({
                "email": email,
                "token": otp,
                "type": "recovery"
            })
            
            if not otp_response or not otp_response.user:
                return jsonify({"error": "Invalid or expired OTP"}), 400
            
            supabase.auth.update_user({
                "password": new_password
            })
            
            return jsonify({
                "message": "Password updated successfully",
                "email": email
            }), 200
            
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    else:
        return jsonify({
            "error": "Invalid request parameters",
            "details": "Provide email for OTP request, or email+otp+new_password for reset"
        }), 400

def extract_user_from_token(access_token):
    """Extract user information from JWT token without validation"""
    try:
        # Decode without verification (just to extract payload)
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        return {
            'user_id': decoded.get('sub'),
            'email': decoded.get('email'),
            'exp': decoded.get('exp')
        }
    except Exception as e:
        logger.warning(f"Could not decode token: {e}")
        return None

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Robust logout endpoint that handles various scenarios"""
    try:
        # Get authorization header
        auth_header = request.headers.get('Authorization')
        
        # Extract user info if token is present
        user_info = None
        if auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header.split(' ')[1]
            user_info = extract_user_from_token(access_token)
            logger.info(f"🔄 Starting logout for user {user_info.get('user_id') if user_info else 'unknown'}")
        else:
            logger.info("🔄 Starting logout without token")

        # Multiple logout strategies
        logout_methods_tried = []
        final_success = False

        # Strategy 1: Try Supabase logout with current session (only if Supabase is available)
        if supabase and auth_header and auth_header.startswith('Bearer '):
            access_token = auth_header.split(' ')[1]
            
            try:
                logger.info("🔄 Attempting Supabase logout method 1...")
                
                # Create a new supabase client instance for this logout
                temp_supabase = create_client(
                    supabase_url=SUPABASE_URL,
                    supabase_key=SUPABASE_KEY
                )
                
                # Try to set session and logout
                try:
                    # Method 1a: Try local logout only (doesn't require refresh token)
                    temp_supabase.auth.sign_out(scope='local')
                    final_success = True
                    logout_methods_tried.append("supabase_local_logout")
                    logger.info("✅ Supabase logout method 1a successful")
                    
                except Exception as e1:
                    logger.warning(f"⚠️ Supabase logout method 1a failed: {e1}")
                    
                    try:
                        # Method 1b: Try global logout (may fail due to refresh token)
                        temp_supabase.auth.set_session(access_token, '')
                        temp_supabase.auth.sign_out()
                        final_success = True
                        logout_methods_tried.append("supabase_global_logout")
                        logger.info("✅ Supabase logout method 1b successful")
                        
                    except Exception as e2:
                        logger.warning(f"⚠️ Supabase logout method 1b failed: {e2}")
                        logout_methods_tried.append(f"supabase_failed: {str(e2)}")
                        
            except Exception as e:
                logger.warning(f"⚠️ Supabase logout method 1 failed: {e}")
                logout_methods_tried.append(f"supabase_error: {str(e)}")

        # Strategy 2: Fallback - always succeed for client
        if not final_success:
            logger.info("⚠️ Using fallback logout method")
            final_success = True
            logout_methods_tried.append("fallback_success")

        # Log the logout event
        user_id = user_info.get('user_id') if user_info else 'unknown'
        logger.info(f"✅ User {user_id} logged out successfully")

        # Prepare response
        response_data = {
            'success': True,
            'message': 'Logged out successfully',
            'user_id': user_id,
            'methods_tried': logout_methods_tried,
            'timestamp': datetime.utcnow().isoformat()
        }

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ Unexpected error during logout: {e}")
        
        # Always return success for logout to allow client cleanup
        return jsonify({
            'success': True,
            'message': 'Logged out locally due to server error',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 200

@auth_bp.route('/verify-token-status', methods=['GET'])
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
                    'display_name': user_response.user.user_metadata.get('display_name', 'User')
                }
            }), 200
        else:
            return jsonify({'valid': False, 'error': 'Invalid token'}), 401
            
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return jsonify({'valid': False, 'error': str(e)}), 401

@auth_bp.route('/test-verify-token', methods=['GET'])
@auth_required
def test_verify_token():
    """Test endpoint to verify if token verification is working"""
    user = g.user
    return jsonify({
        "message": "Token is valid",
        "user_id": user.id,
        "email": user.email
    }), 200

@auth_bp.route('/refresh-token', methods=['POST'])
def refresh_token():
    """Refresh access token using refresh token"""
    if not supabase:
        return jsonify({"error": "Database connection not available"}), 500
        
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    refresh_token = data.get('refresh_token')

    if not refresh_token:
        return jsonify({"error": "Refresh token is required"}), 400

    try:
        response = supabase.auth.refresh_session(refresh_token)
        
        if response and response.session:
            return jsonify({
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "expires_at": response.session.expires_at
            }), 200
        else:
            return jsonify({"error": "Failed to refresh token"}), 401
            
    except Exception as e:
        return jsonify({"error": f"Token refresh failed: {str(e)}"}), 401

# Health check endpoint
@auth_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'auth',
        'supabase_configured': bool(SUPABASE_URL and SUPABASE_KEY),
        'supabase_initialized': supabase is not None,
        'environment_variables': {
            'SUPABASE_URL': 'Set' if SUPABASE_URL else 'Missing',
            'SUPABASE_KEY': 'Set' if SUPABASE_KEY else 'Missing'
        }
    }), 200