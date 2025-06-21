import os
import uuid
import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, current_app
from supabase import create_client, Client
from postgrest import APIError

analyze_bp = Blueprint('analyze_bp', __name__)

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
            current_app.logger.warning(f"Auth attempt {attempt + 1} failed: No user response at {datetime.now(timezone.utc).isoformat()}")
        except Exception as e:
            current_app.logger.error(f"Auth client creation failed (attempt {attempt + 1}/{max_retries}): {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
            if attempt < max_retries - 1:
                current_app.logger.info("Reinitializing Supabase client due to auth failure at %s", datetime.now(timezone.utc).isoformat())
                app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
            else:
                return None, None
    return None, None

def analyze_journal_content(content, questionnaire_data, user_id):
    # Simulated analysis (replace with actual AI API call, e.g., Google Generative AI)
    try:
        current_app.logger.info(f"Analyzing journal content: {content[:50]}... for user {user_id} at {datetime.now(timezone.utc).isoformat()}")
        
        # Determine sentiment based on content and questionnaire
        sentiment = "neutral"
        if any(word in content.lower() for word in ["happy", "joy", "excited"]) or \
           (questionnaire_data and "mood_word" in questionnaire_data and any(word in questionnaire_data["mood_word"].lower() for word in ["happy", "joy"])):
            sentiment = "positive"
        elif any(word in content.lower() for word in ["sad", "depressed", "angry"]):
            sentiment = "negative"

        # Calculate score (0-10)
        score = 5  # Default
        if sentiment == "positive":
            score = 8
        elif sentiment == "negative":
            score = 3

        # Extract themes
        themes = []
        if "stress" in content.lower() or (questionnaire_data and "stress_level" in questionnaire_data and int(questionnaire_data["stress_level"]) > 5):
            themes.append("stress")
        if "grateful" in content.lower() or (questionnaire_data and "mood_word" in questionnaire_data and "grateful" in questionnaire_data["mood_word"].lower()):
            themes.append("gratitude")

        # Provide insights
        insights = "No specific insights detected."
        if themes:
            insights = f"Key themes include: {', '.join(themes)}."

        # Select emoji
        emoji = "😐"
        if sentiment == "positive":
            emoji = "😊"
        elif sentiment == "negative":
            emoji = "😔"

        current_app.logger.info(f"Analysis result: sentiment={sentiment}, score={score}, themes={themes}, insights={insights}, emoji={emoji} at {datetime.now(timezone.utc).isoformat()}")
        return {
            "sentiment": sentiment,
            "score": score,
            "themes": themes,
            "insights": insights,
            "emoji": emoji
        }
    except Exception as e:
        current_app.logger.error(f"Error in analyze_journal_content: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return {"error": f"Failed to analyze journal content: {str(e)}"}

@analyze_bp.route('/api/analyze-journal', methods=['POST'])
def analyze_and_save_journal():
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        current_app.logger.error(f"Authentication failed for user request at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Authentication failed"}), 401

    data = request.get_json()
    if not data or 'content' not in data or 'questionnaireData' not in data or 'userId' not in data:
        current_app.logger.warning(f"Missing required fields in request at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Missing required fields: content, questionnaireData, and userId"}), 400

    content = data['content']
    questionnaire_data = data['questionnaireData']
    try:
        # Validate userId from request matches authenticated userId
        if data['userId'] != user_id:
            current_app.logger.warning(f"Access denied: Mismatched user ID {data['userId']} vs {user_id} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "Access denied: Mismatched user ID"}), 403

        # Analyze the journal content
        current_app.logger.info(f"Received analyze-journal request for user {user_id} with content: {content[:50]}... at {datetime.now(timezone.utc).isoformat()}")
        analysis_result = analyze_journal_content(content, questionnaire_data, user_id)
        if "error" in analysis_result:
            current_app.logger.error(f"Analysis failed with error: {analysis_result['error']} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify(analysis_result), 500

        # Prepare data for saving to Supabase
        journal_entry = {
            "journal_id": str(uuid.uuid4()),
            "user_id": user_id,
            "entry_text": content,
            "mood": questionnaire_data.get("mood_word", "neutral"),
            "prompt_text": questionnaire_data.get("prompts_and_answers", [{}])[0].get("prompt") if questionnaire_data.get("prompts_and_answers") else None,
            "entry_type": questionnaire_data.get("journal_interaction_type", "Journal"),
            "questionnaire_data": json.dumps(questionnaire_data) if questionnaire_data else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": analysis_result["score"],  # Ensure score is saved
            "analysis": json.dumps(analysis_result)  # Ensure analysis is saved as JSON
        }

        current_app.logger.info(f"Attempting to save journal entry to Supabase: {journal_entry} at {datetime.now(timezone.utc).isoformat()}")
        res = client.table("journalEntry").insert(journal_entry).execute()
        if not res.data or len(res.data) == 0:
            current_app.logger.error(f"Failed to insert journal entry into Supabase at {datetime.now(timezone.utc).isoformat()}")
            raise Exception("Failed to insert journal entry into Supabase")

        journal_entry = res.data[0]
        current_app.logger.info(f"Successfully saved journal entry {journal_entry['journal_id']} with score {journal_entry['score']} at {datetime.now(timezone.utc).isoformat()}")

        return jsonify({
            "success": True,
            "data": journal_entry,
            "analysis": analysis_result
        }), 201

    except Exception as e:
        current_app.logger.error(f"Error analyzing or saving journal entry: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Failed to analyze or save journal entry: {str(e)}"}), 500