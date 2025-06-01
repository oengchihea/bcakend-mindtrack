from flask import Blueprint, jsonify, request
from supabase import create_client
import os
from datetime import datetime
from functools import wraps

auth_bp = Blueprint('auth', __name__)
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

def verify_token(f):
    """Decorator to verify JWT tokens from Supabase"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        
        if auth_header:
            try:
                token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else auth_header
            except IndexError:
                return jsonify({'error': 'Invalid token format'}), 401
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            user_response = supabase.auth.get_user(token)
            
            if not user_response or not user_response.user:
                return jsonify({'error': 'Token verification failed'}), 401
            
            request.current_user = user_response.user
            
        except Exception as e:
            return jsonify({'error': 'Token verification failed'}), 401
        
        return f(*args, **kwargs)
    
    return decorated_function

@auth_bp.route('/api/signup', methods=['POST'])
def api_signup():
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

@auth_bp.route('/api/verify-otp', methods=['POST'])
def verify_otp():
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

@auth_bp.route('/api/login', methods=['POST'])
def login():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')

    if not password or not (email or phone):
        return jsonify({"error": "Email or phone and password required"}), 400

    try:
        if email:
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        else:
            response = supabase.auth.sign_in_with_password({
                "phone": phone,
                "password": password
            })

        if not response or not hasattr(response, 'session') or not hasattr(response, 'user'):
            return jsonify({"error": "Unexpected response from Supabase"}), 500

        session = response.session
        user = response.user

        if not session or not user:
            return jsonify({"error": "Authentication failed"}), 401

        user_id = user.id
        user_email = user.email
        user_phone = user.phone

        # Check if user exists in the users table
        existing = supabase.table('user').select('user_id').eq('user_id', user_id).execute()
        if not existing.data:
            # Insert user into users table
            supabase.table('user').insert({
                "user_id": user_id,
                "email": user_email,
                "phone": user_phone or '',
                "name": user_email.split('@')[0] if user_email else 'User',
                "join_date": datetime.utcnow().isoformat()
            }).execute()
        
        return jsonify({
            "message": "Login successful",
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "user": {
                "id": user_id,
                "email": user_email,
                "phone": user_phone
            }
        }), 200

    except Exception as e:
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return jsonify({"error": "Invalid email/phone or password"}), 401
        if "Email not confirmed" in error_msg:
            return jsonify({"error": "Please verify your email first"}), 403
        return jsonify({"error": f"Login failed: {error_msg}"}), 400

@auth_bp.route('/api/reset-password', methods=['POST'])
def reset_password():
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
            response = supabase.auth.reset_password_for_email(
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
            
        except Exception as e:
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
            
            update_response = supabase.auth.update_user({
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

@auth_bp.route('/api/verify-token', methods=['GET'])
@verify_token
def test_verify_token():
    """Test endpoint to verify if token verification is working"""
    user = request.current_user
    return jsonify({
        "message": "Token is valid",
        "user_id": user.id,
        "email": user.email
    }), 200