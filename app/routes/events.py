from flask import Blueprint, request, jsonify, current_app, g
from functools import wraps
from datetime import datetime
import uuid

# Blueprint
events_bp = Blueprint('events', __name__, url_prefix='/api/events')

# Auth decorator for Supabase
def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization required'}), 401

        try:
            token = auth_header.split(' ')[1]
            user = current_app.supabase.auth.get_user(token)
            if not user.user:
                return jsonify({'error': 'Invalid token'}), 401

            g.current_user = user.user
            g.access_token = token
            current_app.supabase.postgrest.auth(token)
        except Exception as e:
            print(f"Authentication error: {str(e)}")  # Debug
            return jsonify({'error': 'Authentication failed'}), 401

        return f(*args, **kwargs)
    return decorated

@events_bp.route('/', methods=['GET'])
@auth_required
def get_all_events():
    try:
        result = current_app.supabase.from_('events').select('*, user!inner(name)').order('event_time').execute()
        print(f"Get all events response: {result.data}")  # Debug
        return jsonify({'events': result.data}), 200
    except Exception as e:
        print(f"Get all events error: {str(e)}")  # Debug
        try:
            fallback_result = current_app.supabase.from_('events').select('*').order('event_time').execute()
            print(f"Get all events fallback response: {fallback_result.data}")  # Debug
            return jsonify({'events': fallback_result.data}), 200
        except Exception as fe:
            print(f"Get all events fallback error: {fe}")  # Debug
            return jsonify({'error': str(e)}), 500

@events_bp.route('/<string:event_id>', methods=['GET'])
@auth_required
def get_event_by_id(event_id):
    try:
        result = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', event_id).single().execute()
        print(f"Get event by ID response: {result.data}")  # Debug
        if result.data:
            return jsonify({'event': result.data}), 200
        return jsonify({'error': 'Event not found'}), 404
    except Exception as e:
        print(f"Get event by ID error: {str(e)}")  # Debug
        try:
            fallback_result = current_app.supabase.from_('events').select('*').eq('event_id', event_id).single().execute()
            print(f"Get event by ID fallback response: {fallback_result.data}")  # Debug
            if fallback_result.data:
                return jsonify({'event': fallback_result.data}), 200
            return jsonify({'error': 'Event not found'}), 404
        except Exception as fe:
            print(f"Get event by ID fallback error: {fe}")  # Debug
            return jsonify({'error': str(e)}), 500

@events_bp.route('/my-events', methods=['GET'])
@auth_required
def get_my_events():
    try:
        user_id = g.current_user.id
        result = current_app.supabase.from_('events').select('*, user!inner(name)').eq('creator_id', user_id).order('event_time').execute()
        print(f"Get my events response: {result.data}")  # Debug
        return jsonify({'events': result.data}), 200
    except Exception as e:
        print(f"Get my events error: {str(e)}")  # Debug
        try:
            fallback_result = current_app.supabase.from_('events').select('*').eq('creator_id', user_id).order('event_time').execute()
            print(f"Get my events fallback response: {fallback_result.data}")  # Debug
            return jsonify({'events': fallback_result.data}), 200
        except Exception as fe:
            print(f"Get my events fallback error: {fe}")  # Debug
            return jsonify({'error': str(e)}), 500

@events_bp.route('/create', methods=['POST'])
@auth_required
def create_event():
    try:
        data = request.get_json()
        user_id = g.current_user.id
        print(f"Create event data: {data}")  # Debug

        event_data = {
            'creator_id': user_id,
            'title': data['title'],
            'description': data.get('description'),
            'event_time': data.get('event_time'),
            'location': data.get('location'),
            'meeting_link': data.get('meeting_link'),
        }

        result = current_app.supabase.table('events').insert(event_data).execute()
        print(f"Create event response: {result.data}")  # Debug

        if result.data:
            try:
                created_event = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', result.data[0]['event_id']).single().execute()
                print(f"Created event with username: {created_event.data}")  # Debug
                return jsonify({'message': 'Event created successfully', 'event': created_event.data}), 201
            except Exception as e:
                print(f"Fetch created event error: {str(e)}")  # Debug
                return jsonify({'message': 'Event created successfully', 'event': result.data[0]}), 201
        return jsonify({'error': 'Failed to create event'}), 500
    except Exception as e:
        print(f"Create event error: {str(e)}")  # Debug
        return jsonify({'error': str(e)}), 500

@events_bp.route('/update/<string:event_id>', methods=['PUT'])
@auth_required
def update_event(event_id):
    try:
        user_id = g.current_user.id
        data = request.get_json()
        print(f"Update event data: {data}")  # Debug

        # Verify event exists and user is creator
        event_check = current_app.supabase.from_('events').select('creator_id').eq('event_id', event_id).single().execute()
        if not event_check.data:
            print(f"Update event error: Event ID {event_id} not found")  # Debug
            return jsonify({'error': 'Event not found'}), 404
        if event_check.data['creator_id'] != user_id:
            print(f"Update event error: User {user_id} is not the creator")  # Debug
            return jsonify({'error': 'Only the creator can update this event'}), 403

        event_data = {
            'title': data.get('title'),
            'description': data.get('description'),
            'event_time': data.get('event_time'),
            'location': data.get('location'),
            'meeting_link': data.get('meeting_link'),
        }
        # Remove None values
        event_data = {k: v for k, v in event_data.items() if v is not None}

        result = current_app.supabase.table('events').update(event_data).eq('event_id', event_id).execute()
        print(f"Update event response: {result.data}")  # Debug

        if result.data:
            updated_event = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', event_id).single().execute()
            return jsonify({'message': 'Event updated successfully', 'event': updated_event.data}), 200
        return jsonify({'error': 'Failed to update event'}), 500
    except Exception as e:
        print(f"Update event error: {str(e)}")  # Debug
        return jsonify({'error': str(e)}), 500

@events_bp.route('/delete/<string:event_id>', methods=['DELETE'])
@auth_required
def delete_event(event_id):
    try:
        user_id = g.current_user.id

        # Verify event exists and user is creator
        event_check = current_app.supabase.from_('events').select('creator_id').eq('event_id', event_id).single().execute()
        if not event_check.data:
            print(f"Delete event error: Event ID {event_id} not found")  # Debug
            return jsonify({'error': 'Event not found'}), 404
        if event_check.data['creator_id'] != user_id:
            print(f"Delete event error: User {user_id} is not the creator")  # Debug
            return jsonify({'error': 'Only the creator can delete this event'}), 403

        # Delete related registrations first
        current_app.supabase.table('eventRegistration').delete().eq('event_id', event_id).execute()
        # Delete the event
        result = current_app.supabase.table('events').delete().eq('event_id', event_id).execute()
        print(f"Delete event response: {result.data}")  # Debug

        if result.data:
            return jsonify({'message': 'Event deleted successfully'}), 200
        return jsonify({'error': 'Failed to delete event'}), 500
    except Exception as e:
        print(f"Delete event error: {str(e)}")  # Debug
        return jsonify({'error': str(e)}), 500

@events_bp.route('/register', methods=['POST'])
@auth_required
def register_to_event():
    try:
        data = request.get_json()
        user_id = getattr(g.current_user, "id", None) or g.current_user.get("id", None)
        print(f"[register_to_event] g.current_user: {g.current_user}, resolved user_id: {user_id}")

        event_id = data.get('event_id')
        print(f"Register event data: {data}")  # Debug

        # Verify event_id exists
        event_check = current_app.supabase.from_('events').select('event_id').eq('event_id', event_id).single().execute()
        if not event_check.data:
            print(f"Register event error: Event ID {event_id} not found")  # Debug
            return jsonify({'error': 'Event not found'}), 404

        # Check for existing registration
        registration_check = current_app.supabase.from_('eventRegistration').select('registration_id').eq('user_id', user_id).eq('event_id', event_id).execute()
        if registration_check.data:
            print(f"Register event error: User {user_id} already registered for event {event_id}")  # Debug
            return jsonify({'error': 'You are already registered for this event'}), 400

        registration = {
            'registration_id': str(uuid.uuid4()),
            'user_id': user_id,
            'event_id': event_id,
            'registered_at': datetime.utcnow().isoformat(),
            'status': data.get('status', 'registered')
        }

        try:
            print(f"Attempting insert into eventRegistration with: {registration}")
            result = current_app.supabase.table('eventRegistration').insert(registration).execute()
            print(f"Register event response: {result.data}")  # Debug
        except Exception as e:
            print(f"Supabase insert error: {str(e)}")  # Debug
            if 'users' in str(e).lower() and 'user' not in str(e).lower():
                print("Error indicates a 'users' table reference, but only 'user' exists. Check Supabase configuration.")
            return jsonify({'error': f"Failed to register: {str(e)}"}), 500

        if result.data:
            return jsonify({'message': 'User registered successfully'}), 201
        return jsonify({'error': 'Failed to register'}), 500
    except Exception as e:
        print(f"Register event error: {str(e)}")  # Debug
        return jsonify({'error': f"Failed to register: {str(e)}"}), 500