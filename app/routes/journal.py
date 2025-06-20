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
        # Use transaction to ensure atomicity for new entries
        with client.transaction() as tx:
            # Prepare journal entry data with score and analysis for new submissions
            score = data.get('score')
            analysis = data.get('analysis')
            if score is not None and not isinstance(score, (int, float)):
                raise ValueError("Score must be a number")
            if score is not None:
                score = int(float(score))  # Convert to integer for int2 column
                if score < -32768 or score > 32767:
                    raise ValueError("Score out of range for int2 (-32768 to 32767)")

            entry_data = {
                "journal_id": str(uuid.uuid4()),
                "user_id": user_id,
                "entry_text": data['content'],
                "mood": data['mood'],
                "prompt_text": data.get('prompt_text'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
                "questionnaire_data": data.get('questionnaire_data'),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score": score if score is not None else None,
                "analysis": json.dumps(analysis) if analysis else None
            }

            # Insert new journal entry
            res = client.table("journalEntry").insert(entry_data).execute()
            journal_entry = res.data[0]
            current_app.logger.info(f"Initial save attempt for new journal entry for user {user_id} with journal_id {journal_entry['journal_id']} and score {journal_entry['score']}.")

            # Verify and enforce score for new entry with immediate retry
            max_retries = 3
            for attempt in range(max_retries):
                verify_res = client.table("journalEntry").select("*").eq("journal_id", journal_entry['journal_id']).execute()
                if not verify_res.data:
                    current_app.logger.error(f"Verification failed for new journal entry with journal_id {journal_entry['journal_id']} on attempt {attempt + 1}.")
                    raise Exception("Verification failed for new entry")
                journal_entry = verify_res.data[0]
                if journal_entry['score'] == score:
                    current_app.logger.info(f"Successfully verified new journal entry with score {journal_entry['score']} for journal_id {journal_entry['journal_id']} on attempt {attempt + 1}.")
                    break
                else:
                    current_app.logger.warning(f"Score mismatch or null for new journal_id {journal_entry['journal_id']} on attempt {attempt + 1}. Expected: {score}, Got: {journal_entry['score']}. Forcing update.")
                    update_data = {"score": score, "analysis": json.dumps(analysis) if analysis else None}
                    update_res = client.table("journalEntry").update(update_data).eq("journal_id", journal_entry['journal_id']).execute()
                    if not update_res.data:
                        current_app.logger.error(f"Update failed for new journal_id {journal_entry['journal_id']} on attempt {attempt + 1}.")
                        if attempt < max_retries - 1:
                            time.sleep(1)  # Wait before retry
                        else:
                            raise Exception("Failed to update score for new entry after retries")
                    journal_entry = update_res.data[0]
                    # Immediate re-verification after update
                    verify_res = client.table("journalEntry").select("*").eq("journal_id", journal_entry['journal_id']).execute()
                    if verify_res.data and verify_res.data[0]['score'] == score:
                        current_app.logger.info(f"Confirmed score {score} saved for journal_id {journal_entry['journal_id']} after update on attempt {attempt + 1}.")
                        break
            else:
                raise Exception("Max retries reached without successful score update for new entry")

            return jsonify({"success": True, "data": journal_entry}), 201
    except ValueError as ve:
        current_app.logger.error(f"Validation error saving entry: {ve}", exc_info=True)
        return jsonify({"error": f"Validation error: {str(ve)}"}), 400
    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e}", exc_info=True)
        return jsonify({"error": f"Failed to save journal entry: {str(e)}"}), 500

@journal_bp.route('/api/score', methods=['GET'])
def get_score():
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    journal_id = request.args.get('journalId')
    if not journal_id:
        return jsonify({"error": "Missing journalId parameter"}), 400

    try:
        res = client.table("journalEntry").select("score", "analysis").eq("journal_id", journal_id).execute()
        if res.data:
            score_data = res.data[0]
            score_data['analysis'] = json.loads(score_data['analysis']) if score_data['analysis'] else {}
            return jsonify(score_data), 200
        return jsonify({"score": None, "analysis": None}), 200  # Return null values
    except Exception as e:
        current_app.logger.error(f"Error fetching score: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500