from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, date, timedelta
import uuid # Not strictly used in the provided snippet but good to keep if planned
import re
import base64
from functools import wraps
from supabase import Client

user_bp = Blueprint('user', __name__) # The blueprint name is 'user'

# UUID validation regex
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

def mood_to_emoji(mood, analysis=None):
    if analysis and isinstance(analysis, dict):
        if 'emoji' in analysis and analysis['emoji']:
            return analysis['emoji']
        sentiment = analysis.get('sentiment', '').lower()
        if 'very positive' in sentiment:
            return '😄'
        elif 'positive' in sentiment:
            return '😊'
        elif 'neutral' in sentiment:
            return '😐'
        elif 'negative' in sentiment:
            return '😔'
        elif 'very negative' in sentiment:
            return '😢'
    
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
    """Validate user ID - allow test IDs during development"""
    if not user_id or user_id.strip() == '':
        raise ValueError("User ID cannot be empty")
    
    # Allow test user IDs during development
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id in test_user_ids:
        print(f'⚠️ Using test user ID: {user_id}')
        return True
    
    # Validate UUID format for production
    if not UUID_REGEX.match(user_id):
        print(f'❌ Invalid UUID format for user_id: "{user_id}"')
        raise ValueError(f'Invalid userId format: {user_id}')
    
    return True

@user_bp.route('/api/user', methods=['GET'])
@require_auth
def get_user():
    user_id = request.args.get('userId')
    if not user_id:
        print('Validation error: userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    
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

@user_bp.route('/api/user/profile', methods=['GET'])
@require_auth
def get_user_profile():
    """Get user profile information including display name for homepage greeting."""
    
    user_id = request.args.get('userId')
    if not user_id:
        print('Validation error: userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Skip user ID mismatch check for test users
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids:
        # Verify the authenticated user matches the requested user
        if request.user.user.id != user_id:
            print(f'Authorization error: User ID mismatch. Auth: {request.user.user.id}, Requested: {user_id}')
            return jsonify({"error": "Unauthorized: User ID mismatch"}), 403

    try:
        supabase: Client = current_app.supabase
        
        # Get user data from Supabase auth
        auth_user = request.user.user
        
        # Default fallback name
        display_name = "User"
        
        # Query the actual 'name' field from your user table schema
        try:
            print(f'Fetching user profile from user table for user_id: {user_id}')
            user_response = supabase.table('user')\
                .select('name, email, phone')\
                .eq('user_id', user_id)\
                .execute()
            
            if user_response.data and len(user_response.data) > 0:
                user_profile = user_response.data[0]
                print(f'Found user profile in database: {user_profile}')
                
                # Use the 'name' field from your actual schema
                if user_profile.get('name') and user_profile['name'].strip():
                    display_name = user_profile['name'].strip()
                    print(f'Using name from database: {display_name}')
                else:
                    print('Name field is empty in database')
            else:
                print(f'No user profile found in database for user_id: {user_id}')
                
        except Exception as db_error:
            print(f'Error fetching from user table: {db_error}')
        
        # Fallback: Try to get name from Supabase auth metadata
        if display_name == "User":
            print('Falling back to auth metadata for name')
            if hasattr(auth_user, 'user_metadata') and auth_user.user_metadata:
                metadata = auth_user.user_metadata
                if 'full_name' in metadata and metadata['full_name']:
                    display_name = metadata['full_name']
                    print(f'Using full_name from auth metadata: {display_name}')
                elif 'name' in metadata and metadata['name']:
                    display_name = metadata['name']
                    print(f'Using name from auth metadata: {display_name}')
                elif 'first_name' in metadata and metadata['first_name']:
                    first_name = metadata['first_name']
                    last_name = metadata.get('last_name', '')
                    display_name = f"{first_name} {last_name}".strip()
                    print(f'Using first/last name from auth metadata: {display_name}')
        
        # Final fallback: Extract from email
        if display_name == "User":
            print('Final fallback: extracting name from email')
            if hasattr(auth_user, 'email') and auth_user.email:
                email_name = auth_user.email.split('@')[0]
                # Convert email username to a more readable format
                display_name = email_name.replace('.', ' ').replace('_', ' ').title()
                print(f'Using name from email: {display_name}')
        
        print(f'Final display name for {user_id}: {display_name}')
        
        return jsonify({
            'userId': user_id,
            'displayName': display_name,
            'userName': display_name,  # Add userName field for Flutter compatibility
            'email': getattr(auth_user, 'email', ''),
            'success': True
        }), 200
        
    except Exception as e:
        print(f'Error fetching user profile: {str(e)}')
        return jsonify({
            "error": "Failed to fetch user profile",
            "details": str(e)
        }), 500

@user_bp.route('/api/user/mood/calendar', methods=['GET'])
@require_auth
def get_mood_calendar():
    """Get mood entries formatted for calendar display with emojis."""
    
    user_id = request.args.get('userId')
    if not user_id:
        print('Validation error: userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Skip user ID mismatch check for test users
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids:
        # Verify the authenticated user matches the requested user
        if request.user.user.id != user_id:
            print(f'Authorization error: User ID mismatch. Auth: {request.user.user.id}, Requested: {user_id}')
            return jsonify({"error": "Unauthorized: User ID mismatch"}), 403

    # Optional date range parameters
    start_date = request.args.get('startDate')  # Format: YYYY-MM-DD
    end_date = request.args.get('endDate')      # Format: YYYY-MM-DD
    limit = request.args.get('limit', 50)       # Default to 50 entries

    try:
        supabase: Client = current_app.supabase
        
        # Build query for mood_entries table
        query = supabase.table('mood_entries')\
            .select('mood_id, mood, created_at, analysis')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)
        
        # Add date filters if provided
        if start_date:
            query = query.gte('created_at', f'{start_date}T00:00:00')
        if end_date:
            query = query.lte('created_at', f'{end_date}T23:59:59')
        
        # Add limit
        query = query.limit(int(limit))
        
        response = query.execute()
        
        if response.data is not None:
            # Process entries to create date-emoji mapping
            date_emojis = {}
            
            for entry in response.data:
                try:
                    # Parse the created_at timestamp
                    created_at = entry['created_at']
                    if isinstance(created_at, str):
                        entry_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        entry_date = created_at
                    
                    # Normalize to date only (remove time component)
                    date_key = entry_date.date().isoformat()
                    
                    # Get emoji for this mood entry
                    emoji = mood_to_emoji(entry['mood'], entry.get('analysis'))
                    
                    # Store the emoji for this date
                    # If multiple entries exist for the same date, this will use the latest one
                    # due to the DESC ordering
                    if date_key not in date_emojis:
                        date_emojis[date_key] = emoji
                
                except Exception as e:
                    print(f'Error processing entry {entry.get("mood_id")}: {str(e)}')
                    continue
            
            # Also return the raw entries for additional processing if needed
            processed_entries = []
            for entry in response.data:
                try:
                    created_at = entry['created_at']
                    if isinstance(created_at, str):
                        entry_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        entry_date = created_at
                    
                    processed_entries.append({
                        'id': entry['mood_id'],
                        'mood': entry['mood'],
                        'emoji': mood_to_emoji(entry['mood'], entry.get('analysis')),
                        'date': entry_date.isoformat(),
                        'dateOnly': entry_date.date().isoformat(),
                        'analysis': entry.get('analysis', {})
                    })
                except Exception as e:
                    print(f'Error processing entry for list: {str(e)}')
                    continue
            
            print(f'Mood calendar fetched for {user_id}: {len(date_emojis)} unique dates')
            
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
        print(f'Error fetching mood calendar: {str(e)}')
        return jsonify({
            "error": "Failed to fetch mood calendar",
            "details": str(e)
        }), 500

@user_bp.route('/api/user/homepage', methods=['GET'])
@require_auth
def get_homepage_data():
    """Get comprehensive homepage data including user greeting and mood calendar."""
    
    user_id = request.args.get('userId')
    if not user_id:
        print('Validation error: userId query parameter is missing')
        return jsonify({"error": "userId query parameter is required"}), 400

    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Skip user ID mismatch check for test users
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids:
        # Verify the authenticated user matches the requested user
        if request.user.user.id != user_id:
            print(f'Authorization error: User ID mismatch. Auth: {request.user.user.id}, Requested: {user_id}')
            return jsonify({"error": "Unauthorized: User ID mismatch"}), 403

    # Optional parameters
    days_back = request.args.get('days', 30)  # Default to 30 days of mood data
    
    try:
        supabase: Client = current_app.supabase
        
        # Get user profile data
        auth_user = request.user.user
        display_name = "Chi Hea"  # Default name for test users
        
        # Try to get name from user table
        try:
            user_response = supabase.table('user')\
                .select('name, email, phone')\
                .eq('user_id', user_id)\
                .execute()
            
            if user_response.data and len(user_response.data) > 0:
                user_profile = user_response.data[0]
                if user_profile.get('name') and user_profile['name'].strip():
                    display_name = user_profile['name'].strip()
        except Exception as e:
            print(f'Error fetching user profile: {e}')
        
        # Fallback to auth metadata for real users
        if display_name == "Chi Hea" and user_id not in test_user_ids:
            if hasattr(auth_user, 'user_metadata') and auth_user.user_metadata:
                metadata = auth_user.user_metadata
                if 'full_name' in metadata and metadata['full_name']:
                    display_name = metadata['full_name']
                elif 'name' in metadata and metadata['name']:
                    display_name = metadata['name']
                elif 'first_name' in metadata and metadata['first_name']:
                    first_name = metadata['first_name']
                    last_name = metadata.get('last_name', '')
                    display_name = f"{first_name} {last_name}".strip()
        
        # Final fallback from email for real users
        if display_name == "Chi Hea" and user_id not in test_user_ids and hasattr(auth_user, 'email') and auth_user.email:
            email_name = auth_user.email.split('@')[0]
            display_name = email_name.replace('.', ' ').replace('_', ' ').title()
        
        # Get mood calendar data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(days_back))
        
        mood_response = supabase.table('mood_entries')\
            .select('mood_id, mood, created_at, analysis')\
            .eq('user_id', user_id)\
            .gte('created_at', start_date.isoformat())\
            .lte('created_at', end_date.isoformat())\
            .order('created_at', desc=True)\
            .execute()
        
        # Process mood entries to create date-emoji mapping
        date_emojis = {}
        recent_entries = []

        if mood_response.data:
            for entry in mood_response.data:
                try:
                    # Parse the created_at timestamp
                    created_at = entry['created_at']
                    if isinstance(created_at, str):
                        entry_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        entry_date = created_at
                    
                    # Normalize to date only
                    date_key = entry_date.date().isoformat()
                    
                    # Get emoji from analysis or mood
                    emoji = mood_to_emoji(entry['mood'], entry.get('analysis'))
                    
                    # Store emoji for this date (latest entry wins due to DESC ordering)
                    if date_key not in date_emojis:
                        date_emojis[date_key] = emoji
                        print(f'✅ Added emoji {emoji} for date {date_key}')
                    
                    # Add to recent entries
                    recent_entries.append({
                        'id': entry['mood_id'],
                        'mood': entry['mood'],
                        'emoji': emoji,
                        'date': entry_date.isoformat(),
                        'dateOnly': date_key,
                        'analysis': entry.get('analysis', {})
                    })
                
                except Exception as e:
                    print(f'❌ Error processing mood entry: {e}')
                    continue

        print(f'✅ Processed mood data: {len(date_emojis)} unique dates, {len(recent_entries)} total entries')
        
        # Get today's mood specifically
        today = date.today().isoformat()
        today_mood = None
        
        today_response = supabase.table('mood_entries')\
            .select('mood_id, mood, created_at, analysis, content')\
            .eq('user_id', user_id)\
            .gte('created_at', f'{today}T00:00:00')\
            .lte('created_at', f'{today}T23:59:59')\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
        
        if today_response.data and len(today_response.data) > 0:
            entry = today_response.data[0]
            today_mood = {
                'id': entry['mood_id'],
                'mood': entry['mood'],
                'emoji': mood_to_emoji(entry['mood'], entry.get('analysis')),
                'content': entry['content'],
                'createdAt': entry['created_at'],
                'analysis': entry.get('analysis', {})
            }
        
        # Calculate some basic stats
        total_entries = len(recent_entries)
        unique_dates = len(date_emojis)
        
        # Get current month info
        current_month = datetime.now().strftime('%B %Y')
        
        print(f'Homepage data prepared for {display_name}: {total_entries} entries, {unique_dates} unique dates')
        
        return jsonify({
            'user': {
                'userId': user_id,
                'displayName': display_name,
                'userName': display_name,
                'email': getattr(auth_user, 'email', ''),
                'greeting': f"Hello {display_name}"
            },
            'moodData': {
                'dateEmojis': date_emojis,
                'recentEntries': recent_entries[:10],  # Last 10 entries
                'totalEntries': total_entries,
                'uniqueDates': unique_dates
            },
            'todayMood': today_mood,
            'calendar': {
                'currentMonth': current_month,
                'dateRange': {
                    'startDate': start_date.date().isoformat(),
                    'endDate': end_date.date().isoformat()
                }
            },
            'success': True
        }), 200

    except Exception as e:
        print(f'Error fetching homepage data: {str(e)}')
        return jsonify({
            "error": "Failed to fetch homepage data",
            "details": str(e)
        }), 500
