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
        # Use transaction to ensure atomicity
        with client.transaction() as tx:
            # Save journal entry
            entry_data = {
                "journal_id": str(uuid.uuid4()),
                "user_id": user_id,
                "entry_text": data['content'],
                "mood": data['mood'],
                "prompt_text": data.get('prompt_text'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
                "questionnaire_data": data.get('questionnaire_data'),
                "created_at": datetime.now(timezone.utc).isoformat()
            }

            res = client.table("journalEntry").insert(entry_data).execute()
            journal_entry = res.data[0]
            current_app.logger.info(f"Successfully saved journal entry for user {user_id} with journal_id {journal_entry['journal_id']}.")

            # Verify journal entry exists
            verify_res = client.table("journalEntry").select("*").eq("journal_id", journal_entry['journal_id']).execute()
            if not verify_res.data:
                current_app.logger.error(f"Verification failed: Journal entry with journal_id {journal_entry['journal_id']} not found after insert.")
                raise Exception("Verification failed")

            # Save score and analysis if provided
            score = data.get('score')
            analysis = data.get('analysis')
            if score is not None and analysis is not None:
                current_app.logger.info(f"Attempting to save score {score} and analysis {analysis} for journal_id {journal_entry['journal_id']}.")
                score_data = {
                    "journal_id": journal_entry['journal_id'],
                    "score": int(float(score)),  # Ensure float to int conversion, validate range for int2
                    "analysis": json.dumps(analysis),
                    "created_at": journal_entry['created_at']
                }
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        score_res = client.table("score").insert(score_data).execute()
                        if score_res.data:
                            current_app.logger.info(f"Successfully saved score {score} for journal_id {journal_entry['journal_id']} on attempt {attempt + 1}.")
                            break
                        else:
                            current_app.logger.error(f"Score insert failed for journal_id {journal_entry['journal_id']} on attempt {attempt + 1}. Response: {score_res}, Data: {score_data}")
                            if attempt < max_retries - 1:
                                time.sleep(1)  # Wait before retry
                            else:
                                raise Exception("Score insert failed after retries")
                    except APIError as e:
                        current_app.logger.error(f"Supabase API Error inserting score for journal_id {journal_entry['journal_id']} on attempt {attempt + 1}: {e.message}", exc_info=True)
                        if attempt < max_retries - 1:
                            time.sleep(1)  # Wait before retry
                        else:
                            raise Exception(f"Supabase API Error: {str(e)}")
                    except ValueError as e:
                        current_app.logger.error(f"ValueError converting score {score} to int for journal_id {journal_entry['journal_id']} on attempt {attempt + 1}: {e}", exc_info=True)
                        raise Exception(f"Invalid score value: {str(e)}")
                    except Exception as e:
                        current_app.logger.error(f"Unexpected error inserting score for journal_id {journal_entry['journal_id']} on attempt {attempt + 1}: {e}", exc_info=True)
                        if attempt < max_retries - 1:
                            time.sleep(1)  # Wait before retry
                        else:
                            raise Exception(f"Unexpected error: {str(e)}")

            # Update journal_entry with score and analysis only if score was successfully saved
            journal_entry['score'] = score if 'score_res' in locals() and score_res.data else None
            journal_entry['analysis'] = analysis if 'score_res' in locals() and score_res.data else None

        return jsonify({"success": True, "data": journal_entry}), 201
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
        res = client.table("score").select("*").eq("journal_id", journal_id).execute()
        if res.data:
            score_data = res.data[0]
            score_data['analysis'] = json.loads(score_data['analysis']) if score_data['analysis'] else {}
            return jsonify(score_data), 200
        return jsonify({"error": "Score not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Error fetching score: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred"}), 500