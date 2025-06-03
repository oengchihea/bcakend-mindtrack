from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, date, timedelta
import uuid # Not strictly used in the provided snippet but good to keep if planned
import re
from functools import wraps
from supabase import Client # Ensure Client is imported if type hinting

user_bp = Blueprint('user', __name__) # The blueprint name is 'user'

# UUID validation regex - Make sure this is defined before _validate_user_id
UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

# --- Helper Function: _validate_user_id ---
# Ensure this function is defined at the module level, BEFORE any routes that use it.
def _validate_user_id(user_id_to_validate: str):
    """Validate user ID format - allows specific test IDs."""
    if not user_id_to_validate or not user_id_to_validate.strip():
        current_app.logger.warning('[_validate_user_id] Validation failed: User ID cannot be empty')
        raise ValueError("User ID cannot be empty")
    
    # Allow specific test user IDs (useful during development)
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id_to_validate in test_user_ids:
        current_app.logger.info(f'[_validate_user_id] Allowing test user ID: {user_id_to_validate}')
        return True # Valid test user ID
    
    # Validate UUID format for actual user IDs
    if not UUID_REGEX.match(user_id_to_validate):
        current_app.logger.warning(f'[_validate_user_id] Validation failed: Invalid UUID format for user_id: "{user_id_to_validate}"')
        raise ValueError(f'Invalid userId format: {user_id_to_validate}')
    
    current_app.logger.info(f'[_validate_user_id] User ID format validated successfully: {user_id_to_validate}')
    return True # Valid UUID format

# --- Decorator: require_auth ---
def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            current_app.logger.warning('[@require_auth] Authorization header missing')
            return jsonify({"error": "Authorization header is required"}), 401
        
        token = None
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            current_app.logger.warning('[@require_auth] Token missing or malformed header')
            return jsonify({"error": "Token is missing or malformed"}), 401
        
        current_app.logger.info(f'[@require_auth] Attempting to verify token (last 10 chars): ...{token[-10:]}')
        
        try:
            supabase_service_client: Client = current_app.supabase_client
            user_response = supabase_service_client.auth.get_user(token)
            
            if not user_response or not hasattr(user_response, 'user') or not user_response.user:
                current_app.logger.warning(f'[@require_auth] Token verification failed. Invalid user or token. Response: {user_response}')
                return jsonify({"error": "Invalid or expired token"}), 401
            
            request.current_user_from_token = user_response.user 
            current_app.logger.info(f"[@require_auth] Token verified successfully for user: {user_response.user.id}")
            
        except Exception as e:
            current_app.logger.error(f'[@require_auth] Exception during token verification: {str(e)}', exc_info=True)
            return jsonify({"error": "Token verification failed", "details": str(e)}), 401
        
        return f(*args, **kwargs)
    return decorated

# --- Helper Function: mood_to_emoji ---
# Ensure this is also defined before routes if used directly by them, or ensure it's correctly scoped.
def mood_to_emoji(mood, analysis=None):
    if analysis and isinstance(analysis, dict):
        if 'emoji' in analysis and analysis['emoji']:
            return analysis['emoji']
        sentiment = analysis.get('sentiment', '').lower()
        if 'very positive' in sentiment: return '😄'
        if 'positive' in sentiment: return '😊'
        if 'neutral' in sentiment: return '😐'
        if 'negative' in sentiment: return '😔'
        if 'very negative' in sentiment: return '😢'
    
    mood_lower = mood.lower() if mood else ''
    mood_emoji_map = {
        'happy': '😊', 'very happy': '😄', 'ecstatic': '😄', 'joyful': '😊', 'excited': '😊',
        'content': '😊', 'peaceful': '😊', 'grateful': '😊', 'sad': '😔', 'very sad': '😢',
        'depressed': '😢', 'down': '😔', 'disappointed': '😔', 'angry': '😡', 'furious': '😡',
        'frustrated': '😠', 'anxious': '😰', 'worried': '😰', 'stressed': '😰',
        'overwhelmed': '😰', 'neutral': '😐', 'okay': '😐', 'fine': '😐', 'alright': '😐',
        'calm': '😐', 'tired': '😴', 'exhausted': '😴', 'energetic': '😊',
    }
    if mood_lower in mood_emoji_map: return mood_emoji_map[mood_lower]
    for mood_key, emoji in mood_emoji_map.items():
        if mood_key in mood_lower: return emoji
    return '😐'

# --- Routes ---
@user_bp.route('/api/user', methods=['GET'])
@require_auth
def get_user():
    user_id_param = request.args.get('userId')
    if not user_id_param:
        current_app.logger.warning('[get_user] userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    auth_user_obj = request.current_user_from_token
    current_app.logger.info(f"[get_user] Authenticated user ID from token: {auth_user_obj.id}")

    test_user_ids = ['user123', 'test-user', 'demo-user']
    if auth_user_obj.id != user_id_param and user_id_param not in test_user_ids:
        current_app.logger.warning(f"[get_user] Mismatch: Token user ID ({auth_user_obj.id}) vs requested user ID ({user_id_param})")
        return jsonify({"error": "Unauthorized to fetch data for this user"}), 403
    
    try:
        _validate_user_id(user_id_param) # Calling the helper function
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        supabase_service_client: Client = current_app.supabase_client
        current_app.logger.info(f'[get_user] Fetching user data from DB for user_id: {user_id_param}')
        response = supabase_service_client.table('user').select('*').eq('user_id', user_id_param).maybe_single().execute()
        
        if not response.data:
            current_app.logger.info(f'[get_user] User not found in DB: {user_id_param}.')
            return jsonify({"error": "User not found in database"}), 404
        
        user_data = response.data
        current_app.logger.info(f'[get_user] User data fetched successfully: {user_data}')
        return jsonify(user_data), 200
        
    except Exception as e:
        current_app.logger.error(f'[get_user] Error fetching user data: {str(e)}', exc_info=True)
        return jsonify({"error": "Failed to fetch user data", "details": str(e)}), 500

@user_bp.route('/api/user/profile', methods=['GET'])
@require_auth
def get_user_profile():
    user_id_param = request.args.get('userId')
    if not user_id_param:
        current_app.logger.warning('[@get_user_profile] userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    authenticated_user = request.current_user_from_token 
    current_app.logger.info(f"[@get_user_profile] Authenticated user from token: {authenticated_user.id}")
    current_app.logger.info(f"[@get_user_profile] Requested profile for userId param: {user_id_param}")

    try:
        _validate_user_id(user_id_param) # Calling the helper function
    except ValueError as e: # Catch the specific error from _validate_user_id
        current_app.logger.warning(f"[@get_user_profile] Validation error for user_id_param '{user_id_param}': {str(e)}")
        return jsonify({"error": str(e)}), 400 # Return 400 for bad request

    test_user_ids = ['user123', 'test-user', 'demo-user']
    if authenticated_user.id != user_id_param and user_id_param not in test_user_ids:
        current_app.logger.warning(
            f'[@get_user_profile] Authorization error: Token user ID ({authenticated_user.id}) '
            f'does not match requested profile ID ({user_id_param}).'
        )
        return jsonify({"error": "Unauthorized: You can only fetch your own profile."}), 403

    try:
        supabase_service_client: Client = current_app.supabase_client
        display_name = "User" 

        current_app.logger.info(f'[@get_user_profile] Fetching profile from DB for user_id: {user_id_param}')
        db_user_response = supabase_service_client.table('user').select('name, email, phone').eq('user_id', user_id_param).maybe_single().execute()

        if db_user_response.data:
            user_profile_from_db = db_user_response.data
            current_app.logger.info(f'[@get_user_profile] Profile from DB: {user_profile_from_db}')
            if user_profile_from_db.get('name') and user_profile_from_db['name'].strip():
                display_name = user_profile_from_db['name'].strip()
        else:
            current_app.logger.info(f'[@get_user_profile] No profile found in DB for user_id: {user_id_param}. Will use auth metadata.')

        if display_name == "User" and hasattr(authenticated_user, 'user_metadata') and authenticated_user.user_metadata:
            auth_metadata = authenticated_user.user_metadata
            current_app.logger.info(f'[@get_user_profile] Using auth metadata: {auth_metadata}')
            if auth_metadata.get('name') and auth_metadata['name'].strip():
                display_name = auth_metadata['name'].strip()
            elif auth_metadata.get('full_name') and auth_metadata['full_name'].strip():
                 display_name = auth_metadata['full_name'].strip()
        
        if display_name == "User" and authenticated_user.email:
            email_name_part = authenticated_user.email.split('@')[0]
            display_name = email_name_part.replace('.', ' ').replace('_', ' ').title()
            current_app.logger.info(f'[@get_user_profile] Using name derived from email: {display_name}')
        
        current_app.logger.info(f'[@get_user_profile] Final display name for {user_id_param}: {display_name}')
        
        return jsonify({
            'userId': user_id_param,
            'displayName': display_name,
            'userName': display_name, 
            'email': authenticated_user.email or (db_user_response.data.get('email') if db_user_response.data else ''),
            'success': True
        }), 200

    except Exception as e:
        current_app.logger.error(f'[@get_user_profile] Error fetching user profile: {str(e)}', exc_info=True)
        return jsonify({"error": "Failed to fetch user profile", "details": str(e)}), 500

@user_bp.route('/api/user/mood/calendar', methods=['GET'])
@require_auth
def get_mood_calendar():
    user_id_param = request.args.get('userId')
    authenticated_user = request.current_user_from_token
    current_app.logger.info(f"[@get_mood_calendar] Auth user: {authenticated_user.id}, Requested for: {user_id_param}")
    # TODO: Add validation for user_id_param using _validate_user_id
    # TODO: Add check: if authenticated_user.id != user_id_param (and not test user) -> return 403
    # TODO: Use current_app.supabase_client for DB queries
    # ... (rest of your logic) ...
    return jsonify({"message": "Mood calendar placeholder for " + str(user_id_param)}), 200

@user_bp.route('/api/user/homepage', methods=['GET'])
@require_auth
def get_homepage_data():
    user_id_param = request.args.get('userId')
    authenticated_user = request.current_user_from_token
    current_app.logger.info(f"[@get_homepage_data] Auth user: {authenticated_user.id}, Requested for: {user_id_param}")
    # TODO: Add validation for user_id_param using _validate_user_id
    # TODO: Add check: if authenticated_user.id != user_id_param (and not test user) -> return 403
    # TODO: Use current_app.supabase_client for DB queries
    # ... (rest of your logic) ...
    return jsonify({"message": "Homepage data placeholder for " + str(user_id_param)}), 200