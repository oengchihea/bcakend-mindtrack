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
    current_app.logger.info(f"Received request data: {data} at %s", datetime.now(timezone.utc).isoformat())
    if not data or 'content' not in data or 'mood' not in data:
        return jsonify({"error": "Missing required fields: content and mood"}), 400

    try:
        # Check if journal_id exists for update or create
        journal_id = data.get('journal_id')

        if journal_id and request.method == 'PUT':
            # Update existing entry
            current_app.logger.info(f"Updating existing entry with journal_id: {journal_id} at %s", datetime.now(timezone.utc).isoformat())
            update_data = {
                "entry_text": data.get('content', ''),
                "mood": data.get('mood', ''),
                "prompt_text": data.get('prompt_text'),
                "questionnaire_data": data.get('questionnaire_data'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
            }
            # Enforce score and analysis from request
            update_data['score'] = data.get('score')
            if update_data['score'] is None and 'analysis' in data and data['analysis']:
                try:
                    analysis_data = json.loads(data['analysis']) if isinstance(data['analysis'], str) else data['analysis']
                    update_data['score'] = int(analysis_data.get('score', 5))
                    current_app.logger.warning(f"Score missing in update, using fallback from analysis: {update_data['score']} at %s", datetime.now(timezone.utc).isoformat())
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    update_data['score'] = 5  # Default score
                    current_app.logger.error(f"Failed to parse analysis for score, using default: {update_data['score']} at %s", datetime.now(timezone.utc).isoformat())

            if 'score' in update_data and update_data['score'] is not None:
                try:
                    update_data['score'] = int(float(str(update_data['score'])))
                    if update_data['score'] < 0 or update_data['score'] > 10:
                        raise ValueError("Score must be between 0 and 10")
                except (ValueError, TypeError) as e:
                    current_app.logger.error(f"Invalid score value: {update_data['score']} for journal_id {journal_id} at %s", datetime.now(timezone.utc).isoformat())
                    return jsonify({"error": "Invalid score value, must be a number between 0 and 10"}), 400
            else:
                update_data['score'] = 5  # Default if no valid score provided

            update_data['analysis'] = data.get('analysis')
            if update_data['analysis'] is not None:
                try:
                    update_data['analysis'] = json.dumps(update_data['analysis']) if isinstance(update_data['analysis'], dict) else update_data['analysis']
                    current_app.logger.info(f"Serialized analysis for update: {update_data['analysis']} at %s", datetime.now(timezone.utc).isoformat())
                except (TypeError, ValueError) as e:
                    current_app.logger.error(f"Failed to serialize analysis: {e} at %s", datetime.now(timezone.utc).isoformat())
                    update_data['analysis'] = None

            current_app.logger.info(f"Update data sent to Supabase: {update_data} at %s", datetime.now(timezone.utc).isoformat())
            res = client.table("journalEntry").update(update_data).eq("journal_id", journal_id).eq("user_id", user_id).execute()
            if not res.data or len(res.data) == 0:
                current_app.logger.error(f"No rows updated for journal_id: {journal_id}. Check if entry exists or user_id matches at %s", datetime.now(timezone.utc).isoformat())
                raise Exception(f"No rows updated for journal_id: {journal_id}")

            journal_entry = res.data[0]
            current_app.logger.info(f"Successfully updated journal entry {journal_id} with score {journal_entry['score']} at %s", datetime.now(timezone.utc).isoformat())
        else:
            # Create new entry
            score = data.get('score')
            analysis = data.get('analysis')
            if score is None and analysis is None:
                return jsonify({"error": "Missing required fields: score and/or analysis for new entries"}), 400
            # Fallback to score from analysis if provided
            if score is None and analysis is not None:
                try:
                    analysis_data = json.loads(analysis) if isinstance(analysis, str) else analysis
                    score = int(analysis_data.get('score', 5))
                    current_app.logger.warning(f"Score missing in request, using fallback from analysis: {score} at %s", datetime.now(timezone.utc).isoformat())
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    score = 5  # Default score if analysis parsing fails
                    current_app.logger.error(f"Failed to parse analysis for score, using default: {score} at %s", datetime.now(timezone.utc).isoformat())

            try:
                score = int(float(str(score)))
                if score < 0 or score > 10:
                    raise ValueError("Score must be between 0 and 10")
            except (ValueError, TypeError) as e:
                return jsonify({"error": "Invalid score value, must be a number between 0 and 10"}), 400

            try:
                analysis = json.dumps(analysis) if isinstance(analysis, dict) else analysis
                json.loads(analysis)
            except (TypeError, ValueError, json.JSONDecodeError) as e:
                return jsonify({"error": "Invalid analysis format, must be valid JSON"}), 400

            entry_data = {
                "journal_id": str(uuid.uuid4()) if not journal_id else journal_id,
                "user_id": user_id,
                "entry_text": data['content'],
                "mood": data['mood'],
                "prompt_text": data.get('prompt_text'),
                "entry_type": data.get('questionnaire_data', {}).get('journal_interaction_type', 'Journal'),
                "questionnaire_data": json.dumps(data.get('questionnaire_data')) if data.get('questionnaire_data') else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score": score,  # Enforce score with fallback
                "analysis": analysis
            }

            current_app.logger.info(f"Insert data sent to Supabase: {entry_data} at %s", datetime.now(timezone.utc).isoformat())
            res = client.table("journalEntry").insert(entry_data).execute() if not journal_id else client.table("journalEntry").update(entry_data).eq("journal_id", journal_id).eq("user_id", user_id).execute()
            if not res.data or len(res.data) == 0:
                current_app.logger.error(f"Failed to insert/update journal entry into Supabase at %s", datetime.now(timezone.utc).isoformat())
                raise Exception("Failed to insert/update journal entry into Supabase")

            journal_entry = res.data[0]
            current_app.logger.info(f"Successfully {'created' if not journal_id else 'updated'} journal entry {journal_entry['journal_id']} with score {journal_entry['score']} at %s", datetime.now(timezone.utc).isoformat())

        return jsonify({"success": True, "data": journal_entry}), 201 if not journal_id else 200

    except (ValueError, TypeError) as e:
        current_app.logger.error(f"Invalid score or analysis data: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
        return jsonify({"error": f"Invalid data format: {str(e)}"}), 400
    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
        return jsonify({"error": f"Failed to save journal entry: {str(e)}"}), 500
