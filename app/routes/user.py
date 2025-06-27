from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime, date, timedelta, timezone
import uuid
import re
import base64
import logging
from supabase import Client, create_client
from typing import Optional, Dict, Any, List
from app.routes.auth import auth_required

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Blueprint
user_bp = Blueprint('user', __name__)

# UUID validation regex
UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

def get_service_role_supabase() -> Client:
    """
    Get Supabase client with service role for storage operations.

    Returns:
        Client: Supabase client with service role credentials.
    """
    service_role_key = current_app.config.get('SUPABASE_SERVICE_ROLE_KEY')
    if service_role_key:
        return create_client(
            supabase_url=current_app.config['SUPABASE_URL'],
            supabase_key=service_role_key
        )
    logger.warning("Using default Supabase client for storage operations")
    return current_app.supabase

def mood_to_emoji(mood: str, analysis: Optional[Dict] = None) -> str:
    """
    Map mood to emoji based on mood string or analysis data.

    Args:
        mood (str): The mood string to map.
        analysis (Optional[Dict]): Analysis data containing sentiment or emoji.

    Returns:
        str: Corresponding emoji for the mood.
    """
    if analysis and isinstance(analysis, dict):
        if 'emoji' in analysis and analysis['emoji']:
            return analysis['emoji']
        sentiment = analysis.get('sentiment', '').lower()
        sentiment_map = {
            'very positive': '😄',
            'positive': '😊',
            'neutral': '😐',
            'negative': '😔',
            'very negative': '😢'
        }
        for key, emoji in sentiment_map.items():
            if key in sentiment:
                return emoji

    mood_lower = mood.lower() if mood else ''
    mood_emoji_map = {
        'happy': '😊', 'very happy': '😄', 'ecstatic': '😄', 'joyful': '😊', 'excited': '😊',
        'content': '😊', 'peaceful': '😊', 'grateful': '😊', 'sad': '😔', 'very sad': '😢',
        'depressed': '😢', 'down': '😔', 'disappointed': '😔', 'angry': '😡', 'furious': '😡',
        'frustrated': '😠', 'anxious': '😰', 'worried': '😰', 'stressed': '😰',
        'overwhelmed': '😰', 'neutral': '😐', 'okay': '😐', 'fine': '😐', 'alright': '😐',
        'calm': '😐', 'tired': '😴', 'exhausted': '😴', 'energetic': '😊'
    }
    return mood_emoji_map.get(mood_lower, '😐')

def validate_user_id(user_id: str) -> bool:
    """
    Validate user ID format, allowing test IDs for development.

    Args:
        user_id (str): The user ID to validate.

    Returns:
        bool: True if valid, raises ValueError if invalid.
    """
    if not user_id or user_id.strip() == '':
        raise ValueError("User ID cannot be empty")
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id in test_user_ids:
        logger.debug(f"Validated test user ID: {user_id}")
        return True
    if not UUID_REGEX.match(user_id):
        raise ValueError(f"Invalid userId format: {user_id}")
    logger.debug(f"Validated user ID: {user_id}")
    return True

def upload_profile_image(user_id: str, image_data: str) -> str:
    """
    Upload profile image to Supabase storage and return public URL.

    Args:
        user_id (str): The user ID for naming the image file.
        image_data (str): Base64-encoded image data.

    Returns:
        str: Public URL of the uploaded image.

    Raises:
        ValueError: If image data is invalid or exceeds size limit.
        Exception: If upload or URL retrieval fails.
    """
    try:
        if not image_data or not isinstance(image_data, str):
            raise ValueError("Invalid image data: must be a non-empty string")
        if not image_data.startswith('data:image/'):
            raise ValueError("Invalid image data format: must start with 'data:image/'")

        header, base64_data = image_data.split(',', 1)
        mime_map = {
            'image/jpeg': ('jpg', 'image/jpeg'),
            'image/jpg': ('jpg', 'image/jpeg'),
            'image/png': ('png', 'image/png'),
            'image/webp': ('webp', 'image/webp')
        }
        file_ext, content_type = 'jpg', 'image/jpeg'
        for mime, (ext, ctype) in mime_map.items():
            if mime in header.lower():
                file_ext, content_type = ext, ctype
                break

        image_bytes = base64.b64decode(base64_data)
        max_size = 5 * 1024 * 1024  # 5MB
        if len(image_bytes) > max_size:
            raise ValueError(f"Image too large: {len(image_bytes)} bytes (max: {max_size} bytes)")

        timestamp = int(datetime.now(timezone.utc).timestamp())
        filename = f"profile_{user_id}_{timestamp}.{file_ext}"

        supabase = get_service_role_supabase()
        try:
            buckets = supabase.storage.list_buckets()
            if not any(bucket.name == 'profiles' for bucket in buckets):
                supabase.storage.create_bucket(
                    'profiles',
                    options={'public': True, 'allowedMimeTypes': list(mime_map.values()), 'fileSizeLimit': max_size}
                )
        except Exception as e:
            logger.warning(f"Failed to verify/create bucket: {e}")

        supabase.storage.from_('profiles').upload(
            filename,
            image_bytes,
            file_options={'content-type': content_type, 'cache-control': '3600'}
        )

        public_url = supabase.storage.from_('profiles').get_public_url(filename)
        if isinstance(public_url, dict):
            public_url = public_url.get('public_url') or public_url.get('publicURL')
        if not public_url:
            base_url = current_app.config.get('SUPABASE_URL', '').rstrip('/')
            public_url = f"{base_url}/storage/v1/object/public/profiles/{filename}"

        logger.info(f"Uploaded profile image for user {user_id}: {public_url}")
        return public_url
    except ValueError as ve:
        logger.warning(f"Image validation failed for user {user_id}: {ve}")
        raise
    except Exception as e:
        logger.error(f"Image upload failed for user {user_id}: {e}")
        raise Exception(f"Image upload failed: {str(e)}")

@user_bp.route('/user', methods=['GET'])
@auth_required
def get_user():
    """
    Retrieve user data by user ID.

    Query Parameters:
        userId (str): The ID of the user to retrieve.

    Returns:
        JSON response with user data or error message.
    """
    user_id = request.args.get('userId')
    if not user_id:
        logger.warning("Missing userId query parameter")
        return jsonify({"error": "userId query parameter is required", "code": "MISSING_USER_ID"}), 400

    try:
        validate_user_id(user_id)
    except ValueError as e:
        logger.warning(f"Invalid user ID: {e}")
        return jsonify({"error": str(e), "code": "INVALID_USER_ID"}), 400

    try:
        supabase = current_app.supabase
        response = supabase.table('user').select('*').eq('user_id', user_id).execute()
        if not response.data:
            new_user_data = {
                'user_id': user_id,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            insert_response = supabase.table('user').insert(new_user_data).execute()
            if not insert_response.data:
                logger.error(f"Failed to create user {user_id}")
                return jsonify({"error": "Failed to create user", "code": "CREATE_FAILED"}), 500
            logger.info(f"Created new user {user_id}")
            return jsonify(insert_response.data[0]), 201

        logger.info(f"Fetched user data for {user_id}")
        return jsonify(response.data[0]), 200
    except Exception as e:
        logger.error(f"Failed to fetch user data for {user_id}: {e}")
        return jsonify({"error": "Failed to fetch user data", "code": "FETCH_FAILED", "details": str(e)}), 500

@user_bp.route('/user/profile', methods=['GET'])
@auth_required
def get_user_profile():
    """
    Retrieve user profile information.

    Query Parameters:
        userId (str): The ID of the user to retrieve.

    Returns:
        JSON response with user profile data or error message.
    """
    user_id = request.args.get('userId')
    if not user_id:
        logger.warning("Missing userId query parameter")
        return jsonify({"error": "userId query parameter is required", "code": "MISSING_USER_ID"}), 400

    try:
        validate_user_id(user_id)
    except ValueError as e:
        logger.warning(f"Invalid user ID: {e}")
        return jsonify({"error": str(e), "code": "INVALID_USER_ID"}), 400

    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        logger.warning(f"Unauthorized access attempt by {authenticated_user_id} for user {user_id}")
        return jsonify({"error": "Unauthorized: User ID mismatch", "code": "UNAUTHORIZED"}), 403

    try:
        supabase = current_app.supabase
        auth_user_obj = g.user
        display_name, profile_image_url, phone, email = "User", None, None, getattr(auth_user_obj, 'email', '')

        user_response = supabase.table('user').select('name, email, phone, profile_image_url').eq('user_id', user_id).maybe_single().execute()
        if user_response.data:
            user_profile = user_response.data
            display_name = user_profile.get('name', display_name).strip() or display_name
            email = user_profile.get('email', email).strip() or email
            phone = user_profile.get('phone')
            profile_image_url = user_profile.get('profile_image_url')

        if display_name == "User":
            metadata = getattr(auth_user_obj, 'user_metadata', {})
            display_name = (
                metadata.get('full_name') or
                metadata.get('name') or
                (auth_user_obj.email.split('@')[0].replace('.', ' ').replace('_', ' ').title() if auth_user_obj.email else display_name)
            )

        logger.info(f"Fetched profile for user {user_id}")
        return jsonify({
            'userId': user_id,
            'displayName': display_name,
            'userName': display_name,
            'profileImageUrl': profile_image_url,
            'email': email,
            'phone': phone,
            'success': True
        }), 200
    except Exception as e:
        logger.error(f"Failed to fetch user profile for {user_id}: {e}")
        return jsonify({"error": "Failed to fetch user profile", "code": "FETCH_FAILED", "details": str(e)}), 500

@user_bp.route('/user/profile', methods=['PUT'])
@auth_required
def update_user_profile():
    """
    Update user profile information.

    Query Parameters:
        userId (str): The ID of the user to update.

    Returns:
        JSON response with updated profile data or error message.
    """
    user_id = request.args.get('userId')
    if not user_id:
        logger.warning("Missing userId query parameter")
        return jsonify({"error": "userId query parameter is required", "code": "MISSING_USER_ID"}), 400

    try:
        validate_user_id(user_id)
    except ValueError as e:
        logger.warning(f"Invalid user ID: {e}")
        return jsonify({"error": str(e), "code": "INVALID_USER_ID"}), 400

    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        logger.warning(f"Unauthorized access attempt by {authenticated_user_id} for user {user_id}")
        return jsonify({"error": "Unauthorized: User ID mismatch", "code": "UNAUTHORIZED"}), 403

    try:
        data = request.get_json()
        if not data:
            logger.warning("Missing request body")
            return jsonify({"error": "Request body is required", "code": "INVALID_REQUEST"}), 400

        supabase = current_app.supabase
        update_payload = {}
        if data.get('name') and data['name'].strip():
            update_payload['name'] = data['name'].strip()[:255]

        if data.get('profileImage'):
            try:
                update_payload['profile_image_url'] = upload_profile_image(user_id, data['profileImage'])
            except ValueError as ve:
                logger.warning(f"Image validation failed: {ve}")
                return jsonify({"error": str(ve), "code": "INVALID_IMAGE"}), 400
            except Exception as e:
                logger.error(f"Image upload failed: {e}")
                return jsonify({"error": "Image upload failed", "code": "UPLOAD_FAILED", "details": str(e)}), 500

        if not update_payload:
            logger.warning("No valid data to update")
            return jsonify({"error": "Name or profileImage required", "code": "INVALID_DATA"}), 400

        update_payload['updated_at'] = datetime.now(timezone.utc).isoformat()
        existing_user = supabase.table('user').select('user_id').eq('user_id', user_id).maybe_single().execute()

        if existing_user.data:
            update_response = supabase.table('user').update(update_payload).eq('user_id', user_id).execute()
            if not update_response.data:
                logger.error("Profile update blocked by RLS")
                return jsonify({"error": "Profile update blocked by Row Level Security", "code": "RLS_BLOCKED"}), 403

            fetch_response = supabase.table('user').select('*').eq('user_id', user_id).maybe_single().execute()
            if not fetch_response.data:
                logger.error("User not found after update")
                return jsonify({"error": "User not found after update", "code": "NOT_FOUND"}), 500

            logger.info(f"Updated profile for user {user_id}")
            return jsonify({
                'success': True,
                'message': 'Profile updated successfully',
                'displayName': fetch_response.data.get('name', 'User'),
                'profileImageUrl': fetch_response.data.get('profile_image_url'),
                'user': fetch_response.data
            }), 200
        else:
            create_payload = {'user_id': user_id, 'created_at': datetime.now(timezone.utc).isoformat(), **update_payload}
            insert_response = supabase.table('user').insert(create_payload).execute()
            if not insert_response.data:
                logger.error("Failed to create user")
                return jsonify({"error": "Failed to create user", "code": "CREATE_FAILED"}), 500

            fetch_response = supabase.table('user').select('*').eq('user_id', user_id).maybe_single().execute()
            if not fetch_response.data:
                logger.error("User not found after creation")
                return jsonify({"error": "User not found after creation", "code": "NOT_FOUND"}), 500

            logger.info(f"Created profile for user {user_id}")
            return jsonify({
                'success': True,
                'message': 'Profile created successfully',
                'displayName': fetch_response.data.get('name', 'User'),
                'profileImageUrl': fetch_response.data.get('profile_image_url'),
                'user': fetch_response.data
            }), 201
    except Exception as e:
        logger.error(f"Failed to update user profile for {user_id}: {e}")
        return jsonify({"error": "Failed to update user profile", "code": "UPDATE_FAILED", "details": str(e)}), 500

@user_bp.route('/user/mood/calendar', methods=['GET'])
@auth_required
def get_mood_calendar():
    """
    Retrieve mood calendar data for a user.

    Query Parameters:
        userId (str): The ID of the user.
        startDate (str, optional): Start date in YYYY-MM-DD format.
        endDate (str, optional): End date in YYYY-MM-DD format.
        limit (int, optional): Maximum number of entries to return (default: 50).

    Returns:
        JSON response with mood calendar data or error message.
    """
    user_id = request.args.get('userId')
    if not user_id:
        logger.warning("Missing userId query parameter")
        return jsonify({"error": "userId query parameter is required", "code": "MISSING_USER_ID"}), 400

    try:
        validate_user_id(user_id)
    except ValueError as e:
        logger.warning(f"Invalid user ID: {e}")
        return jsonify({"error": str(e), "code": "INVALID_USER_ID"}), 400

    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        logger.warning(f"Unauthorized access attempt by {authenticated_user_id} for user {user_id}")
        return jsonify({"error": "Unauthorized: User ID mismatch", "code": "UNAUTHORIZED"}), 403

    start_date_str, end_date_str = request.args.get('startDate'), request.args.get('endDate')
    limit = min(request.args.get('limit', 50, type=int), 100)

    try:
        supabase = current_app.supabase
        query = supabase.table('mood_entries').select('mood_id, mood, created_at, analysis').eq('user_id', user_id).order('created_at', desc=True)
        if start_date_str:
            query = query.gte('created_at', f'{start_date_str}T00:00:00')
        if end_date_str:
            query = query.lte('created_at', f'{end_date_str}T23:59:59')
        query = query.limit(limit)

        response = query.execute()
        date_emojis, processed_entries = {}, []
        for entry in response.data or []:
            try:
                created_at_val = entry['created_at']
                entry_date = datetime.fromisoformat(created_at_val.replace('Z', '+00:00')).date() if isinstance(created_at_val, str) else created_at_val.date()
                date_key = entry_date.isoformat()
                emoji = mood_to_emoji(entry['mood'], entry.get('analysis'))

                if date_key not in date_emojis:
                    date_emojis[date_key] = emoji

                processed_entries.append({
                    'id': entry['mood_id'],
                    'mood': entry['mood'],
                    'emoji': emoji,
                    'date': entry_date.isoformat(),
                    'dateOnly': date_key,
                    'analysis': entry.get('analysis', {})
                })
            except Exception as e:
                logger.warning(f"Failed to process mood entry {entry.get('mood_id')}: {e}")

        logger.info(f"Fetched mood calendar for user {user_id} with {len(processed_entries)} entries")
        return jsonify({
            'dateEmojis': date_emojis,
            'entries': processed_entries,
            'totalEntries': len(processed_entries),
            'success': True
        }), 200
    except Exception as e:
        logger.error(f"Failed to fetch mood calendar for {user_id}: {e}")
        return jsonify({"error": "Failed to fetch mood calendar", "code": "FETCH_FAILED", "details": str(e)}), 500

@user_bp.route('/user/homepage', methods=['GET'])
@auth_required
def get_homepage_data():
    """
    Retrieve homepage data for a user, including profile and recent mood entries.

    Query Parameters:
        userId (str): The ID of the user.
        days (int, optional): Number of days to fetch mood entries (default: 30).

    Returns:
        JSON response with homepage data or error message.
    """
    user_id = request.args.get('userId')
    if not user_id:
        logger.warning("Missing userId query parameter")
        return jsonify({"error": "userId query parameter is required", "code": "MISSING_USER_ID"}), 400

    try:
        validate_user_id(user_id)
    except ValueError as e:
        logger.warning(f"Invalid user ID: {e}")
        return jsonify({"error": str(e), "code": "INVALID_USER_ID"}), 400

    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        logger.warning(f"Unauthorized access attempt by {authenticated_user_id} for user {user_id}")
        return jsonify({"error": "Unauthorized: User ID mismatch", "code": "UNAUTHORIZED"}), 403

    days_back = min(request.args.get('days', 30, type=int), 90)

    try:
        supabase = current_app.supabase
        auth_user_obj = g.user
        display_name, profile_image_url = "User", None

        user_profile_response = supabase.table('user').select('name, email, phone, profile_image_url').eq('user_id', user_id).maybe_single().execute()
        if user_profile_response.data:
            user_profile_data = user_profile_response.data
            display_name = user_profile_data.get('name', display_name).strip() or display_name
            profile_image_url = user_profile_data.get('profile_image_url')

        if display_name == "User" and user_id not in test_user_ids:
            metadata = getattr(auth_user_obj, 'user_metadata', {})
            display_name = (
                metadata.get('full_name') or
                metadata.get('name') or
                (auth_user_obj.email.split('@')[0].replace('.', ' ').replace('_', ' ').title() if auth_user_obj.email else display_name)
            )

        end_date_dt = datetime.now(timezone.utc)
        start_date_dt = end_date_dt - timedelta(days=days_back)
        mood_entries_response = supabase.table('mood_entries').select('mood_id, mood, created_at, analysis').eq('user_id', user_id).gte('created_at', start_date_dt.isoformat()).lte('created_at', end_date_dt.isoformat()).order('created_at', desc=True).execute()

        date_emojis, recent_entries = {}, []
        for entry in mood_entries_response.data or []:
            try:
                created_at_val = entry['created_at']
                entry_date = datetime.fromisoformat(created_at_val.replace('Z', '+00:00')).date() if isinstance(created_at_val, str) else created_at_val.date()
                date_key = entry_date.isoformat()
                emoji = mood_to_emoji(entry['mood'], entry.get('analysis'))

                if date_key not in date_emojis:
                    date_emojis[date_key] = emoji

                recent_entries.append({
                    'id': entry['mood_id'],
                    'mood': entry['mood'],
                    'emoji': emoji,
                    'date': entry_date.isoformat(),
                    'dateOnly': date_key,
                    'analysis': entry.get('analysis', {})
                })
            except Exception as e:
                logger.warning(f"Failed to process mood entry {entry.get('mood_id')}: {e}")

        today_iso = date.today().isoformat()
        today_mood_response = supabase.table('mood_entries').select('mood_id, mood, created_at, analysis, content').eq('user_id', user_id).gte('created_at', f'{today_iso}T00:00:00').lte('created_at', f'{today_iso}T23:59:59').order('created_at', desc=True).limit(1).execute()

        today_mood = None
        if today_mood_response.data and today_mood_response.data[0]:
            entry = today_mood_response.data[0]
            today_mood = {
                'id': entry['mood_id'],
                'mood': entry['mood'],
                'emoji': mood_to_emoji(entry['mood'], entry.get('analysis')),
                'content': entry.get('content'),
                'createdAt': entry['created_at'],
                'analysis': entry.get('analysis', {})
            }

        logger.info(f"Fetched homepage data for user {user_id} with {len(recent_entries)} mood entries")
        return jsonify({
            'user': {
                'userId': user_id,
                'displayName': display_name,
                'userName': display_name,
                'profileImageUrl': profile_image_url,
                'email': getattr(auth_user_obj, 'email', ''),
                'greeting': f"Hello {display_name}"
            },
            'moodData': {
                'dateEmojis': date_emojis,
                'recentEntries': recent_entries[:10],
                'totalEntries': len(recent_entries),
                'uniqueDates': len(date_emojis)
            },
            'todayMood': today_mood,
            'calendar': {
                'currentMonth': datetime.now(timezone.utc).strftime('%B %Y'),
                'dateRange': {
                    'startDate': start_date_dt.date().isoformat(),
                    'endDate': end_date_dt.date().isoformat()
                }
            },
            'success': True
        }), 200
    except Exception as e:
        logger.error(f"Failed to fetch homepage data for {user_id}: {e}")
        return jsonify({"error": "Failed to fetch homepage data", "code": "FETCH_FAILED", "details": str(e)}), 500

@user_bp.route('/health', methods=['GET'])
def health_check_user():
    """Health check endpoint for user service."""
    logger.info("User health check accessed")
    return jsonify({
        "status": "healthy",
        "message": "User API is running",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200