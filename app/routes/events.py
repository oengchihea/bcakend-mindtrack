from flask import Blueprint, request, jsonify, current_app, g
from functools import wraps
from datetime import datetime, timezone
import uuid
import logging
from typing import Callable
from app.routes.auth import auth_required

# Initialize logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize Blueprint
events_bp = Blueprint('events', __name__, url_prefix='/events')

@events_bp.route('/', methods=['GET'])
@auth_required
def get_all_events():
    """Retrieve all events with user information."""
    try:
        limit = min(request.args.get('limit', 50, type=int), 100)
        offset = request.args.get('offset', 0, type=int)
        result = current_app.supabase.from_('events').select('*, user!inner(name)').order('event_time').range(offset, offset + limit - 1).execute()
        logger.info(f"Fetched {len(result.data)} events")
        return jsonify({"events": result.data, "count": len(result.data)}), 200
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        return jsonify({"error": str(e), "code": "FETCH_FAILED"}), 500

@events_bp.route('/<string:event_id>', methods=['GET'])
@auth_required
def get_event_by_id(event_id: str):
    """Retrieve a specific event by ID."""
    try:
        result = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', event_id).single().execute()
        if result.data:
            logger.info(f"Fetched event {event_id}")
            return jsonify({"event": result.data}), 200
        logger.warning(f"Event {event_id} not found")
        return jsonify({"error": "Event not found", "code": "NOT_FOUND"}), 404
    except Exception as e:
        logger.error(f"Failed to fetch event {event_id}: {e}")
        return jsonify({"error": str(e), "code": "FETCH_FAILED"}), 500

@events_bp.route('/my-events', methods=['GET'])
@auth_required
def get_my_events():
    """Retrieve events created by the authenticated user."""
    try:
        user_id = g.user.id
        limit = min(request.args.get('limit', 50, type=int), 100)
        offset = request.args.get('offset', 0, type=int)
        result = current_app.supabase.from_('events').select('*, user!inner(name)').eq('creator_id', user_id).order('event_time').range(offset, offset + limit - 1).execute()
        logger.info(f"Fetched {len(result.data)} events for user {user_id}")
        return jsonify({"events": result.data, "count": len(result.data)}), 200
    except Exception as e:
        logger.error(f"Failed to fetch user events: {e}")
        return jsonify({"error": str(e), "code": "FETCH_FAILED"}), 500

@events_bp.route('/create', methods=['POST'])
@auth_required
def create_event():
    """Create a new event."""
    try:
        data = request.get_json()
        if not data or not data.get('title'):
            logger.warning("Missing required fields")
            return jsonify({"error": "Title is required", "code": "MISSING_FIELDS"}), 400

        user_id = g.user.id
        event_data = {
            'creator_id': user_id,
            'title': data['title'][:255],
            'description': data.get('description', '')[:1000],
            'event_time': data.get('event_time'),
            'location': data.get('location', '')[:255],
            'meeting_link': data.get('meeting_link', '')[:255]
        }

        result = current_app.supabase.table('events').insert(event_data).execute()
        if result.data:
            created_event = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', result.data[0]['event_id']).single().execute()
            logger.info(f"Created event {result.data[0]['event_id']} for user {user_id}")
            return jsonify({"message": "Event created successfully", "event": created_event.data}), 201
        logger.error("Failed to create event")
        return jsonify({"error": "Failed to create event", "code": "CREATE_FAILED"}), 500
    except Exception as e:
        logger.error(f"Error creating event: {e}")
        return jsonify({"error": str(e), "code": "CREATE_FAILED"}), 500

@events_bp.route('/update/<string:event_id>', methods=['PUT'])
@auth_required
def update_event(event_id: str):
    """Update an existing event (only by creator)."""
    try:
        user_id = g.user.id
        data = request.get_json()
        if not data:
            logger.warning("Missing request body")
            return jsonify({"error": "Request body required", "code": "INVALID_REQUEST"}), 400

        event_check = current_app.supabase.from_('events').select('creator_id').eq('event_id', event_id).single().execute()
        if not event_check.data:
            logger.warning(f"Event {event_id} not found")
            return jsonify({"error": "Event not found", "code": "NOT_FOUND"}), 404
        if event_check.data['creator_id'] != user_id:
            logger.warning(f"User {user_id} not authorized to update event {event_id}")
            return jsonify({"error": "Only the creator can update this event", "code": "UNAUTHORIZED"}), 403

        event_data = {
            'title': data.get('title', '')[:255],
            'description': data.get('description', '')[:1000],
            'event_time': data.get('event_time'),
            'location': data.get('location', '')[:255],
            'meeting_link': data.get('meeting_link', '')[:255]
        }
        event_data = {k: v for k, v in event_data.items() if v is not None}

        result = current_app.supabase.table('events').update(event_data).eq('event_id', event_id).execute()
        if result.data:
            updated_event = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', event_id).single().execute()
            logger.info(f"Updated event {event_id} for user {user_id}")
            return jsonify({"message": "Event updated successfully", "event": updated_event.data}), 200
        logger.error(f"Failed to update event {event_id}")
        return jsonify({"error": "Failed to update event", "code": "UPDATE_FAILED"}), 500
    except Exception as e:
        logger.error(f"Error updating event {event_id}: {e}")
        return jsonify({"error": str(e), "code": "UPDATE_FAILED"}), 500

@events_bp.route('/delete/<string:event_id>', methods=['DELETE'])
@auth_required
def delete_event(event_id: str):
    """Delete an event and its registrations (only by creator)."""
    try:
        user_id = g.user.id
        event_check = current_app.supabase.from_('events').select('creator_id').eq('event_id', event_id).single().execute()
        if not event_check.data:
            logger.warning(f"Event {event_id} not found")
            return jsonify({"error": "Event not found", "code": "NOT_FOUND"}), 404
        if event_check.data['creator_id'] != user_id:
            logger.warning(f"User {user_id} not authorized to delete event {event_id}")
            return jsonify({"error": "Only the creator can delete this event", "code": "UNAUTHORIZED"}), 403

        current_app.supabase.table('eventRegistration').delete().eq('event_id', event_id).execute()
        result = current_app.supabase.table('events').delete().eq('event_id', event_id).execute()
        if result.data:
            logger.info(f"Deleted event {event_id} for user {user_id}")
            return jsonify({"message": "Event deleted successfully"}), 200
        logger.error(f"Failed to delete event {event_id}")
        return jsonify({"error": "Failed to delete event", "code": "DELETE_FAILED"}), 500
    except Exception as e:
        logger.error(f"Error deleting event {event_id}: {e}")
        return jsonify({"error": str(e), "code": "DELETE_FAILED"}), 500

@events_bp.route('/register', methods=['POST'])
@auth_required
def register_to_event():
    """Register a user for an event."""
    try:
        data = request.get_json()
        user_id = g.user.id
        event_id = data.get('event_id')
        if not event_id:
            logger.warning("Missing event_id")
            return jsonify({"error": "Event ID required", "code": "MISSING_FIELDS"}), 400

        event_check = current_app.supabase.from_('events').select('event_id').eq('event_id', event_id).single().execute()
        if not event_check.data:
            logger.warning(f"Event {event_id} not found")
            return jsonify({"error": "Event not found", "code": "NOT_FOUND"}), 404

        registration_check = current_app.supabase.from_('eventRegistration').select('registration_id').eq('user_id', user_id).eq('event_id', event_id).execute()
        if registration_check.data:
            logger.warning(f"User {user_id} already registered for event {event_id}")
            return jsonify({"error": "You are already registered for this event", "code": "ALREADY_REGISTERED"}), 400

        registration = {
            'registration_id': str(uuid.uuid4()),
            'user_id': user_id,
            'event_id': event_id,
            'registered_at': datetime.now(timezone.utc).isoformat(),
            'status': data.get('status', 'registered')
        }

        result = current_app.supabase.table('eventRegistration').insert(registration).execute()
        if result.data:
            logger.info(f"User {user_id} registered for event {event_id}")
            return jsonify({"message": "User registered successfully"}), 201
        logger.error(f"Failed to register user {user_id} for event {event_id}")
        return jsonify({"error": "Failed to register", "code": "REGISTER_FAILED"}), 500
    except Exception as e:
        logger.error(f"Error registering for event: {e}")
        return jsonify({"error": str(e), "code": "REGISTER_FAILED"}), 500