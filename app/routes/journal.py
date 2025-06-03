import os
import uuid
from datetime import datetime, timezone
import json
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Initialize Supabase client (typically with anon key, auth is handled by token)
try:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") # This should be your ANON key
    if not SUPABASE_URL or not SUPABASE_KEY:
        # Using print for startup errors as current_app.logger might not be available
        print("CRITICAL ERROR: SUPABASE_URL or SUPABASE_KEY not found in environment variables at import time (journal.py).")
except Exception as e:
    print(f"Error during initial Supabase configuration check (journal.py): {e}")


journal_bp = Blueprint('journal_bp', __name__)

# --- Helper Function to Create Authenticated Supabase Client ---
def create_authenticated_supabase_client(jwt_token: str) -> Client | None:
    """
    Creates a Supabase client instance authenticated with the provided JWT.
    """
    supabase_url_runtime = os.getenv("SUPABASE_URL")
    supabase_key_runtime = os.getenv("SUPABASE_KEY") # ANON key

    if not supabase_url_runtime or not supabase_key_runtime:
        current_app.logger.error("[JournalAuthHelper] SUPABASE_URL or SUPABASE_KEY missing for authenticated client creation.")
        return None
    try:
        client = create_client(supabase_url_runtime, supabase_key_runtime)
        client.postgrest.auth(jwt_token)
        return client
    except Exception as e:
        current_app.logger.error(f"[JournalAuthHelper] Failed to create authenticated Supabase client: {e}", exc_info=True)
        return None

# --- Journal Service Class ---
class JournalService:
    def __init__(self, db_client: Client):
        if not db_client:
            current_app.logger.error("[JournalService] Initialized with a null db_client.")
            raise ValueError("Database client cannot be null for JournalService")
        self.supabase = db_client

    def _analyze_content_placeholder(self, content: str, mood_context: str | None = None) -> dict:
        """Placeholder for AI content analysis."""
        current_app.logger.info(f"[JournalService] Using placeholder AI analysis. Mood: {mood_context}, Content snippet: {content[:50]}...")
        return {
            "insights": f"Journal entry analyzed (placeholder). Mood context: {mood_context or 'N/A'}. Content snippet: {content[:50]}...",
            "sentiment": "neutral",
            "emoji": "😐", 
            "themes": [],
            "score": 5.0,
            "source": "backend-placeholder-analysis",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def save_journal_to_journal_entry_table(self, user_id: str, content: str, mood: str, 
                                            prompt_text: str | None = None, 
                                            questionnaire_data_str: str | None = None) -> dict:
        target_table_name = "journalEntry" 
        current_app.logger.info(f"[JournalService] Preparing to save journal to \"{target_table_name}\" for user: {user_id}")

        entry_type = "Standard Journal" 
        if mood:
            mood_lower = mood.lower()
            if "ai guided" in mood_lower or "ai_guided" in mood_lower:
                entry_type = "AI Guided Journal"
            elif "free write" in mood_lower or "freewrite" in mood_lower:
                 entry_type = "Free Writing Journal"
            elif prompt_text and entry_type == "Standard Journal": 
                 entry_type = "Prompted Journal"
        elif prompt_text: 
            entry_type = "Prompted Journal"
        
        analysis_result = self._analyze_content_placeholder(content, mood_context=mood)

        parsed_questionnaire_data = None
        if questionnaire_data_str:
            try:
                parsed_questionnaire_data = json.loads(questionnaire_data_str)
            except json.JSONDecodeError:
                current_app.logger.warning(f"[JournalService] Failed to parse questionnaire_data_str as JSON. Storing as null. Data: {questionnaire_data_str[:100]}")
                parsed_questionnaire_data = None 

        db_entry_data = {
            "journal_id": str(uuid.uuid4()),
            "user_id": user_id, 
            "entry_text": content,
            "mood": mood, 
            "prompt_text": prompt_text,
            "entry_type": entry_type,
            "analysis": analysis_result, 
            "created_at": datetime.now(timezone.utc).isoformat(),
            "questionnaire_data": parsed_questionnaire_data 
        }
        
        current_app.logger.debug(f"[JournalService] Data for '{target_table_name}' insert: {json.dumps(db_entry_data, indent=2, default=str)}")

        try:
            response = self.supabase.table(target_table_name).insert(db_entry_data).execute()
            
            if response.data and len(response.data) > 0:
                current_app.logger.info(f"[JournalService] Successfully inserted journal to '{target_table_name}'. Inserted data: {response.data[0]}")
                return {"success": True, "message": "Journal entry saved successfully.", "data": response.data[0]}
            else:
                current_app.logger.warning(f"[JournalService] Insert to '{target_table_name}' reported success by not throwing an exception, but returned no data or empty data. Response: {response}")
                return {"success": True, "message": "Journal entry saved (no specific data returned in response).", "data": None}

        except APIError as e:
            current_app.logger.error(f"[JournalService] Supabase APIError during insert to {target_table_name}: Code {e.code}, Message: {e.message}, Details: {e.details}, Hint: {e.hint}", exc_info=True)
            error_message = e.message or "Database API error"
            if "violates row-level security policy" in error_message.lower() or e.code == "42501": 
                raise Exception(f"RLS policy violation for {target_table_name}: {error_message}") from e
            raise Exception(f"Database operation for {target_table_name} failed: {error_message}") from e
        except Exception as e:
            current_app.logger.error(f"[JournalService] Generic exception during insert to {target_table_name}: {str(e)}", exc_info=True)
            raise Exception(f"Unexpected error saving to {target_table_name}: {str(e)}") from e

@journal_bp.route('/api/journalEntry', methods=['POST'])
def save_detailed_journal_entry_route():
    current_app.logger.info(f"[JournalRoute] Received request for POST /api/journalEntry")
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            current_app.logger.warning("[JournalRoute] Missing or malformed Authorization header.")
            return jsonify({"error": "Authorization token is missing or malformed"}), 401

        token = auth_header.split(' ')[1]

        db_client = create_authenticated_supabase_client(token)
        if not db_client:
            current_app.logger.error("[JournalRoute] Failed to create authenticated Supabase client using token.")
            return jsonify({"error": "Failed to initialize database client for user"}), 500

        authenticated_user_id = None
        try:
            user_response = db_client.auth.get_user(jwt=token) 

            if user_response and user_response.user:
                authenticated_user_id = user_response.user.id
                current_app.logger.info(f"[JournalRoute] User ID from token (auth.get_user().user.id): {authenticated_user_id}")
            else:
                current_app.logger.error(f"[JournalRoute] Could not get user info from token. Response: {user_response}")
                return jsonify({"error": "Invalid token or unable to fetch user details"}), 401
        except Exception as e: 
            current_app.logger.error(f"[JournalRoute] Error getting user from token: {str(e)}", exc_info=True)
            if "Invalid JWT" in str(e) or "token is invalid" in str(e).lower() or "JWSError" in str(e):
                 return jsonify({"error": "Invalid or expired token"}), 401
            return jsonify({"error": f"Error validating token: {str(e)}"}), 401
        
        if not authenticated_user_id: 
             current_app.logger.error("[JournalRoute] Authenticated User ID could not be determined from token after get_user call.")
             return jsonify({"error": "User authentication failed."}), 401

        data = request.get_json()
        if not data:
            current_app.logger.error("[JournalRoute] No JSON data received in request body")
            return jsonify({"error": "No data provided"}), 400

        payload_user_id = data.get('userId') 
        current_app.logger.info(f"[JournalRoute] User ID from request payload (data.get('userId')): {payload_user_id}")
        
        if payload_user_id and payload_user_id != authenticated_user_id:
            current_app.logger.warning(
                f"[JournalRoute] Mismatch! Token User ID ({authenticated_user_id}) vs Payload User ID ({payload_user_id}). "
                f"Using Token User ID ({authenticated_user_id}) for database operation for security (RLS)."
            )
        
        content = data.get('content')
        mood_type = data.get('mood') 
        prompt_used = data.get('prompt_text') 
        questionnaire_data_str = data.get('questionnaire_data') 

        if content is None: 
            current_app.logger.error("[JournalRoute] 'content' field is missing in request data.")
            return jsonify({"error": "'content' is required."}), 400
        if mood_type is None: 
            current_app.logger.error("[JournalRoute] 'mood' field is missing in request data.")
            return jsonify({"error": "'mood' is required."}), 400

        current_app.logger.info(f"[JournalRoute] Data for save: User (token): {authenticated_user_id}, Mood: {mood_type}, Content len: {len(content) if content else 0}, Questionnaire len: {len(questionnaire_data_str) if questionnaire_data_str else 0}")

        journal_service = JournalService(db_client=db_client)
        
        result = journal_service.save_journal_to_journal_entry_table(
            user_id=authenticated_user_id, 
            content=content,
            mood=mood_type,
            prompt_text=prompt_used, 
            questionnaire_data_str=questionnaire_data_str
        )
        
        current_app.logger.info(f"[JournalRoute] Journal save operation completed. Success: {result.get('success')}, Message: {result.get('message')}")
        if result.get("success"):
            return jsonify(result), 201 
        else:
            return jsonify({"error": result.get("message", "Failed to save journal entry"), "details": result.get("data")}), 500

    except Exception as e:
        current_app.logger.error(f"[JournalRoute] General Unhandled Exception in /api/journalEntry: {str(e)}", exc_info=True)
        if "RLS policy violation" in str(e):
            return jsonify({"error": "Database security policy prevented saving the journal.", "details": str(e)}), 403 
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500
