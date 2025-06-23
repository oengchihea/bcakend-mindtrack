from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime, date, timedelta
import uuid
import re
import base64
from app.routes.auth import auth_required
from supabase import Client, create_client

user_bp = Blueprint('user', __name__)

UUID_REGEX = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

def get_service_role_supabase():
    """Get Supabase client with service role for storage operations"""
    service_role_key = current_app.config.get('SUPABASE_SERVICE_ROLE_KEY')
    if service_role_key:
        return create_client(
            supabase_url=current_app.config['SUPABASE_URL'],
            supabase_key=service_role_key
        )
    return current_app.supabase

def mood_to_emoji(mood, analysis=None):
    if analysis and isinstance(analysis, dict):
        if 'emoji' in analysis and analysis['emoji']:
            return analysis['emoji']
        sentiment = analysis.get('sentiment', '').lower()
        if 'very positive' in sentiment: return '😄'
        elif 'positive' in sentiment: return '😊'
        elif 'neutral' in sentiment: return '😐'
        elif 'negative' in sentiment: return '😔'
        elif 'very negative' in sentiment: return '😢'
    
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

def _validate_user_id(user_id):
    if not user_id or user_id.strip() == '': 
        raise ValueError("User ID cannot be empty")
    
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id in test_user_ids:
        return True
    
    if not UUID_REGEX.match(user_id):
        raise ValueError(f'Invalid userId format: {user_id}')
    return True

def _upload_profile_image(user_id, image_data):
    """Upload profile image to Supabase storage using service role"""
    try:
        if not image_data or not isinstance(image_data, str):
            raise ValueError("Invalid image data: must be a non-empty string")
            
        if not image_data.startswith('data:image/'):
            raise ValueError("Invalid image data format: must start with 'data:image/'")
        
        header, base64_data = image_data.split(',', 1)
        
        if 'jpeg' in header.lower() or 'jpg' in header.lower(): 
            file_ext, content_type = 'jpg', 'image/jpeg'
        elif 'png' in header.lower(): 
            file_ext, content_type = 'png', 'image/png'
        elif 'webp' in header.lower(): 
            file_ext, content_type = 'webp', 'image/webp'
        else: 
            file_ext, content_type = 'jpg', 'image/jpeg'
        
        timestamp = int(datetime.utcnow().timestamp())
        filename = f"profile_{user_id}_{timestamp}.{file_ext}"
        
        image_bytes = base64.b64decode(base64_data)
        
        max_size = 5 * 1024 * 1024  # 5MB
        if len(image_bytes) > max_size:
            raise ValueError(f"Image too large: {len(image_bytes)} bytes (max: {max_size} bytes)")
        
        # Use service role client for storage operations to bypass RLS
        supabase = get_service_role_supabase()
        
        try:
            # Ensure bucket exists
            try:
                buckets = supabase.storage.list_buckets()
                bucket_exists = any(bucket.name == 'profiles' for bucket in buckets)
                
                if not bucket_exists:
                    supabase.storage.create_bucket(
                        'profiles', 
                        options={
                            'public': True,
                            'allowedMimeTypes': ['image/jpeg', 'image/png', 'image/webp'],
                            'fileSizeLimit': 5242880  # 5MB
                        }
                    )
            except Exception:
                # Continue anyway - bucket might exist
                pass
            
            # Upload the file
            supabase.storage.from_('profiles').upload(
                filename, 
                image_bytes,
                file_options={
                    'content-type': content_type,
                    'cache-control': '3600'
                }
            )
            
        except Exception as upload_error:
            # Try simpler upload without file options
            try:
                supabase.storage.from_('profiles').upload(filename, image_bytes)
            except Exception as simple_error:
                raise Exception(f"All upload methods failed. Last error: {str(simple_error)}")
        
        # Get public URL
        try:
            public_url_response = supabase.storage.from_('profiles').get_public_url(filename)
            
            # Handle different response formats
            if hasattr(public_url_response, 'public_url'):
                public_url = public_url_response.public_url
            elif hasattr(public_url_response, 'publicURL'):
                public_url = public_url_response.publicURL
            elif isinstance(public_url_response, str):
                public_url = public_url_response
            elif isinstance(public_url_response, dict):
                public_url = public_url_response.get('publicURL') or public_url_response.get('public_url')
            else:
                # Construct URL manually
                base_url = current_app.config.get('SUPABASE_URL', '').rstrip('/')
                public_url = f"{base_url}/storage/v1/object/public/profiles/{filename}"
            
            return public_url
            
        except Exception:
            # Construct URL manually as fallback
            base_url = current_app.config.get('SUPABASE_URL', '').rstrip('/')
            public_url = f"{base_url}/storage/v1/object/public/profiles/{filename}"
            return public_url
        
    except ValueError as ve:
        raise ve
    except Exception as e:
        raise Exception(f"Image upload failed: {str(e)}")

@user_bp.route('/user', methods=['GET'])
@auth_required
def get_user():
    user_id = request.args.get('userId')
    if not user_id: 
        return jsonify({"error": "userId query parameter is required"}), 400
    
    try: 
        _validate_user_id(user_id)
    except ValueError as e: 
        return jsonify({"error": str(e)}), 400
    
    try:
        supabase = current_app.supabase
        response = supabase.table('user').select('*').eq('user_id', user_id).execute()
        
        if not response.data:
            new_user_data = {
                'user_id': user_id, 
                'created_at': datetime.utcnow().isoformat()
            }
            
            insert_response = supabase.table('user').insert(new_user_data).execute()
            
            if not (hasattr(insert_response, 'data') and insert_response.data):
                error_details = getattr(insert_response, "error", "Unknown error from insert_response")
                return jsonify({"error": "Failed to create user", "details": str(error_details)}), 500
            
            return jsonify(insert_response.data[0]), 201
        
        user_data = response.data[0]
        return jsonify(user_data), 200
        
    except Exception as e:
        return jsonify({"error": "Failed to fetch user data", "details": str(e)}), 500

@user_bp.route('/user/profile', methods=['GET'])
@auth_required
def get_user_profile():
    user_id = request.args.get('userId')
    if not user_id: 
        return jsonify({"error": "userId query parameter is required"}), 400
    
    try: 
        _validate_user_id(user_id)
    except ValueError as e: 
        return jsonify({"error": str(e)}), 400
    
    authenticated_user_id = g.user.id
    
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({"error": "Unauthorized: User ID mismatch"}), 403
    
    try:
        supabase = current_app.supabase
        auth_user_obj = g.user
        display_name, profile_image_url, phone = "User", None, None
        email = getattr(auth_user_obj, 'email', '')
        
        try:
            user_response = supabase.table('user').select('name, email, phone, profile_image_url').eq('user_id', user_id).maybe_single().execute()
            
            if user_response.data:
                user_profile = user_response.data
                
                if user_profile.get('name') and user_profile['name'].strip(): 
                    display_name = user_profile['name'].strip()
                if user_profile.get('email') and user_profile['email'].strip(): 
                    email = user_profile['email'].strip()
                if user_profile.get('phone'): 
                    phone = user_profile['phone']
                if user_profile.get('profile_image_url'): 
                    profile_image_url = user_profile['profile_image_url']
                
        except Exception:
            pass
        
        # Fallback to auth metadata
        if display_name == "User":
            if hasattr(auth_user_obj, 'user_metadata') and auth_user_obj.user_metadata:
                metadata = auth_user_obj.user_metadata
                if 'full_name' in metadata and metadata['full_name']: 
                    display_name = metadata['full_name']
                elif 'name' in metadata and metadata['name']: 
                    display_name = metadata['name']
            elif hasattr(auth_user_obj, 'email') and auth_user_obj.email and display_name == "User":
                email_name = auth_user_obj.email.split('@')[0]
                display_name = email_name.replace('.', ' ').replace('_', ' ').title()
        
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
        return jsonify({"error": "Failed to fetch user profile", "details": str(e)}), 500

@user_bp.route('/user/profile', methods=['PUT'])
@auth_required
def update_user_profile():
    user_id_param = request.args.get('userId')
    if not user_id_param: 
        return jsonify({"error": "userId query parameter is required"}), 400
    
    try: 
        _validate_user_id(user_id_param)
    except ValueError as e: 
        return jsonify({"error": str(e)}), 400
    
    authenticated_user_id = g.user.id

    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id_param not in test_user_ids and authenticated_user_id != user_id_param:
        return jsonify({"error": "Unauthorized: User ID mismatch"}), 403

    try:
        data = request.get_json()
        if not data: 
            return jsonify({"error": "Request body is required"}), 400
        
        # Get authenticated Supabase client for RLS
        supabase = current_app.supabase
        
        update_payload = {}
        
        # Handle name update
        if 'name' in data and data['name'] and data['name'].strip():
            update_payload['name'] = data['name'].strip()
        
        # Handle profile image upload
        if 'profileImage' in data and data['profileImage']:
            try:
                uploaded_image_url = _upload_profile_image(user_id_param, data['profileImage'])
                if uploaded_image_url:
                    update_payload['profile_image_url'] = uploaded_image_url
                else:
                    return jsonify({"error": "Failed to upload profile image - no URL returned"}), 500
            except ValueError as ve:
                return jsonify({"error": f"Image validation error: {str(ve)}"}), 400
            except Exception as ie:
                return jsonify({"error": f"Image upload failed: {str(ie)}"}), 500
        
        if not update_payload:
            return jsonify({"error": "No valid data to update (name or profileImage required)"}), 400
        
        # Add timestamp
        update_payload['updated_at'] = datetime.utcnow().isoformat()
        
        # Check if user exists
        existing_user_check = supabase.table('user').select('user_id').eq('user_id', user_id_param).maybe_single().execute()

        if existing_user_check.data: 
            try:
                update_operation_response = supabase.table('user').update(update_payload).eq('user_id', user_id_param).execute()
                
                # Check for RLS issues
                if not update_operation_response.data:
                    return jsonify({
                        "error": "Profile update blocked by Row Level Security",
                        "details": "The update operation was blocked by RLS policies"
                    }), 403

            except Exception as e_update: 
                return jsonify({"error": f"Database update error: {str(e_update)}"}), 500

            # Re-fetch to verify update
            try:
                fetch_response = supabase.table('user').select('*').eq('user_id', user_id_param).maybe_single().execute()
                
                if not fetch_response.data: 
                    return jsonify({"error": "Critical error: User disappeared after update attempt."}), 500
                
                updated_user_data_from_db = fetch_response.data
                
            except Exception as e_fetch:
                return jsonify({"error": f"Database error after update: {str(e_fetch)}"}), 500
            
            return jsonify({
                'success': True, 
                'message': 'Profile updated successfully',
                'displayName': updated_user_data_from_db.get('name', 'User'),
                'profileImageUrl': updated_user_data_from_db.get('profile_image_url'), 
                'user': updated_user_data_from_db 
            }), 200
            
        else: # Create new user if not existing
            create_payload = {
                'user_id': user_id_param, 
                'created_at': datetime.utcnow().isoformat(), 
                **update_payload
            }
            
            try:
                insert_response = supabase.table('user').insert(create_payload).execute()

                if not (hasattr(insert_response, 'data') and insert_response.data):
                    return jsonify({"error": "Database insert error", "details": "Insert returned no data"}), 500
                
            except Exception as e_insert:
                return jsonify({"error": f"Database insert error: {str(e_insert)}"}), 500
            
            # Re-fetch new user data
            try:
                fetch_response_after_insert = supabase.table('user').select('*').eq('user_id', user_id_param).maybe_single().execute()
                
                if not fetch_response_after_insert.data: 
                    return jsonify({"error": "Critical error: User not found after creation."}), 500
                
                new_user_data_from_db = fetch_response_after_insert.data
                
            except Exception as e_fetch_insert:
                return jsonify({"error": f"Database error after insert: {str(e_fetch_insert)}"}), 500
            
            return jsonify({
                'success': True, 
                'message': 'Profile created successfully as user did not exist.',
                'displayName': new_user_data_from_db.get('name', 'User'),
                'profileImageUrl': new_user_data_from_db.get('profile_image_url'),
                'user': new_user_data_from_db 
            }), 201
            
    except Exception as e:
        return jsonify({"error": "Failed to update user profile", "details": str(e)}), 500

@user_bp.route('/user/mood/calendar', methods=['GET'])
@auth_required
def get_mood_calendar():
    user_id = request.args.get('userId')
    if not user_id: 
        return jsonify({"error": "userId query parameter is required"}), 400
    
    try: 
        _validate_user_id(user_id)
    except ValueError as e: 
        return jsonify({"error": str(e)}), 400
    
    authenticated_user_id = g.user.id
    
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({"error": "Unauthorized: User ID mismatch"}), 403
    
    start_date_str, end_date_str = request.args.get('startDate'), request.args.get('endDate')
    limit_str = request.args.get('limit', '50')
    
    try:
        supabase = current_app.supabase
        query = supabase.table('mood_entries').select('mood_id, mood, created_at, analysis').eq('user_id', user_id).order('created_at', desc=True)
        
        if start_date_str: 
            query = query.gte('created_at', f'{start_date_str}T00:00:00')
        if end_date_str: 
            query = query.lte('created_at', f'{end_date_str}T23:59:59')
        
        try: 
            query = query.limit(int(limit_str))
        except ValueError:
            query = query.limit(50)
        
        response = query.execute()
        
        if response.data is not None:
            date_emojis, processed_entries = {}, []
            for entry in response.data:
                try:
                    created_at_val = entry['created_at']
                    entry_date = datetime.fromisoformat(created_at_val.replace('Z', '+00:00')) if isinstance(created_at_val, str) else created_at_val
                    date_key = entry_date.date().isoformat()
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
                except Exception:
                    pass
            
            return jsonify({
                'dateEmojis': date_emojis, 
                'entries': processed_entries, 
                'totalEntries': len(response.data), 
                'success': True
            }), 200
        else:
            return jsonify({
                'dateEmojis': {}, 
                'entries': [], 
                'totalEntries': 0, 
                'success': True 
            }), 200
            
    except Exception as e:
        return jsonify({"error": "Failed to fetch mood calendar", "details": str(e)}), 500

@user_bp.route('/user/homepage', methods=['GET'])
@auth_required
def get_homepage_data():
    user_id = request.args.get('userId')
    if not user_id: 
        return jsonify({"error": "userId query parameter is required"}), 400
    
    try: 
        _validate_user_id(user_id)
    except ValueError as e: 
        return jsonify({"error": str(e)}), 400
    
    authenticated_user_id = g.user.id
    
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({"error": "Unauthorized: User ID mismatch"}), 403
    
    days_back_str = request.args.get('days', '30')
    
    try:
        supabase = current_app.supabase
        auth_user_obj = g.user
        display_name, profile_image_url = "User", None
        
        try:
            user_profile_response = supabase.table('user').select('name, email, phone, profile_image_url').eq('user_id', user_id).maybe_single().execute()
            if user_profile_response.data:
                user_profile_data = user_profile_response.data
                if user_profile_data.get('name') and user_profile_data['name'].strip(): 
                    display_name = user_profile_data['name'].strip()
                if user_profile_data.get('profile_image_url'): 
                    profile_image_url = user_profile_data['profile_image_url']
        except Exception:
            pass
        
        if display_name == "User" and user_id not in test_user_ids:
            if hasattr(auth_user_obj, 'user_metadata') and auth_user_obj.user_metadata:
                metadata = auth_user_obj.user_metadata
                if 'full_name' in metadata and metadata['full_name']: 
                    display_name = metadata['full_name']
                elif 'name' in metadata and metadata['name']: 
                    display_name = metadata['name']
                elif 'first_name' in metadata and metadata['first_name']:
                    display_name = f"{metadata['first_name']} {metadata.get('last_name', '')}".strip()
            elif hasattr(auth_user_obj, 'email') and auth_user_obj.email:
                display_name = auth_user_obj.email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
        
        end_date_dt = datetime.now()
        try: 
            start_date_dt = end_date_dt - timedelta(days=int(days_back_str))
        except ValueError:
            start_date_dt = end_date_dt - timedelta(days=30)
        
        mood_entries_response = supabase.table('mood_entries').select('mood_id, mood, created_at, analysis').eq('user_id', user_id).gte('created_at', start_date_dt.isoformat()).lte('created_at', end_date_dt.isoformat()).order('created_at', desc=True).execute()
        
        date_emojis, recent_entries = {}, []
        if mood_entries_response.data:
            for entry in mood_entries_response.data:
                try:
                    created_at_val = entry['created_at']
                    entry_date = datetime.fromisoformat(created_at_val.replace('Z', '+00:00')) if isinstance(created_at_val, str) else created_at_val
                    date_key = entry_date.date().isoformat()
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
                except Exception:
                    pass
        
        today_iso, today_mood = date.today().isoformat(), None
        today_mood_response = supabase.table('mood_entries').select('mood_id, mood, created_at, analysis, content').eq('user_id', user_id).gte('created_at', f'{today_iso}T00:00:00').lte('created_at', f'{today_iso}T23:59:59').order('created_at', desc=True).limit(1).execute()
        
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
        
        total_mood_entries, unique_mood_dates = len(recent_entries), len(date_emojis)
        current_month_year = datetime.now().strftime('%B %Y')
        
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
                'totalEntries': total_mood_entries, 
                'uniqueDates': unique_mood_dates
            },
            'todayMood': today_mood,
            'calendar': {
                'currentMonth': current_month_year,
                'dateRange': {
                    'startDate': start_date_dt.date().isoformat(), 
                    'endDate': end_date_dt.date().isoformat()
                }
            },
            'success': True
        }), 200
        
    except Exception as e:
        return jsonify({"error": "Failed to fetch homepage data", "details": str(e)}), 500

@user_bp.route('/health', methods=['GET'])
def health_check_user():
    return jsonify({"status": "healthy", "message": "User API is running"}), 200