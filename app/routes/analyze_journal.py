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

def analyze_journal_content(content, questionnaire_data, user_id):
    # Placeholder for AI analysis (simulating Gemini API behavior)
    # In a real scenario, replace this with an actual AI API call (e.g., Google Generative AI)
    try:
        # Simulated analysis based on content and questionnaire data
        sentiment = "neutral"
        if "happy" in content.lower() or (questionnaire_data and "mood_word" in questionnaire_data and "happy" in questionnaire_data["mood_word"].lower()):
            sentiment = "positive"
        elif "sad" in content.lower():
            sentiment = "negative"

        score = 5  # Default score
        if sentiment == "positive":
            score = 8
        elif sentiment == "negative":
            score = 3

        themes = []
        if "stress" in content.lower():
            themes.append("stress")
        if "grateful" in content.lower():
            themes.append("gratitude")

        insights = "No specific insights detected."
        if themes:
            insights = f"Key themes include: {', '.join(themes)}."

        emoji = "😐"
        if sentiment == "positive":
            emoji = "😊"
        elif sentiment == "negative":
            emoji = "😔"

        return {
            "sentiment": sentiment,
            "score": score,
            "themes": themes,
            "insights": insights,
            "emoji": emoji
        }
    except Exception as e:
        current_app.logger.error(f"Error analyzing journal content: {e}", exc_info=True)
        return {"error": f"Failed to analyze journal content: {str(e)}"}

@analyze_bp.route('/api/analyze-journal', methods=['POST'])
def analyze_and_save_journal():
    client, user_id = get_auth_client(current_app._get_current_object())
    if not client or not user_id:
        return jsonify({"error": "Authentication failed"}), 401

    data = request.get_json()
    if not data or 'content' not in data or 'questionnaireData' not in data:
        return jsonify({"error": "Missing required fields: content and questionnaireData"}), 400

    content = data['content']
    questionnaire_data = data['questionnaireData']
    try:
        # Analyze the journal content
        analysis_result = analyze_journal_content(content, questionnaire_data, user_id)
        if "error" in analysis_result:
            return jsonify(analysis_result), 500

        # Prepare data for saving to Supabase
        journal_entry = {
            "journal_id": str(uuid.uuid4()),
            "user_id": user_id,
            "entry_text": content,
            "mood": questionnaire_data.get("mood_word", "neutral"),
            "prompt_text": questionnaire_data.get("prompts_and_answers", [{}])[0].get("prompt") if questionnaire_data.get("prompts_and_answers") else None,
            "entry_type": questionnaire_data.get("journal_interaction_type", "Journal"),
            "questionnaire_data": questionnaire_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "score": analysis_result["score"],
            "analysis": json.dumps(analysis_result)
        }

        # Save to Supabase
        res = client.table("journalEntry").insert(journal_entry).execute()
        if not res.data or len(res.data) == 0:
            raise Exception("Failed to insert journal entry into Supabase")

        journal_entry = res.data[0]
        current_app.logger.info(f"Successfully analyzed and saved journal entry {journal_entry['journal_id']}")

        return jsonify({
            "success": True,
            "data": journal_entry,
            "analysis": analysis_result
        }), 201

    except Exception as e:
        current_app.logger.error(f"Error analyzing or saving journal entry: {e}", exc_info=True)
        return jsonify({"error": f"Failed to analyze or save journal entry: {str(e)}"}), 500