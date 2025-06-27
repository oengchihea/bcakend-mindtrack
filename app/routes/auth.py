import os
import logging
from flask import Blueprint, jsonify, request, g, current_app
from supabase import Client, create_client
from datetime import datetime, timezone
from functools import wraps
import jwt
from dotenv import load_dotenv
from typing import Callable, Tuple, Optional

# Load environment variables
load_dotenv()

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_ANON_KEY") or
    os.getenv("SUPABASE_KEY") or
    os.getenv("SUPABASE_ROLE_SERVICE") or
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)

# Initialize Supabase client
supabase: Optional[Client] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)
        logger.info("Supabase client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
else:
    logger.error("Missing SUPABASE_URL or SUPABASE_KEY")

# Initialize Blueprint
auth_bp = Blueprint('auth', __name__)

def auth_required(f: Callable) -> Callable:
    """
    Decorator to ensure user authentication via JWT token.

    Verifies the token, sets Supabase auth context for RLS, and stores user in `g`.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        supabase_client = getattr(current_app, 'supabase', supabase)
        if not supabase_client:
            logger.error("No Supabase client available")
            return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            logger.warning("Missing or invalid Authorization header")
            return jsonify({"error": "Authorization header required", "code": "AUTH_HEADER_MISSING"}), 401

        try:
            token = auth_header.split(' ')[1]
            logger.debug(f"Validating token: {token[:20]}... (length: {len(token)})")
            if hasattr(supabase_client, 'postgrest'):
                supabase_client.postgrest.auth(token)
            user_response = supabase_client.auth.get_user(token)
            if not user_response or not user_response.user:
                if hasattr(supabase_client, 'postgrest'):
                    supabase_client.postgrest.auth(None)
                logger.warning("Invalid or expired token")
                return jsonify({"error": "Invalid or expired token", "code": "INVALID_TOKEN"}), 401

            g.user = user_response.user
            g.token = token
            logger.info(f"Authenticated user {g.user.id}")
            return f(*args, **kwargs)
        except Exception as e:
            if hasattr(supabase_client, 'postgrest'):
                supabase_client.postgrest.auth(None)
            logger.error(f"Token verification failed: {e}, Token: {token[:20]}...")
            return jsonify({"error": "Token verification failed", "code": "TOKEN_VERIFICATION_FAILED", "details": str(e)}), 500  # Changed to 500 for server errors
    return decorated_function

def validate_email(email: str) -> bool:
    """Validate email format."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

@auth_bp.route('/signup', methods=['POST'])
def api_signup():
    """Register a new user with email, password, name, and phone."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

    if not request.is_json:
        logger.warning("Invalid request format")
        return jsonify({"error": "Request must be JSON", "code": "INVALID_REQUEST"}), 400

    data = request.get_json()
    email, password, name, phone = data.get('email'), data.get('password'), data.get('name'), data.get('phone')

    if not all([email, password, name, phone]):
        logger.warning("Missing required fields")
        return jsonify({"error": "Email, password, name, and phone are required", "code": "MISSING_FIELDS"}), 400

    if not validate_email(email):
        logger.warning(f"Invalid email format: {email}")
        return jsonify({"error": "Invalid email format", "code": "INVALID_EMAIL"}), 400

    if len(password) < 8:
        logger.warning("Password too short")
        return jsonify({"error": "Password must be at least 8 characters", "code": "INVALID_PASSWORD"}), 400

    try:
        existing_user = supabase.table('user').select('email').eq('email', email).execute()
        if existing_user.data:
            logger.warning(f"Email already registered: {email}")
            return jsonify({"error": "Email is already registered", "code": "EMAIL_EXISTS"}), 400

        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"verify_via": "otp", "name": name, "phone": phone},
                "email_redirect_to": "http://your-app.com/verify"
            }
        })

        supabase.table('user').insert({
            "user_id": response.user.id,
            "email": email,
            "name": name,
            "phone": phone,
            "join_date": datetime.now(timezone.utc).isoformat()
        }).execute()

        logger.info(f"User signed up successfully: {response.user.id}")
        return jsonify({"message": "OTP sent to your email for verification", "user_id": response.user.id}), 201
    except Exception as e:
        logger.error(f"Signup failed: {e}")
        return jsonify({"error": "Signup failed", "code": "SIGNUP_FAILED", "details": str(e)}), 400

@auth_bp.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP for email confirmation."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

    if not request.is_json:
        logger.warning("Invalid request format")
        return jsonify({"error": "Request must be JSON", "code": "INVALID_REQUEST"}), 400

    data = request.get_json()
    email, token = data.get('email'), data.get('token')

    if not email or not token:
        logger.warning("Missing email or OTP token")
        return jsonify({"error": "Email and OTP token are required", "code": "MISSING_FIELDS"}), 400

    try:
        response = supabase.auth.verify_otp({"email": email, "token": token, "type": "signup"})
        if not response or not response.session:
            logger.warning("OTP verification failed")
            return jsonify({"error": "Verification failed", "code": "INVALID_OTP"}), 400

        logger.info(f"OTP verified for email: {email}")
        return jsonify({
            "message": "Email verification successful",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {"id": response.user.id, "email": response.user.email}
        }), 200
    except Exception as e:
        logger.error(f"OTP verification failed: {e}")
        return jsonify({"error": "Verification failed", "code": "VERIFICATION_FAILED", "details": str(e)}), 400

@auth_bp.route('/login', methods=['POST'])
def login():
    """Authenticate user with email or phone and password."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

    if not request.is_json:
        logger.warning("Invalid request format")
        return jsonify({"error": "Request must be JSON", "code": "INVALID_REQUEST"}), 400

    data = request.get_json()
    email, phone, password = data.get('email'), data.get('phone'), data.get('password')

    if not password or not (email or phone):
        logger.warning("Missing email/phone or password")
        return jsonify({"error": "Email or phone and password required", "code": "MISSING_FIELDS"}), 400

    try:
        fresh_supabase = create_client(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)
        response = None
        if email:
            response = fresh_supabase.auth.sign_in_with_password({"email": email, "password": password})
        else:
            response = fresh_supabase.auth.sign_in_with_password({"phone": phone, "password": password})

        if not response or not response.session or not response.user:
            logger.warning("Authentication failed: Invalid response")
            return jsonify({"error": "Authentication failed", "code": "AUTH_FAILED"}), 401

        user_id, user_email, user_phone = response.user.id, response.user.email, response.user.phone
        display_name = response.user.user_metadata.get('name', 'User') if response.user.user_metadata else 'User'

        existing = fresh_supabase.table('user').select('user_id').eq('user_id', user_id).execute()
        if not existing.data:
            fresh_supabase.table('user').insert({
                "user_id": user_id,
                "email": user_email,
                "phone": user_phone or '',
                "name": display_name,
                "join_date": datetime.now(timezone.utc).isoformat()
            }).execute()

        logger.info(f"User logged in successfully: {user_id}")
        return jsonify({
            "success": True,
            "message": "Login successful",
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": user_id,
                "email": user_email,
                "phone": user_phone,
                "display_name": display_name
            }
        }), 200
    except Exception as e:
        error_msg = str(e).lower()
        if "invalid login credentials" in error_msg:
            logger.warning("Invalid login credentials")
            return jsonify({"error": "Invalid email or password", "code": "INVALID_CREDENTIALS"}), 401
        elif "email not confirmed" in error_msg:
            logger.warning("Email not confirmed")
            return jsonify({"error": "Please verify your email first", "code": "EMAIL_NOT_CONFIRMED"}), 403
        logger.error(f"Login failed: {e}")
        return jsonify({"error": "Authentication failed", "code": "AUTH_FAILED", "details": str(e)}), 401

@auth_bp.route('/change-password', methods=['POST'])
@auth_required
def change_password():
    """Change user password after verifying current password."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

    if not request.is_json:
        logger.warning("Invalid request format")
        return jsonify({"error": "Request must be JSON", "code": "INVALID_REQUEST"}), 400

    data = request.get_json()
    current_password, new_password, confirm_password = data.get('currentPassword'), data.get('newPassword'), data.get('confirmPassword')

    if not all([current_password, new_password, confirm_password]):
        logger.warning("Missing password fields")
        return jsonify({"error": "Current password, new password, and confirmation required", "code": "MISSING_FIELDS"}), 400

    if new_password != confirm_password:
        logger.warning("New passwords do not match")
        return jsonify({"error": "New passwords do not match", "code": "PASSWORD_MISMATCH"}), 400

    if len(new_password) < 8:
        logger.warning("New password too short")
        return jsonify({"error": "New password must be at least 8 characters", "code": "INVALID_PASSWORD"}), 400

    if current_password == new_password:
        logger.warning("New password same as current")
        return jsonify({"error": "New password must be different from current", "code": "SAME_PASSWORD"}), 400

    try:
        current_user = g.user
        user_email = current_user.email
        if not user_email:
            logger.warning("User email not found")
            return jsonify({"error": "User email not found", "code": "NO_EMAIL"}), 400

        verification_response = supabase.auth.sign_in_with_password({"email": user_email, "password": current_password})
        if not verification_response or not verification_response.user:
            logger.warning("Current password incorrect")
            return jsonify({"error": "Current password is incorrect", "code": "INVALID_CURRENT_PASSWORD"}), 401

        session = verification_response.session
        if not session or not session.access_token:
            logger.error("Failed to get valid session")
            return jsonify({"error": "Failed to get valid session", "code": "SESSION_ERROR"}), 500

        session_supabase = create_client(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)
        session_supabase.auth.set_session(session.access_token, session.refresh_token)
        update_response = session_supabase.auth.update_user({"password": new_password})

        if not update_response or not update_response.user:
            logger.error("Failed to update password")
            return jsonify({"error": "Failed to update password", "code": "UPDATE_FAILED"}), 500

        logger.info(f"Password updated successfully for user {current_user.id}")
        return jsonify({"message": "Password updated successfully", "success": True}), 200
    except Exception as e:
        error_msg = str(e).lower()
        if "weak password" in error_msg:
            logger.warning("Weak password provided")
            return jsonify({"error": "Password is too weak", "code": "WEAK_PASSWORD"}), 400
        logger.error(f"Password change failed: {e}")
        return jsonify({"error": "Password change failed", "code": "CHANGE_FAILED", "details": str(e)}), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Initiate or complete password reset with OTP."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

    if not request.is_json:
        logger.warning("Invalid request format")
        return jsonify({"error": "Request must be JSON", "code": "INVALID_REQUEST"}), 400

    data = request.get_json()
    email, new_password, otp = data.get('email'), data.get('new_password'), data.get('otp')

    if not email and not (otp and new_password):
        logger.warning("Invalid request parameters")
        return jsonify({"error": "Email required for OTP request, or email+otp+new_password for reset", "code": "INVALID_PARAMS"}), 400

    try:
        if not otp and not new_password:
            supabase.auth.reset_password_for_email(email, {"redirect_to": "http://your-app.com/reset-password"})
            logger.info(f"Password reset OTP sent for email: {email}")
            return jsonify({
                "message": "If an account exists, an OTP has been sent",
                "next_step": "verify_otp",
                "email": email
            }), 200
        elif email and otp and new_password:
            otp_response = supabase.auth.verify_otp({"email": email, "token": otp, "type": "recovery"})
            if not otp_response or not otp_response.user:
                logger.warning("Invalid or expired OTP")
                return jsonify({"error": "Invalid or expired OTP", "code": "INVALID_OTP"}), 400

            supabase.auth.update_user({"password": new_password})
            logger.info(f"Password reset successfully for email: {email}")
            return jsonify({"message": "Password updated successfully", "email": email}), 200
        else:
            logger.warning("Invalid request parameters")
            return jsonify({"error": "Invalid request parameters", "code": "INVALID_PARAMS"}), 400
    except Exception as e:
        logger.error(f"Password reset failed: {e}")
        return jsonify({"error": "Password reset failed", "code": "RESET_FAILED", "details": str(e)}), 400

@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Log out the user, clearing session."""
    try:
        auth_header = request.headers.get('Authorization')
        user_id = 'unknown'
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                decoded = jwt.decode(token, options={"verify_signature": False})
                user_id = decoded.get('sub', 'unknown')
            except Exception as e:
                logger.warning(f"Could not decode token: {e}")

        logger.info(f"Starting logout for user {user_id}")
        if supabase and auth_header and auth_header.startswith('Bearer '):
            temp_supabase = create_client(supabase_url=SUPABASE_URL, supabase_key=SUPABASE_KEY)
            try:
                temp_supabase.auth.sign_out(scope='local')
                logger.info(f"Supabase logout successful for user {user_id}")
            except Exception as e:
                logger.warning(f"Supabase logout failed: {e}")

        logger.info(f"User {user_id} logged out successfully")
        return jsonify({
            "success": True,
            "message": "Logged out successfully",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}")
        return jsonify({
            "success": True,
            "message": "Logged out locally due to server error",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200

@auth_bp.route('/verify-token-status', methods=['GET'])
def verify_token_status():
    """Verify if a JWT token is valid."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 503

    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        logger.warning("No token provided")
        return jsonify({"valid": False, "error": "No token provided", "code": "NO_TOKEN"}), 401

    try:
        access_token = auth_header.split(' ')[1]
        user_response = supabase.auth.get_user(access_token)
        if user_response.user:
            logger.info(f"Token verified for user {user_response.user.id}")
            return jsonify({
                "valid": True,
                "user": {
                    "id": user_response.user.id,
                    "email": user_response.user.email,
                    "display_name": user_response.user.user_metadata.get('display_name', 'User')
                }
            }), 200
        logger.warning("Invalid token")
        return jsonify({"valid": False, "error": "Invalid token", "code": "INVALID_TOKEN"}), 401
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        return jsonify({"valid": False, "error": str(e), "code": "VERIFICATION_FAILED"}), 401

@auth_bp.route('/test-verify-token', methods=['GET'])
@auth_required
def test_verify_token():
    """Test endpoint to verify token authentication."""
    user = g.user
    logger.info(f"Token verification test for user {user.id}")
    return jsonify({
        "message": "Token is valid",
        "user_id": user.id,
        "email": user.email
    }), 200

@auth_bp.route('/refresh-token', methods=['POST'])
def refresh_token():
    """Refresh JWT access token using refresh token."""
    if not supabase:
        logger.error("Supabase client not initialized")
        return jsonify({"error": "Database connection not available", "code": "NO_SUPABASE"}), 500

    if not request.is_json:
        logger.warning("Invalid request format")
        return jsonify({"error": "Request must be JSON", "code": "INVALID_REQUEST"}), 400

    data = request.get_json()
    refresh_token = data.get('refresh_token')
    if not refresh_token:
        logger.warning("Missing refresh token")
        return jsonify({"error": "Refresh token is required", "code": "MISSING_TOKEN"}), 400

    try:
        response = supabase.auth.refresh_session(refresh_token)
        if response and response.session:
            logger.info("Token refreshed successfully")
            return jsonify({
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "expires_at": response.session.expires_at
            }), 200
        logger.warning("Failed to refresh token")
        return jsonify({"error": "Failed to refresh token", "code": "REFRESH_FAILED"}), 401
    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return jsonify({"error": f"Token refresh failed: {str(e)}", "code": "REFRESH_FAILED"}), 401

@auth_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for auth service."""
    logger.info("Auth health check accessed")
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "auth",
        "supabase_configured": bool(SUPABASE_URL and SUPABASE_KEY),
        "supabase_initialized": supabase is not None
    }), 200
