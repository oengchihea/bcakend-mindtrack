import os
import uuid
from datetime import datetime, timezone
import json
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest.exceptions import APIError

journal_bp = Blueprint('journal_bp', __name__)

def _get_authenticated_supabase_client_from_request():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        current_app.logger.warning("[AuthHelper] Missing or malformed Authorization header.")
        return None, None

    token = auth_header.split(' ')[1]

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        current_app.logger.error("[AuthHelper] SUPABASE_URL or SUPABASE_KEY missing.")
        return None, None
    try:
        client = create_client(supabase_url, supabase_key)
        client.postgrest.auth(token) # Set the JWT for the PostgREST client

        user_response = client.auth.get_user(jwt=token) # Validate token and get user
        if not user_response or not user_response.user:
            current_app.logger.warning(f"[AuthHelper] Invalid token or unable to fetch user details.")
            return None, None

        current_app.logger.info(f"[AuthHelper] Authenticated Supabase client created for user: {user_response.user.id}")
        return client, user_response.user.id
    except Exception as e:
        current_app.logger.error(f"[AuthHelper] Failed to create/validate authenticated Supabase client: {e}", exc_info=True)
        return None, None

class JournalService:
    def __init__(self, db_client: Client):
        if not db_client:
            current_app.logger.error("[JournalService] Initialized with a null db_client.")
            raise ValueError("Database client cannot be null for JournalService")
        self.supabase = db_client

    def _analyze_content_placeholder(self, content: str, mood_context: str | None = None) -> dict:
        current_app.logger.info(f"[JournalService] Using placeholder AI analysis. Mood: {mood_context}, Content snippet: {content[:50]}...")
        return {
            "insights": f"Journal entry analyzed (placeholder). Mood context: {mood_context or 'N/A'}. Content snippet: {content[:50]}...",
            "sentiment": "neutral", "emoji": "😐", "themes": [], "score": 5.0,
            "source": "backend-placeholder-analysis", "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def save_journal_to_journal_entry_table(self, user_id: str, content: str, mood: str,
                                            prompt_text: str | None = None,
                                            questionnaire_data_str: str | None = None) -> dict:
        target_table_name = "journalEntry"
        current_app.logger.info(f"[JournalService] Preparing to save journal to \"{target_table_name}\" for user: {user_id}")
        entry_type = "Standard Journal"
        parsed_questionnaire_data = None
        if questionnaire_data_str:
            try:
                parsed_questionnaire_data = json.loads(questionnaire_data_str)
                interaction_type = parsed_questionnaire_data.get("journal_interaction_type")
                if interaction_type == "ai_guided_multi_prompt" or interaction_type == "ai_guided_single_prompt":
                    entry_type = "AI Guided Journal"
                elif interaction_type == "free_writing":
                    entry_type = "Free Writing Journal"
            except json.JSONDecodeError:
                current_app.logger.warning(f"[JournalService] Failed to parse QData. Storing as null. Data: {questionnaire_data_str[:100]}")

        if entry_type == "Standard Journal": # Fallback if not determined by questionnaire_data
            if mood:
                mood_lower = mood.lower()
                if "ai guided" in mood_lower or "ai_guided" in mood_lower: entry_type = "AI Guided Journal"
                elif "free write" in mood_lower or "freewrite" in mood_lower: entry_type = "Free Writing Journal"
            if prompt_text and entry_type == "Standard Journal":
                 entry_type = "Prompted Journal"
            elif prompt_text and "ai guided" not in entry_type.lower() and "free writing" not in entry_type.lower():
                 entry_type = "AI Guided Journal"


        analysis_result = self._analyze_content_placeholder(content, mood_context=mood)

        db_entry_data = {
            "journal_id": str(uuid.uuid4()), "user_id": user_id, "entry_text": content,
            "mood": mood, "prompt_text": prompt_text, "entry_type": entry_type,
            "analysis": analysis_result, "created_at": datetime.now(timezone.utc).isoformat(),
            "questionnaire_data": parsed_questionnaire_data
        }
        current_app.logger.debug(f"[JournalService] Data for '{target_table_name}' insert: {json.dumps(db_entry_data, indent=2, default=str)}")
        try:
            response = self.supabase.table(target_table_name).insert(db_entry_data).execute()
            if response.data and len(response.data) > 0:
                current_app.logger.info(f"[JournalService] Inserted to '{target_table_name}'. Data: {response.data[0]}")
                return {"success": True, "message": "Journal entry saved.", "data": response.data[0]}
            else:
                current_app.logger.warning(f"[JournalService] Insert to '{target_table_name}' no data returned in response list, but operation likely succeeded. Resp: {response}")
                return {"success": True, "message": "Journal entry saved (no data in response list).", "data": db_entry_data}
        except APIError as e:
            current_app.logger.error(f"[JournalService] Supabase APIError insert to {target_table_name}: {e.code}, {e.message}", exc_info=True)
            error_message = e.message or "Database API error"
            if hasattr(e, 'details') and isinstance(e.details, dict) and 'message' in e.details:
                 error_message = e.details['message']
            elif hasattr(e, 'details') and isinstance(e.details, str):
                 error_message = e.details

            if "violates row-level security policy" in error_message.lower() or e.code == "42501":
                raise Exception(f"RLS policy violation for {target_table_name}: {error_message}") from e
            raise Exception(f"Database operation for {target_table_name} failed: {error_message}") from e
        except Exception as e:
            current_app.logger.error(f"[JournalService] Generic exception insert to {target_table_name}: {str(e)}", exc_info=True)
            raise Exception(f"Unexpected error saving to {target_table_name}: {str(e)}") from e

@journal_bp.route('/api/journalEntry', methods=['POST'])
def save_detailed_journal_entry_route():
    current_app.logger.info(f"[JournalRoute] Received POST /api/journalEntry")
    try:
        db_client, authenticated_user_id = _get_authenticated_supabase_client_from_request()
        if not db_client or not authenticated_user_id:
            return jsonify({"error": "Authentication failed or Supabase client could not be initialized."}), 401

        data = request.get_json()
        if not data: return jsonify({"error": "No data provided"}), 400

        payload_user_id = data.get('userId')
        if payload_user_id and payload_user_id != authenticated_user_id:
            current_app.logger.warning(f"[JournalRoute] Mismatch! Token UID ({authenticated_user_id}) vs Payload UID ({payload_user_id}). Using Token UID.")

        user_id_to_save = authenticated_user_id

        content = data.get('content')
        mood_type = data.get('mood')
        prompt_used = data.get('prompt_text')

        questionnaire_data_input = data.get('questionnaire_data')
        questionnaire_data_str = None
        if isinstance(questionnaire_data_input, dict):
            questionnaire_data_str = json.dumps(questionnaire_data_input)
        elif isinstance(questionnaire_data_input, str):
             questionnaire_data_str = questionnaire_data_input


        if content is None: return jsonify({"error": "'content' is required."}), 400
        if mood_type is None: return jsonify({"error": "'mood' is required."}), 400

        journal_service = JournalService(db_client=db_client)
        result = journal_service.save_journal_to_journal_entry_table(
            user_id=user_id_to_save, content=content, mood=mood_type,
            prompt_text=prompt_used, questionnaire_data_str=questionnaire_data_str
        )
        if result.get("success"): return jsonify(result), 201
        else: return jsonify({"error": result.get("message", "Failed to save"), "details": result.get("data")}), 500
    except Exception as e:
        current_app.logger.error(f"[JournalRoute] Unhandled Exception in /api/journalEntry: {str(e)}", exc_info=True)
        if "RLS policy violation" in str(e): return jsonify({"error": "DB security policy prevented saving.", "details": str(e)}), 403
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500

@journal_bp.route('/api/journal/entries', methods=['GET', 'DELETE'])
def journal_entries_route():
    db_client, authenticated_user_id = _get_authenticated_supabase_client_from_request()
    if not db_client or not authenticated_user_id:
        return jsonify({"error": "Authentication failed or Supabase client could not be initialized."}), 401

    query_user_id_from_param = request.args.get('userId')
    if not query_user_id_from_param:
        current_app.logger.warning("[JournalHistoryRoute] 'userId' query parameter is missing.")
        return jsonify({"error": "'userId' query parameter is required"}), 400

    if query_user_id_from_param != authenticated_user_id:
        current_app.logger.error(
            f"[JournalHistoryRoute] Mismatch: Token User ID ({authenticated_user_id}) "
            f"vs Query Param User ID ({query_user_id_from_param}). Access denied."
        )
        return jsonify({"error": "Access denied: Operation can only be performed on your own entries."}), 403

    user_id_to_operate_on = authenticated_user_id
    target_table_name = "journalEntry"

    if request.method == 'GET':
        current_app.logger.info(f"[JournalHistoryRoute-GET] Fetching entries from '{target_table_name}' for user: {user_id_to_operate_on}")
        try:
            response = db_client.table(target_table_name)\
                                .select("*")\
                                .eq("user_id", user_id_to_operate_on)\
                                .order("created_at", desc=True)\
                                .execute()
            if response.data is not None:
                current_app.logger.info(f"[JournalHistoryRoute-GET] Successfully fetched {len(response.data)} entries for user {user_id_to_operate_on}.")
                return jsonify(response.data), 200
            else:
                current_app.logger.warning(f"[JournalHistoryRoute-GET] No data field in response or null data for user {user_id_to_operate_on}. Response: {response}")
                return jsonify([]), 200
        except APIError as e:
            current_app.logger.error(f"[JournalHistoryRoute-GET] Supabase APIError: {e.code}, {e.message}, {e.details}", exc_info=True)
            return jsonify({"error": f"Database error fetching entries: {e.message}"}), getattr(e, 'status_code', 500)
        except Exception as e:
            current_app.logger.error(f"[JournalHistoryRoute-GET] Generic error: {str(e)}", exc_info=True)
            return jsonify({"error": f"Failed to fetch journal entries: {str(e)}"}), 500

    elif request.method == 'DELETE':
        current_app.logger.info(f"[JournalHistoryRoute-DELETE] Deleting entries from '{target_table_name}' for user: {user_id_to_operate_on}")
        try:
            response = db_client.table(target_table_name)\
                                .delete()\
                                .eq("user_id", user_id_to_operate_on)\
                                .execute()
            current_app.logger.info(f"[JournalHistoryRoute-DELETE] Delete operation executed for user {user_id_to_operate_on}. Response data count: {len(response.data) if response.data else 'N/A'}")
            return jsonify({"message": "All journal entries deleted successfully."}), 200
        except APIError as e:
            current_app.logger.error(f"[JournalHistoryRoute-DELETE] Supabase APIError: {e.code}, {e.message}, {e.details}", exc_info=True)
            return jsonify({"error": f"Database error deleting entries: {e.message}"}), getattr(e, 'status_code', 500)
        except Exception as e:
            current_app.logger.error(f"[JournalHistoryRoute-DELETE] Generic error: {str(e)}", exc_info=True)
            return jsonify({"error": f"Failed to delete journal entries: {str(e)}"}), 500
