import os
import uuid
from datetime import datetime, timezone
import json
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest.exceptions import APIError

# Initialize Supabase client (typically with anon key, auth is handled by token)
# This global client might be used for non-user-specific tasks if any,
# but for user operations, we'll use an authenticated client.
try:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY") # This should be your ANON key
    if not SUPABASE_URL or not SUPABASE_KEY:
        current_app.logger.error("SUPABASE_URL or SUPABASE_KEY not found in environment variables.")
        # You might want to raise an exception or handle this more gracefully
    # supabase_global_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    # current_app is not available at import time for logging here.
    # Consider logging this inside create_app or on first request.
    print(f"Error initializing global Supabase client: {e}")


journal_bp = Blueprint('journal_bp', __name__)

# --- Helper Function to Create Authenticated Supabase Client ---
def create_authenticated_supabase_client(jwt_token: str) -> Client | None:
    """
    Creates a Supabase client instance authenticated with the provided JWT.
    """
    if not SUPABASE_URL or not SUPABASE_KEY: # Re-check in case of import-time issues
        current_app.logger.error("SUPABASE_URL or SUPABASE_KEY missing for authenticated client creation.")
        return None
    try:
        # The supabase-py client automatically uses the Authorization header if present.
        # We ensure it's correctly formatted.
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "apikey": SUPABASE_KEY # The anon key is still required by Supabase for API gateway access
        }
        # For supabase-py v1.x and below:
        # from supabase.lib.client_options import ClientOptions
        # return create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(headers=headers))
        # For supabase-py v2.x:
        # The client itself doesn't take headers directly in create_client for user-specific auth.
        # Instead, you'd typically use client.auth.set_session(access_token, refresh_token)
        # or ensure the token is passed with each request if the library doesn't handle it globally
        # based on an initial setup.
        # However, for direct table operations with RLS, the Authorization header is key.
        # Let's assume a simple client creation and rely on the header for RLS.
        # A common pattern is to create a new client instance for each request with the token.
        
        # For supabase-py v2.x, the recommended way to make authenticated calls
        # is often by setting the session or ensuring the HTTP client used internally
        # by supabase-py includes the Authorization header.
        # A simpler approach for direct RLS check is to ensure the `postgrest_client`
        # within the Supabase client has the auth header.
        
        # Let's use a more direct way to ensure the header is used for PostgREST calls
        # This might need adjustment based on the exact version and features of supabase-py
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        client.postgrest.auth(jwt_token) # This is a common way for supabase-py v2+
        return client
    except Exception as e:
        current_app.logger.error(f"Failed to create authenticated Supabase client: {e}", exc_info=True)
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
        current_app.logger.warning("[JournalService] AI analysis service URL or API key not configured. Using placeholder analysis.")
        return {
            "insights": f"Journal entry analyzed (placeholder). Mood context: {mood_context or 'N/A'}. Content snippet: {content[:50]}...",
            "sentiment": "neutral",
            "emoji": "😐", # Placeholder emoji
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

        # Determine entry type
        entry_type = "Standard Journal"
        if mood and "ai_guided" in mood.lower(): # Example, adjust as needed
            entry_type = "AI Guided Journal"
        elif prompt_text:
            entry_type = "Prompted Journal"
        
        # Analyze content (using placeholder)
        analysis_result = self._analyze_content_placeholder(content, mood_context=mood)

        # Prepare data for database insertion
        db_entry_data = {
            "journal_id": str(uuid.uuid4()),
            "user_id": user_id,  # CRITICAL: This user_id MUST match auth.uid() for RLS
            "entry_text": content,
            "mood": mood,
            "prompt_text": prompt_text,
            "entry_type": entry_type,
            "analysis": json.dumps(analysis_result), # Store analysis as JSON string
            "created_at": datetime.now(timezone.utc).isoformat(),
            "questionnaire_data": questionnaire_data_str # Store as stringified JSON or parse if column is JSONB
        }

        current_app.logger.info(f"[JournalService] Data for '{target_table_name}' insert: {json.dumps(db_entry_data, indent=2)}")

        try:
            response = self.supabase.table(target_table_name).insert(db_entry_data).execute()
            current_app.logger.info(f"[JournalService] Successfully inserted journal to '{target_table_name}'. Response: {response.data}")
            # Assuming response.data contains the inserted record or relevant info
            return {"success": True, "message": "Journal entry saved successfully.", "data": response.data}
        except APIError as e:
            current_app.logger.error(f"[JournalService] Supabase APIError during insert to {target_table_name}: {e.json()}", exc_info=True)
            # Re-raise with a more specific message if it's an RLS violation
            if e.code == "42501" or ("violates row-level security policy" in e.message): # Check PostgREST error code for RLS
                raise Exception(f"RLS policy violation for {target_table_name}: {e.message}") from e
            raise Exception(f"Database operation for {target_table_name} failed: {e.message}") from e
        except Exception as e:
            current_app.logger.error(f"[JournalService] Generic exception during insert to {target_table_name}: {str(e)}", exc_info=True)
            raise Exception(f"Unexpected error saving to {target_table_name}: {str(e)}") from e


# --- Flask Route for Saving Journal Entries ---
@journal_bp.route('/journalEntry', methods=['POST']) # Assuming this is the endpoint for saving journals
def save_detailed_journal_entry_route():
    current_app.logger.info(f"[JournalRoute] HIT /api/journal POST (save_detailed_journal_entry_route)")
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            current_app.logger.error("[JournalRoute] Missing or malformed Authorization header")
            return jsonify({"error": "Authorization token is missing or malformed"}), 401

        token = auth_header.split(' ')[1]
        current_app.logger.info(f"[JournalRoute] Received token (last 10 chars): ...{token[-10:]}")

        db_client = create_authenticated_supabase_client(token)
        if not db_client:
            current_app.logger.error("[JournalRoute] Failed to create authenticated Supabase client using token.")
            return jsonify({"error": "Failed to initialize database client for user"}), 500

        authenticated_user_id = None
        try:
            user_response = db_client.auth.get_user() # Fetches user based on token set in client
            if user_response and user_response.user:
                authenticated_user_id = user_response.user.id
                current_app.logger.info(f"[JournalRoute] User ID from token (auth.uid() equivalent): {authenticated_user_id}")
            else:
                current_app.logger.error(f"[JournalRoute] Could not get user info from token. Response: {user_response}")
                return jsonify({"error": "Invalid token or unable to fetch user details"}), 401
        except Exception as e:
            current_app.logger.error(f"[JournalRoute] Error getting user from token: {str(e)}", exc_info=True)
            return jsonify({"error": "Error validating token"}), 401
        
        if not authenticated_user_id: # Should be caught above, but as a safeguard
             current_app.logger.error("[JournalRoute] Authenticated User ID could not be determined from token.")
             return jsonify({"error": "User authentication failed."}), 401


        data = request.get_json()
        if not data:
            current_app.logger.error("[JournalRoute] No JSON data received in request body")
            return jsonify({"error": "No data provided"}), 400

        payload_user_id = data.get('userId') # User ID sent from Flutter client
        current_app.logger.info(f"[JournalRoute] User ID from request payload (data.get('userId')): {payload_user_id}")
        
        # Security Check: Optionally compare payload_user_id with authenticated_user_id
        if payload_user_id and payload_user_id != authenticated_user_id:
            current_app.logger.warning(
                f"[JournalRoute] Mismatch! Token User ID ({authenticated_user_id}) vs Payload User ID ({payload_user_id}). "
                f"Proceeding with Token User ID for database operation due to RLS."
            )
            # Depending on strictness, you might choose to reject here, but RLS will enforce it anyway if db_entry_data.user_id is set to authenticated_user_id

        content = data.get('content')
        mood_type = data.get('mood', 'Standard Journal') # Default if not provided
        prompt_used = data.get('prompt_text') # Can be None
        questionnaire_data_str = data.get('questionnaire_data') # Stringified JSON from Flutter

        if content is None: # Basic validation
            current_app.logger.error("[JournalRoute] 'content' field is missing in request data.")
            return jsonify({"error": "'content' is required."}), 400

        current_app.logger.info(f"[JournalRoute] /api/journal POST - Received data: User (from token): {authenticated_user_id}, Mood/Type: {mood_type}, Content Present: {bool(content)}, Questionnaire Present: {bool(questionnaire_data_str)}")

        journal_service = JournalService(db_client=db_client)
        
        current_app.logger.info(f"[JournalRoute] Calling journal_service.save_journal_to_journal_entry_table with user_id: {authenticated_user_id} (derived from token)")

        # CRITICAL: Use the authenticated_user_id from the token for the database operation
        # This ensures the 'user_id' field in the database matches auth.uid() for RLS.
        result = journal_service.save_journal_to_journal_entry_table(
            user_id=authenticated_user_id, 
            content=content,
            mood=mood_type,
            prompt_used=prompt_used,
            questionnaire_data_str=questionnaire_data_str
        )
        
        current_app.logger.info(f"[JournalRoute] Journal save operation completed. Result: {result.get('message')}")
        if result.get("success"):
            return jsonify(result), 200 # Or 201 for created
        else:
            # This path might not be hit if exceptions are raised directly
            return jsonify(result), 500 

    except Exception as e:
        # Log the full traceback for unexpected errors
        current_app.logger.error(f"[JournalRoute] /api/journal POST - General Unhandled Exception: {str(e)}", exc_info=True)
        # Check if the error message is the RLS violation to return a more specific error
        if "RLS policy violation" in str(e) or ("violates row-level security policy" in str(e)):
            return jsonify({"error": f"Database security policy prevented saving journal. Details: {str(e)}"}), 403 # Forbidden
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500


# You would register this blueprint in your main app factory (e.g., app/__init__.py)
# from .routes.journal import journal_bp
# app.register_blueprint(journal_bp, url_prefix='/api') # Example prefix