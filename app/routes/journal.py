import os
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest import APIError

journal_bp = Blueprint('journal_bp', __name__)

def get_auth_client(app):
    """
    Creates a Supabase client authenticated with the user's token.
    This ensures that all database operations respect Row Level Security (RLS).
    """
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        current_app.logger.warning("Auth header missing or malformed.")
        return None, None

    token = auth_header.split(" ")[1]
    
    # It's crucial to create a new client instance for the request
    # and authenticate it with the user's token.
    # This is often the root cause of RLS issues.
    try:
        # Create a new client instance for this request
        url = app.config['SUPABASE_URL']
        key = app.config['SUPABASE_KEY']
        
        # This client will be authenticated with the user's JWT
        authenticated_client = create_client(url, key)
        authenticated_client.postgrest.auth(token)
        
        # Verify the token is valid and get the user
        user_response = authenticated_client.auth.get_user()
        
        if user_response.user:
            return authenticated_client, user_response.user.id
        else:
            current_app.logger.warning("Token is invalid or expired.")
            return None, None
            
    except Exception as e:
        current_app.logger.error(f"Auth client creation failed: {e}", exc_info=True)
        return None, None

def get_service_client(app):
    """
    Creates a Supabase client with the service role key to bypass RLS.
    This should be used with extreme caution and only for authorized writes.
    """
    service_key = app.config.get('SUPABASE_SERVICE_ROLE_KEY')
    if not service_key:
        current_app.logger.error("FATAL: SUPABASE_SERVICE_ROLE_KEY is not configured.")
        return None
    try:
        url = app.config['SUPABASE_URL']
        return create_client(url, service_key)
    except Exception as e:
        current_app.logger.error(f"Failed to create service client: {e}")
        return None

@journal_bp.route('/journal/entries', methods=['GET', 'DELETE'])
def handle_journal_entries():
    current_app.logger.info(f"Route /api/journal/entries hit with method: {request.method} at %s", datetime.now(timezone.utc).isoformat())
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    query_user_id = request.args.get('userId')
    if query_user_id != user_id:
        return jsonify({"error": "Access denied: Mismatched user ID"}), 403

    if request.method == 'GET':
        try:
            res = client.table("journalEntry").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            current_app.logger.info(f"Successfully fetched {len(res.data)} entries for user {user_id} at %s", datetime.now(timezone.utc).isoformat())
            return jsonify(res.data or []), 200
        except APIError as e:
            current_app.logger.error(f"Supabase API Error on GET: {e.message} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
            return jsonify({"error": f"Database error: {e.message}"}), 500
        except Exception as e:
            current_app.logger.error(f"Generic Error on GET: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
            return jsonify({"error": "An unexpected server error occurred"}), 500

    if request.method == 'DELETE':
        try:
            res = client.table("journalEntry").delete().eq("user_id", user_id).execute()
            current_app.logger.info(f"Deleted {len(res.data)} entries for user {user_id} at %s", datetime.now(timezone.utc).isoformat())
            return jsonify({"message": "Entries deleted", "count": len(res.data)}), 200
        except Exception as e:
            current_app.logger.error(f"Error on DELETE: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
            return jsonify({"error": "Failed to delete entries"}), 500

@journal_bp.route('/journalEntry', methods=['POST', 'PUT'])
def save_journal_entry():
    # Step 1: Securely authenticate the user to get their ID.
    _, user_id = get_auth_client(current_app._get_current_object())
    if not user_id:
        return jsonify({"error": "Authentication failed. User ID could not be verified."}), 401

    # Step 2: Get the privileged service client to perform the write.
    # This bypasses any RLS issues on the table.
    service_client = get_service_client(current_app._get_current_object())
    if not service_client:
        return jsonify({"error": "Server configuration error. Cannot save data."}), 500

    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body cannot be empty."}), 400

    current_app.logger.info(f"Received data for journal entry: {json.dumps(data)}")

    try:
        if request.method == 'POST':
            # (Validation logic remains the same...)
            required_fields = ['content', 'mood', 'score', 'analysis']
            missing = [field for field in required_fields if field not in data]
            if missing:
                return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400
            
            try:
                score = int(data['score'])
                if not (0 <= score <= 10):
                    raise ValueError("Score must be between 0 and 10.")
            except (ValueError, TypeError):
                return jsonify({"error": "Score must be an integer between 0 and 10."}), 400

            try:
                analysis_data = data['analysis']
                analysis_dict = json.loads(analysis_data) if isinstance(analysis_data, str) else analysis_data
                if not isinstance(analysis_dict, dict):
                    raise TypeError("Analysis must be a valid JSON object.")
            except (json.JSONDecodeError, TypeError) as e:
                return jsonify({"error": f"Invalid analysis format: {e}"}), 400

            entry_data = {
                "journal_id": str(uuid.uuid4()),
                "user_id": user_id,
                "entry_text": data['content'],
                "mood": data['mood'],
                "prompt_text": data.get('prompt_text'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
                "questionnaire_data": data.get('questionnaire_data'),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score": score,
                "analysis": analysis_dict
            }
            
            # Step 3: Use the privileged client to insert data.
            res = service_client.table("journalEntry").insert(entry_data).execute()

            if not hasattr(res, 'data') or not res.data:
                raise Exception(f"Failed to insert journal entry. Supabase response: {res}")

            response_data = res.data[0]
            response_data['backend_version'] = 'v1.2-canary'  # Canary to verify deployment
            return jsonify({"success": True, "data": response_data}), 201

        elif request.method == 'PUT':
            return jsonify({"success": True, "message": "Update endpoint called."}), 200

    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e}", exc_info=True)
        return jsonify({"error": f"A server error occurred: {str(e)}"}), 500
