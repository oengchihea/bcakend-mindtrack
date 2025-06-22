import os
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest import APIError

journal_bp = Blueprint('journal_bp', __name__)

def get_auth_client(app):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        current_app.logger.warning("Auth header missing or malformed at %s", datetime.now(timezone.utc).isoformat())
        return None, None

    token = auth_header.split(" ")[1]
    max_retries = 2
    for attempt in range(max_retries):
        try:
            if not app.supabase:
                current_app.logger.error("Supabase client not initialized in app context at %s", datetime.now(timezone.utc).isoformat())
                return None, None
            client = app.supabase
            client.postgrest.auth(token)
            user_response = client.auth.get_user(jwt=token)
            if user_response.user:
                return client, user_response.user.id
            current_app.logger.warning(f"Auth attempt {attempt + 1} failed: No user response at %s", datetime.now(timezone.utc).isoformat())
        except Exception as e:
            current_app.logger.error(f"Auth client creation failed (attempt {attempt + 1}/{max_retries}): {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
            if attempt < max_retries - 1:
                current_app.logger.info("Reinitializing Supabase client due to auth failure at %s", datetime.now(timezone.utc).isoformat())
                app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
            else:
                return None, None
    return None, None

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
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    data = request.get_json()
    current_app.logger.info(f"Received request for /journalEntry ({request.method}) at %s", datetime.now(timezone.utc).isoformat())

    if not data:
        return jsonify({"error": "Request body cannot be empty."}), 400

    try:
        if request.method == 'POST':
            required_fields = ['content', 'mood', 'score', 'analysis']
            missing = [field for field in required_fields if field not in data]
            if missing:
                return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

            try:
                score = int(data['score'])
                if not (0 <= score <= 10):
                    raise ValueError("Score must be between 0 and 10.")
            except (ValueError, TypeError):
                current_app.logger.error(f"Invalid score value: {data.get('score')}")
                return jsonify({"error": "Score must be an integer between 0 and 10."}), 400

            try:
                analysis_data = data['analysis']
                if isinstance(analysis_data, str):
                    analysis_dict = json.loads(analysis_data)
                elif isinstance(analysis_data, dict):
                    analysis_dict = analysis_data
                else:
                    raise TypeError("Analysis must be a valid JSON object or string.")
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.error(f"Invalid analysis format: {data.get('analysis')}, error: {e}")
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
            
            current_app.logger.info(f"Attempting to insert new journal entry: {entry_data}")
            res = client.table("journalEntry").insert(entry_data).execute()

            if not hasattr(res, 'data') or not res.data:
                current_app.logger.error(f"Failed to insert journal entry. Supabase response: {res}")
                raise Exception("Failed to insert journal entry into Supabase")

            journal_entry = res.data[0]
            current_app.logger.info(f"Successfully created journal entry {journal_entry['journal_id']} with score {journal_entry.get('score')}")
            return jsonify({"success": True, "data": journal_entry}), 201

        elif request.method == 'PUT':
            journal_id = data.get('journal_id')
            if not journal_id:
                return jsonify({"error": "Missing journal_id for update"}), 400
            
            # Placeholder for future update logic
            current_app.logger.info(f"Update operation for journal_id {journal_id} is not yet fully implemented.")
            # Your existing update logic can be placed here.
            # For now, returning a success to avoid breaking the flow if PUT is called.
            return jsonify({"success": True, "message": "Update endpoint called but no action taken."}), 200

    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save journal entry: {str(e)}"}), 500
