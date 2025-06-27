import os
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app, g
from supabase import create_client, Client
from postgrest import APIError
from .auth import auth_required

journal_bp = Blueprint('journal_bp', __name__)

def get_service_client():
    """
    Creates a Supabase client with the service role key to bypass RLS.
    This should be used with extreme caution and only for authorized writes.
    """
    service_key = current_app.config.get('SUPABASE_SERVICE_ROLE_KEY')
    if not service_key:
        current_app.logger.error("FATAL: SUPABASE_SERVICE_ROLE_KEY is not configured.")
        return None
    try:
        url = current_app.config['SUPABASE_URL']
        return create_client(
            supabase_url=url,
            supabase_key=service_key
        )
    except Exception as e:
        current_app.logger.error(f"Failed to create service client: {e}")
        return None

@journal_bp.route('/journal/entries', methods=['GET', 'DELETE'])
@auth_required
def handle_journal_entries():
    current_app.logger.info(f"Route /api/journal/entries hit with method: {request.method} at %s", datetime.now(timezone.utc).isoformat())
    user_id = g.user.id
    client = current_app.supabase # RLS is handled by the auth_required decorator

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

@journal_bp.route('/journal/entries/<journal_id>', methods=['DELETE'])
@auth_required
def delete_journal_entry(journal_id):
    """Delete a specific journal entry by journal_id"""
    current_app.logger.info(f"Route /api/journal/entries/{journal_id} hit with DELETE method at {datetime.now(timezone.utc).isoformat()}")
    user_id = g.user.id

    # Get the service client for RLS-bypassed operations
    service_client = get_service_client()
    if not service_client:
        return jsonify({"error": "Server configuration error. Cannot delete data."}), 500

    try:
        # First, verify the journal entry exists and belongs to the user
        check_result = current_app.supabase.table("journalEntry").select("journal_id, user_id").eq("journal_id", journal_id).eq("user_id", user_id).execute()
        
        if not check_result.data:
            current_app.logger.warning(f"Journal entry {journal_id} not found or doesn't belong to user {user_id}")
            return jsonify({"error": "Journal entry not found or you don't have permission to delete it"}), 404

        # Delete the journal entry using service client to bypass RLS
        delete_result = service_client.table("journalEntry").delete().eq("journal_id", journal_id).eq("user_id", user_id).execute()
        
        if delete_result.data:
            current_app.logger.info(f"Successfully deleted journal entry {journal_id} for user {user_id}")
            return jsonify({"message": "Journal entry deleted successfully", "deleted_id": journal_id}), 200
        else:
            current_app.logger.error(f"Failed to delete journal entry {journal_id} - no data returned")
            return jsonify({"error": "Failed to delete journal entry"}), 500

    except APIError as e:
        current_app.logger.error(f"Supabase API Error on DELETE: {e.message} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Database error: {e.message}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error deleting journal entry {journal_id}: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": "Failed to delete journal entry"}), 500

@journal_bp.route('/journalEntry', methods=['POST', 'PUT', 'DELETE'])
@auth_required
def save_journal_entry():
    user_id = g.user.id

    # Step 2: Get the privileged service client to perform the write.
    # This bypasses any RLS issues on the table.
    service_client = get_service_client()
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

        elif request.method == 'DELETE':
            # Handle DELETE requests with query parameters
            journal_id = request.args.get('journalId')
            request_user_id = request.args.get('userId')
            
            current_app.logger.info(f"DELETE /api/journalEntry with journalId={journal_id}, userId={request_user_id}")
            
            if not journal_id:
                return jsonify({"error": "journalId parameter is required"}), 400
            
            # Verify user_id matches authenticated user
            if request_user_id and request_user_id != user_id:
                return jsonify({"error": "User ID mismatch"}), 403

            try:
                # First, verify the journal entry exists and belongs to the user
                check_result = current_app.supabase.table("journalEntry").select("journal_id, user_id").eq("journal_id", journal_id).eq("user_id", user_id).execute()
                
                if not check_result.data:
                    current_app.logger.warning(f"Journal entry {journal_id} not found or doesn't belong to user {user_id}")
                    return jsonify({"error": "Journal entry not found or you don't have permission to delete it"}), 404

                # Delete the journal entry using service client to bypass RLS
                delete_result = service_client.table("journalEntry").delete().eq("journal_id", journal_id).eq("user_id", user_id).execute()
                
                if delete_result.data:
                    current_app.logger.info(f"Successfully deleted journal entry {journal_id} for user {user_id}")
                    return jsonify({"message": "Journal entry deleted successfully", "deleted_id": journal_id}), 200
                else:
                    current_app.logger.error(f"Failed to delete journal entry {journal_id} - no data returned")
                    return jsonify({"error": "Failed to delete journal entry"}), 500

            except APIError as e:
                current_app.logger.error(f"Supabase API Error on DELETE: {e.message}")
                return jsonify({"error": f"Database error: {e.message}"}), 500
            except Exception as e:
                current_app.logger.error(f"Error deleting journal entry {journal_id}: {e}")
                return jsonify({"error": "Failed to delete journal entry"}), 500

    except Exception as e:
        current_app.logger.error(f"Error saving entry: {e}", exc_info=True)
        return jsonify({"error": f"A server error occurred: {str(e)}"}), 500

@journal_bp.route('/journal/entry/<journal_id>', methods=['DELETE'])
@auth_required
def delete_journal_entry_alt(journal_id):
    """Alternative delete endpoint for journal entry by journal_id"""
    current_app.logger.info(f"Route /api/journal/entry/{journal_id} hit with DELETE method at {datetime.now(timezone.utc).isoformat()}")
    user_id = g.user.id
    request_user_id = request.args.get('userId')

    # Get the service client for RLS-bypassed operations
    service_client = get_service_client()
    if not service_client:
        return jsonify({"error": "Server configuration error. Cannot delete data."}), 500

    # Verify user_id matches if provided
    if request_user_id and request_user_id != user_id:
        return jsonify({"error": "User ID mismatch"}), 403

    try:
        # First, verify the journal entry exists and belongs to the user
        check_result = current_app.supabase.table("journalEntry").select("journal_id, user_id").eq("journal_id", journal_id).eq("user_id", user_id).execute()
        
        if not check_result.data:
            current_app.logger.warning(f"Journal entry {journal_id} not found or doesn't belong to user {user_id}")
            return jsonify({"error": "Journal entry not found or you don't have permission to delete it"}), 404

        # Delete the journal entry using service client to bypass RLS
        delete_result = service_client.table("journalEntry").delete().eq("journal_id", journal_id).eq("user_id", user_id).execute()
        
        if delete_result.data:
            current_app.logger.info(f"Successfully deleted journal entry {journal_id} for user {user_id}")
            return jsonify({"message": "Journal entry deleted successfully", "deleted_id": journal_id}), 200
        else:
            current_app.logger.error(f"Failed to delete journal entry {journal_id} - no data returned")
            return jsonify({"error": "Failed to delete journal entry"}), 500

    except APIError as e:
        current_app.logger.error(f"Supabase API Error on DELETE: {e.message} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Database error: {e.message}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error deleting journal entry {journal_id}: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": "Failed to delete journal entry"}), 500

@journal_bp.route('/journalEntry/<journal_id>', methods=['DELETE'])
@auth_required
def delete_journal_entry_alt2(journal_id):
    """Another alternative delete endpoint for journal entry by journal_id"""
    current_app.logger.info(f"Route /api/journalEntry/{journal_id} hit with DELETE method at {datetime.now(timezone.utc).isoformat()}")
    user_id = g.user.id
    request_user_id = request.args.get('userId')

    # Get the service client for RLS-bypassed operations
    service_client = get_service_client()
    if not service_client:
        return jsonify({"error": "Server configuration error. Cannot delete data."}), 500

    # Verify user_id matches if provided
    if request_user_id and request_user_id != user_id:
        return jsonify({"error": "User ID mismatch"}), 403

    try:
        # First, verify the journal entry exists and belongs to the user
        check_result = current_app.supabase.table("journalEntry").select("journal_id, user_id").eq("journal_id", journal_id).eq("user_id", user_id).execute()
        
        if not check_result.data:
            current_app.logger.warning(f"Journal entry {journal_id} not found or doesn't belong to user {user_id}")
            return jsonify({"error": "Journal entry not found or you don't have permission to delete it"}), 404

        # Delete the journal entry using service client to bypass RLS
        delete_result = service_client.table("journalEntry").delete().eq("journal_id", journal_id).eq("user_id", user_id).execute()
        
        if delete_result.data:
            current_app.logger.info(f"Successfully deleted journal entry {journal_id} for user {user_id}")
            return jsonify({"message": "Journal entry deleted successfully", "deleted_id": journal_id}), 200
        else:
            current_app.logger.error(f"Failed to delete journal entry {journal_id} - no data returned")
            return jsonify({"error": "Failed to delete journal entry"}), 500

    except APIError as e:
        current_app.logger.error(f"Supabase API Error on DELETE: {e.message} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Database error: {e.message}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error deleting journal entry {journal_id}: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": "Failed to delete journal entry"}), 500
