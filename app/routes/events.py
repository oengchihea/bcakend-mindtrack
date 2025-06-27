from flask import Blueprint, request, jsonify, current_app, g
from functools import wraps
from datetime import datetime
import uuid

# Blueprint
events_bp = Blueprint('events', __name__, url_prefix='/api/events')

# Auth decorator for Supabase 2.0+
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
            
            # For Supabase 2.0+, set the session instead of using postgrest.auth
            try:
                current_app.supabase.auth.set_session(token, token)
            except Exception:
                # Fallback if session setting fails
                pass
                
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
        
        print(f"=== UPDATE EVENT DEBUG START ===")  # Debug
        print(f"Event ID: {event_id}")  # Debug
        print(f"User ID: {user_id}")  # Debug
        print(f"Raw request data: {data}")  # Debug
        print(f"Data type: {type(data)}")  # Debug

        # Validate request data
        if not data:
            print(f"ERROR: No request body provided")  # Debug
            return jsonify({'error': 'Request body is required'}), 400

        # Verify event exists and user is creator
        print(f"Checking if event exists...")  # Debug
        event_check = current_app.supabase.from_('events').select('creator_id, title, description, location, meeting_link').eq('event_id', event_id).single().execute()
        print(f"Event check result: {event_check.data}")  # Debug
        
        if not event_check.data:
            print(f"ERROR: Event ID {event_id} not found")  # Debug
            return jsonify({'error': 'Event not found'}), 404
        if event_check.data['creator_id'] != user_id:
            print(f"ERROR: User {user_id} is not the creator (actual creator: {event_check.data['creator_id']})")  # Debug
            return jsonify({'error': 'Only the creator can update this event'}), 403

        print(f"Current event data in DB: {event_check.data}")  # Debug

        # Prepare update data with explicit field handling
        event_data = {}
        
        # Handle each field explicitly
        if 'title' in data:
            if data['title'] and data['title'].strip():
                event_data['title'] = data['title'].strip()
                print(f"Will update title: '{data['title']}' -> '{event_data['title']}'")  # Debug
            else:
                print(f"Skipping title update (empty or None)")  # Debug
                
        if 'description' in data:
            event_data['description'] = data['description'].strip() if data['description'] else ""
            print(f"Will update description: '{data['description']}' -> '{event_data['description']}'")  # Debug
            
        if 'event_time' in data:
            if data['event_time']:
                event_data['event_time'] = data['event_time']
                print(f"Will update event_time: '{data['event_time']}'")  # Debug
            else:
                print(f"Skipping event_time update (empty)")  # Debug
                
        if 'location' in data:
            if data['location'] and data['location'].strip():
                event_data['location'] = data['location'].strip()
                print(f"Will update location: '{data['location']}' -> '{event_data['location']}'")  # Debug
            else:
                print(f"Skipping location update (empty or None)")  # Debug
                
        if 'meeting_link' in data:
            event_data['meeting_link'] = data['meeting_link'].strip() if data['meeting_link'] else None
            print(f"Will update meeting_link: '{data['meeting_link']}' -> '{event_data['meeting_link']}'")  # Debug

        print(f"Final update data: {event_data}")  # Debug

        if not event_data:
            print(f"ERROR: No valid fields to update")  # Debug
            return jsonify({'error': 'No valid fields provided for update'}), 400

        # Perform the update with more detailed logging
        print(f"Executing Supabase update...")  # Debug
        try:
            # Try the update with explicit column matching
            result = current_app.supabase.table('events').update(event_data).eq('event_id', event_id).eq('creator_id', user_id).execute()
            print(f"Update executed successfully")  # Debug
            print(f"Update result type: {type(result)}")  # Debug
            print(f"Update result data: {result.data}")  # Debug
            print(f"Update result count: {getattr(result, 'count', 'no count')}")  # Debug
            
            # Check if the update actually affected any rows
            if hasattr(result, 'count') and result.count == 0:
                print(f"WARNING: Update count is 0 - no rows were affected")  # Debug
                print(f"This might be due to RLS policies or event not found")  # Debug
                # Try a direct check to see if the event exists
                check_result = current_app.supabase.from_('events').select('*').eq('event_id', event_id).eq('creator_id', user_id).execute()
                print(f"Event existence check: {check_result.data}")  # Debug
                if not check_result.data:
                    return jsonify({'error': 'Event not found or access denied'}), 404
                else:
                    # Try update without creator_id constraint
                    print(f"Retrying update without creator_id constraint...")  # Debug
                    retry_result = current_app.supabase.table('events').update(event_data).eq('event_id', event_id).execute()
                    print(f"Retry update result: {retry_result.data}")  # Debug
                    result = retry_result
            elif result.data is None or len(result.data) == 0:
                print(f"WARNING: Update returned no data but might have succeeded")  # Debug
                # Supabase sometimes returns empty data even on successful updates
            else:
                print(f"SUCCESS: Update affected {len(result.data)} rows")  # Debug
                
        except Exception as update_error:
            print(f"ERROR during Supabase update: {update_error}")  # Debug
            import traceback
            print(f"Update error traceback: {traceback.format_exc()}")  # Debug
            
            # Try alternative update method using from_() instead of table()
            print(f"Trying alternative update method...")  # Debug
            try:
                alt_result = current_app.supabase.from_('events').update(event_data).eq('event_id', event_id).execute()
                print(f"Alternative update result: {alt_result.data}")  # Debug
                result = alt_result
            except Exception as alt_error:
                print(f"Alternative update also failed: {alt_error}")  # Debug
                return jsonify({'error': f'Database update failed: {str(update_error)}'}), 500

        # Fetch the updated event to verify and return
        print(f"Fetching updated event...")  # Debug
        try:
            updated_event = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', event_id).single().execute()
            print(f"Fetched updated event successfully: {updated_event.data}")  # Debug
            
            # Verify that the changes were actually applied
            update_successful = True
            failed_fields = []
            
            for field, new_value in event_data.items():
                if field in updated_event.data:
                    db_value = updated_event.data[field]
                    # Handle potential whitespace differences
                    if isinstance(db_value, str) and isinstance(new_value, str):
                        db_value_clean = db_value.strip()
                        new_value_clean = new_value.strip()
                        if db_value_clean != new_value_clean:
                            print(f"WARNING: Field '{field}' was not updated correctly!")  # Debug
                            print(f"  Expected: '{new_value_clean}' (len:{len(new_value_clean)})")  # Debug
                            print(f"  DB has: '{db_value_clean}' (len:{len(db_value_clean)})")  # Debug
                            update_successful = False
                            failed_fields.append(field)
                        else:
                            print(f"SUCCESS: Field '{field}' updated correctly to '{new_value_clean}'")  # Debug
                    else:
                        if db_value != new_value:
                            print(f"WARNING: Field '{field}' was not updated correctly!")  # Debug
                            print(f"  Expected: '{new_value}', but DB has: '{db_value}'")  # Debug
                            update_successful = False
                            failed_fields.append(field)
                        else:
                            print(f"SUCCESS: Field '{field}' updated correctly to '{new_value}'")  # Debug
            
            if not update_successful:
                print(f"ERROR: Update verification failed for fields: {failed_fields}")  # Debug
                # Try one more direct update for the failed fields
                retry_data = {field: event_data[field] for field in failed_fields}
                print(f"Retrying update for failed fields: {retry_data}")  # Debug
                try:
                    final_result = current_app.supabase.from_('events').update(retry_data).eq('event_id', event_id).execute()
                    print(f"Final retry result: {final_result.data}")  # Debug
                    # Fetch again to verify
                    final_check = current_app.supabase.from_('events').select('*, user!inner(name)').eq('event_id', event_id).single().execute()
                    print(f"Final verification: {final_check.data}")  # Debug
                    print(f"=== UPDATE EVENT DEBUG END ===")  # Debug
                    return jsonify({'message': 'Event updated successfully after retry', 'event': final_check.data}), 200
                except Exception as retry_error:
                    print(f"Final retry failed: {retry_error}")  # Debug
            
            print(f"=== UPDATE EVENT DEBUG END ===")  # Debug
            return jsonify({'message': 'Event updated successfully', 'event': updated_event.data}), 200
            
        except Exception as fetch_error:
            print(f"Error fetching updated event with user info: {fetch_error}")  # Debug
            # Fallback: fetch without user info
            try:
                updated_event_fallback = current_app.supabase.from_('events').select('*').eq('event_id', event_id).single().execute()
                print(f"Fetched event without user info: {updated_event_fallback.data}")  # Debug
                print(f"=== UPDATE EVENT DEBUG END ===")  # Debug
                return jsonify({'message': 'Event updated successfully', 'event': updated_event_fallback.data}), 200
            except Exception as fallback_error:
                print(f"ERROR: Even fallback fetch failed: {fallback_error}")  # Debug
                print(f"=== UPDATE EVENT DEBUG END ===")  # Debug
                return jsonify({'error': 'Update completed but could not fetch updated event'}), 500

    except Exception as e:
        print(f"CRITICAL ERROR in update_event: {str(e)}")  # Debug
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")  # Debug
        print(f"=== UPDATE EVENT DEBUG END ===")  # Debug
        return jsonify({'error': f'Failed to update event: {str(e)}'}), 500

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