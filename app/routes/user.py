from flask import Blueprint, request, jsonify, current_app
from datetime import datetime
import uuid
import re
from functools import wraps
from supabase import Client

user_bp = Blueprint('user', __name__)

# UUID validation regex
UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            print('Error: Authorization header missing')
            return jsonify({"error": "Authorization header is required"}), 401
        
        try:
            token = auth_header.replace('Bearer ', '')
            supabase: Client = current_app.supabase
            user = supabase.auth.get_user(token)
            if not user:
                print('Error: Invalid or expired token')
                return jsonify({"error": "Invalid or expired token"}), 401
            request.user = user
        except Exception as e:
            print(f'Error verifying token: {str(e)}')
            return jsonify({"error": "Token verification failed", "details": str(e)}), 401
        
        return f(*args, **kwargs)
    return decorated

@user_bp.route('/api/user', methods=['GET'])
@require_auth
def get_user():
    user_id = request.args.get('userId')
    if not user_id:
        print('Validation error: userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    if not UUID_REGEX.match(user_id):
        print(f'Validation error: Invalid UUID format for user_id: "{user_id}"')
        return jsonify({"error": "Invalid userId format, must be UUID"}), 400

    try:
        supabase: Client = current_app.supabase
        print(f'Fetching user data for user_id: {user_id}')
        response = supabase.table('user').select('*').eq('user_id', user_id).execute()
        
        if not response.data:
            print(f'User not found: {user_id}, creating new user')
            new_user = {
                'user_id': user_id,
                'created_at': datetime.utcnow().isoformat()
            }
            supabase.table('user').insert(new_user).execute()
            print(f'Successfully created user with user_id: {user_id}')
            return jsonify(new_user), 201
        
        user_data = response.data[0]
        print(f'User data fetched successfully: {user_data}')
        return jsonify(user_data), 200
        
    except Exception as e:
        print(f'Error fetching user data: {str(e)}')
        return jsonify({
            "error": "Failed to fetch user data",
            "details": str(e)
        }), 500