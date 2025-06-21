import os
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest import APIError
import time

journal_bp = Blueprint('journal_bp', __name__)

def get_auth_client(app):
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        current_app.logger.warning("Auth header missing or malformed.")
        return None, None

    token = auth_header.split(" ")[1]
    max_retries = 2
    for attempt in range(max_retries):
        try:
            if not app.supabase:
                current_app.logger.error("Supabase client not initialized in app context.")
                return None, None
            client = app.supabase
            client.postgrest.auth(token)
            user_response = client.auth.get_user(jwt=token)
            if user_response.user:
                return client, user_response.user.id
            current_app.logger.warning(f"Auth attempt {attempt + 1} failed: No user response.")
        except Exception as e:
            current_app.logger.error(f"Auth client creation failed (attempt {attempt + 1}/{max_retries}): {e}", exc_info=True)
            if attempt < max_retries - 1:
                current_app.logger.info("Reinitializing Supabase client due to auth failure.")
                app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
            else:
                return None, None
    return None, None

@journal_bp.route('/api/journal/entries', methods=['GET', 'DELETE'])
def handle_journal_entries():
    current_app.logger.info(f"Route /api/journal/entries hit with method: {request.method}")
    client, user_id = get_auth_client(current_app._get_current_object())
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
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    data = request.get_json()
    if not data or 'content' not in data or 'mood' not in data:
        return jsonify({"error": "Missing required fields: content and mood"}), 400

    try:
        # Check if journal_id exists for update
        journal_id = data.get('journal_id')

        if journal_id:
            # Update existing entry
            current_app.logger.info(f"Updating existing entry with journal_id: {journal_id}")
            update_data = {
                "entry_text": data.get('content'),
                "mood": data.get('mood'),
                "prompt_text": data.get('prompt_text'),
                "questionnaire_data": data.get('questionnaire_data'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
            }
            # Explicitly set score and analysis, with type checking
            if 'score' in data and data['score'] is not None:
                update_data['score'] = int(data['score']) if isinstance(data['score'], (int, float, str)) else None
            if 'analysis' in data and data['analysis'] is not None:
                try:
                    update_data['analysis'] = json.dumps(data['analysis']) if isinstance(data['analysis'], (dict, str)) else None
                except (TypeError, ValueError) as e:
                    current_app.logger.error(f"Failed to serialize analysis: {e}")
                    update_data['analysis'] = None

            current_app.logger.info(f"Update data sent to Supabase: {update_data}")
            res = client.table("journalEntry").update(update_data).eq("journal_id", journal_id).execute()
            if not res.data or len(res.data) == 0:
                raise Exception(f"Failed to update journal entry with journal_id: {journal_id}")

            journal_entry = res.data[0]
            current_app.logger.info(f"Successfully updated journal entry {journal_id}")
        else:
            # Create new entry
            entry_data = {
                "journal_id": str(uuid.uuid4()),
                "user_id": user_id,
                "entry_text": data['content'],
                "mood": data['mood'],
                "prompt_text": data.get('prompt_text'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
                "questionnaire_data": data.get('questionnaire_data'),
                "created_at": datetime.now(timezone.utc).isoformat(),
                # Explicitly set score and analysis with type validation
                "score": int(data.get('score', 0)) if data.get('score') is not None and isinstance(data.get('score'), (int, float, str)) else None,
                "analysis": json.dumps(data.get('analysis', {})) if data.get('analysis') is not None and isinstance(data.get('analysis'), (dict, str)) else None
            }

            current_app.logger.info(f"Insert data sent to Supabase: {entry_data}")
            res = client.table("journalEntry").insert(entry_data).execute()
            if not res.data or len(res.data) == 0:
                raise Exception("Failed to insert journal entry into Supabase")

            journal_entry = res.data[0]
            current_app.logger.info(f"Successfully created journal entry {journal_entry['journal_id']}")

        return jsonify({"success": True, "data": journal_entry}), 201 if not journal_id else 200

    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Invalid score or analysis data: {e}", exc_info=True)
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save journal entry: {str(e)}"}), 500

# Optional: /api/journalScore endpoint (enable if journal_scores table is needed)
@journal_bp.route('/api/journalScore', methods=['POST'])
def save_journal_score():
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    data = request.get_json()
    if not data or 'journalId' not in data or 'score' not in data or 'userId' not in data or data['userId'] != user_id:
        return jsonify({"error": "Missing required fields: journalId, score, and userId, or mismatched userId"}), 400

    try:
        journal_id = data.get('journalId')
        score = data.get('score')
        analysis = data.get('analysis')

        try:
            score = int(float(str(score)))
            if score < 0 or score > 10:
                raise ValueError("Score must be between 0 and 10")
        except (ValueError, TypeError):
            current_app.logger.error(f"Invalid score value: {score}, rejecting request")
            return jsonify({"error": "Invalid score value, must be a number between 0 and 10"}), 400

        current_app.logger.info(f"Saving score: {score} for journal_id: {journal_id}")

        if analysis is not None:
            if isinstance(analysis, str):
                try:
                    analysis = json.loads(analysis)
                except json.JSONDecodeError:
                    current_app.logger.warning(f"Invalid JSON in analysis: {analysis}, setting to None")
                    analysis = None
            if not isinstance(analysis, dict):
                current_app.logger.warning(f"Invalid analysis type: {type(analysis)}, setting to None")
                analysis = None

        score_data = {
            "journal_id": journal_id,
            "user_id": user_id,
            "score": score,
            "analysis": json.dumps(analysis) if analysis else None,
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        current_app.logger.info(f"Score data sent to Supabase: {score_data}")
        res = client.table("journal_scores").insert(score_data).execute()
        if not res.data or len(res.data) == 0:
            raise Exception(f"Failed to save score for journal_id: {journal_id}")

        score_entry = res.data[0]
        current_app.logger.info(f"Successfully saved score for journal_id: {journal_id} with score {score}")

        return jsonify({"success": True, "data": score_entry}), 201

    except ValueError as ve:
        current_app.logger.error(f"Validation error saving score: {ve}", exc_info=True)
        return jsonify({"error": f"Validation error: {str(ve)}"}), 400
    except Exception as e:
        current_app.logger.error(f"Error saving score: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save journal score: {str(e)}"}), 500