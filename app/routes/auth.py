from flask import Blueprint, jsonify, render_template, request, redirect, url_for, flash
from supabase import create_client
import os
from datetime import datetime



auth_bp = Blueprint('auth', __name__)
supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

@auth_bp.route('/api/signup', methods=['POST'])
def api_signup():
    if not request.is_json:
        print('Error: Request is not JSON')
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    print('Received signup request data:', data)
    email = data.get('email')
    password = data.get('password')
    name = data.get('name')
    phone = data.get('phone')
    
    # Validate input
    if not email:
        print('Validation error: Email is required')
        return jsonify({"error": "Email is required"}), 400
    if not password:
        print('Validation error: Password is required')
        return jsonify({"error": "Password is required"}), 400
    if len(password) < 8:
        print('Validation error: Password too short')
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if not name:
        print('Validation error: Name is required')
        return jsonify({"error": "Name is required"}), 400
    if not phone:
        print('Validation error: Phone is required')
        return jsonify({"error": "Phone is required"}), 400
    
    # Check if email already exists
    try:
        print(f'Checking if email exists: {email}')
        existing_user = supabase.table('user').select('email').eq('email', email).execute()
        if existing_user.data:
            print('Email already registered:', email)
            return jsonify({"error": "Email is already registered"}), 400
    except Exception as e:
        print(f'Error checking email: {str(e)}')
        return jsonify({"error": "Error checking email", "details": str(e)}), 500
    
    try:
        # Sign up with email and OTP verification
        print(f'Attempting signup for email: {email}')
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"verify_via": "otp", "name": name, "phone": phone},
                "email_redirect_to": "http://your-app.com/verify"
            }
        })

        # Insert user data into the users table
        print(f'Inserting user data for user_id: {response.user.id}')
        supabase.table('user').insert({
            "user_id": response.user.id,
            "email": email,
            "name": name,
            "phone": phone,
            "join_date": datetime.utcnow().isoformat()
        }).execute()
        
        print('Signup successful, OTP sent')
        return jsonify({
            "message": "OTP sent to your email for verification",
            "user_id": response.user.id
        }), 201
        
    except Exception as e:
        print(f'Error during signup: {str(e)}')
        return jsonify({
            "error": "Signup failed",
            "details": str(e)
        }), 400

@auth_bp.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    # Validate request
    if not request.is_json:
        print('Error: Request is not JSON')
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.get_json()
    print('Received OTP verification request data:', data)
    email = data.get('email')
    token = data.get('token')
    
    # Validate input
    if not email or not token:
        print('Validation error: Email and OTP token are required')
        return jsonify({"error": "Email and OTP token are required"}), 400
    
    try:
        print(f'Verifying OTP for email: {email}')
        response = supabase.auth.verify_otp({
            "email": email,
            "token": token,
            "type": "signup"  # For signup verification
        })
        
        if not response or not response.session:
            print('OTP verification failed')
            return jsonify({"error": "Verification failed"}), 400
            
        print('OTP verification successful')
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
        print(f'Error during OTP verification: {str(e)}')
        return jsonify({
            "error": "Verification failed",
            "details": str(e)
        }), 400


@auth_bp.route('/api/login', methods=['POST'])
def login():
    if not request.is_json:
        print('Error: Request is not JSON')
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    print("Received login request data:", data)  # Debug logging

    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')

    if not password or not (email or phone):
        print('Error: Missing email/phone or password')
        return jsonify({"error": "Email or phone and password required"}), 400

    try:
        if email:
            print(f"Attempting login with email: {email}")
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
        else:
            print(f"Attempting login with phone: {phone}")
            response = supabase.auth.sign_in_with_password({
                "phone": phone,
                "password": password
            })

        # Check for valid response
        if not response or not hasattr(response, 'session') or not hasattr(response, 'user'):
            print("Supabase login failed: Invalid response structure")
            return jsonify({"error": "Unexpected response from Supabase"}), 500

        session = response.session
        user = response.user

        if not session or not user:
            print("Supabase login failed: Missing session or user data")
            return jsonify({"error": "Authentication failed"}), 401

        user_id = user.id
        user_email = user.email
        user_phone = user.phone

        # Check if user exists in the users table
        existing = supabase.table('user').select('user_id').eq('user_id', user_id).execute()
        if not existing.data:
            # Insert user into users table, aligning with signup schema
            print(f"Inserting new user {user_id} into users table")
            supabase.table('user').insert({
                "user_id": user_id,
                "email": user_email,
                "phone": user_phone or '',  # Include phone if available
                "name": user_email.split('@')[0],  # Fallback name
                "join_date": datetime.utcnow().isoformat()
            }).execute()

        print(f"Login successful for user_id: {user_id}")
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
        print("Login error:", str(e))
        error_msg = str(e)
        if "Invalid login credentials" in error_msg:
            return jsonify({"error": "Invalid email/phone or password"}), 401
        if "Email not confirmed" in error_msg:
            return jsonify({"error": "Please verify your email first"}), 403
        return jsonify({"error": f"Login failed: {error_msg}"}), 400
    
#Reset Password
@auth_bp.route('/api/reset-password', methods=['POST'])
def reset_password():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    print("Received reset password request data:", data)

    email = data.get('email')
    new_password = data.get('new_password')
    otp = data.get('otp')

    # Step 1: Request password reset (send OTP)
    if not otp and not new_password:
        if not email:
            return jsonify({"error": "Email is required to reset password"}), 400

        try:
            print(f"Attempting to send OTP to email: {email}")
            # Use reset_password_for_email to specifically send OTP for password reset
            response = supabase.auth.reset_password_for_email(
                email,
                {
                    "redirect_to": "http://your-app.com/reset-password"  # Optional redirect
                }
            )
            
            return jsonify({
                "message": "If an account exists, an OTP has been sent",
                "next_step": "verify_otp",
                "email": email
            }), 200
            
        except Exception as e:
            print(f"Error sending OTP: {str(e)}")
            return jsonify({
                "message": "If an account exists, an OTP has been sent",
                "next_step": "verify_otp",
                "email": email
            }), 200
    
    # Step 2: Verify OTP and update password
    elif email and otp and new_password:
        try:
            # Verify the OTP specifically for password recovery
            print(f"Verifying OTP for email: {email}")
            otp_response = supabase.auth.verify_otp({
                "email": email,
                "token": otp,
                "type": "recovery"  # Critical: must use 'recovery' type for password reset
            })
            
            if not otp_response or not otp_response.user:
                print("OTP verification failed")
                return jsonify({"error": "Invalid or expired OTP"}), 400
            
            # Update password using the authenticated session
            print("OTP verified, updating password...")
            update_response = supabase.auth.update_user({
                "password": new_password
            })
            
            return jsonify({
                "message": "Password updated successfully",
                "email": email
            }), 200
            
        except Exception as e:
            print(f"Error during password reset: {str(e)}")
            return jsonify({"error": str(e)}), 400
    
    else:
        return jsonify({
            "error": "Invalid request parameters",
            "details": "Provide email for OTP request, or email+otp+new_password for reset"
        }), 400