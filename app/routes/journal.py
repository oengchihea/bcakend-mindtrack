import os
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest import APIError

journal_bp = Blueprint('journal_bp', __name__)

def get_auth_client():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        current_app.logger.warning("Auth header missing or malformed.")
        return None, None

    token = auth_header.split(" ")[1]
    try:
        client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        client.postgrest.auth(token)
        user_response = client.auth.get_user(jwt=token)
        if user_response.user:
            return client, user_response.user.id
        return None, None
    except Exception as e:
        current_app.logger.error(f"Auth client creation failed: {e}", exc_info=True)
        return None, None

@journal_bp.route('/api/journal/entries', methods=['GET', 'DELETE'])
def handle_journal_entries():
    current_app.logger.info(f"Route /api/journal/entries hit with method: {request.method}")
    client, user_id = get_auth_client()
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    query_user_id = request.args.get('userId')
    if query_user_id != user_id:
        return jsonify({"error": "Access denied: Mismatched user ID"}), 403

    if request.method == 'GET':
        try:
            res = client.table("journalEntry").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
            current_app.logger.info(f"Successfully fetched {len(res.data)} entries for user {user_id}.")
            return jsonify(res.data or []), 200
        except APIError as e:
            current_app.logger.error(f"Supabase API Error on GET: {e.message}", exc_info=True)
            return jsonify({"error": f"Database error: {e.message}"}), 500
        except Exception as e:
            current_app.logger.error(f"Generic Error on GET: {e}", exc_info=True)
            return jsonify({"error": "An unexpected server error occurred"}), 500

    if request.method == 'DELETE':
        try:
            res = client.table("journalEntry").delete().eq("user_id", user_id).execute()
            current_app.logger.info(f"Deleted {len(res.data)} entries for user {user_id}.")
            return jsonify({"message": "Entries deleted", "count": len(res.data)}), 200
        except Exception as e:
            current_app.logger.error(f"Error on DELETE: {e}", exc_info=True)
            return jsonify({"error": "Failed to delete entries"}), 500

@journal_bp.route('/api/journalEntry', methods=['POST'])
def save_journal_entry():
    client, user_id = get_auth_client()
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    data = request.get_json()
    if not data or 'content' not in data or 'mood' not in data:
        return jsonify({"error": "Missing required fields: content and mood"}), 400

    try:
        entry_data = {
            "journal_id": str(uuid.uuid4()),
            "user_id": user_id,
            "entry_text": data['content'],
            "mood": data['mood'],
            "prompt_text": data.get('prompt_text'),
            "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
            "questionnaire_data": data.get('questionnaire_data'),
            "analysis_score": data.get('score'),  # Store the analysis score if provided
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Validate score if provided
        if entry_data["analysis_score"] is not None:
            try:
                score = float(entry_data["analysis_score"])
                if not (0 <= score <= 10):
                    return jsonify({"error": "Score must be between 0 and 10"}), 400
                entry_data["analysis_score"] = score
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid score format"}), 400

        res = client.table("journalEntry").insert(entry_data).execute()
        current_app.logger.info(f"Successfully saved journal entry for user {user_id} with score {entry_data['analysis_score']}.")
        return jsonify({"success": True, "data": res.data[0]}), 201
    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e}", exc_info=True)
        return jsonify({"error": "Failed to save journal entry"}), 500