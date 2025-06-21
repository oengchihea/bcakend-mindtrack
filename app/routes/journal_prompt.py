from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone
import random

journal_prompt_bp = Blueprint('journal_prompt_bp', __name__)

@journal_prompt_bp.route('/api/journal-prompt/generate', methods=['POST'])
def generate_journal_prompts():
    current_app.logger.info("Received request for journal prompts at %s", datetime.now(timezone.utc).isoformat())
    data = request.get_json()
    if not data:
        current_app.logger.warning("No JSON data received for journal prompt generation at %s", datetime.now(timezone.utc).isoformat())
        return jsonify({"error": "No data provided"}), 400

    count = data.get('count', 3)
    mood = data.get('mood')
    topic = data.get('topic')

    # Sample prompt list (replace with dynamic generation if needed)
    prompts = [
        "What was a highlight of your day, big or small?",
        "What challenged you today, and how did you approach it?",
        "Describe something you're grateful for right now.",
        "What's one thing you learned today?",
        "How are you feeling physically and emotionally at this moment?",
    ]

    # Filter prompts based on mood or topic
    filtered_prompts = prompts
    if mood:
        filtered_prompts = [p for p in filtered_prompts if mood.lower() in p.lower()]
    if topic:
        filtered_prompts = [p for p in filtered_prompts if topic.lower() in p.lower()]

    # If no prompts match filters, return a subset of default prompts
    if not filtered_prompts:
        current_app.logger.info("No prompts matched filters (mood=%s, topic=%s), returning %d default prompts at %s", 
                                mood, topic, min(count, len(prompts)), datetime.now(timezone.utc).isoformat())
        filtered_prompts = random.sample(prompts, min(count, len(prompts)))
    
    selected_prompts = random.sample(filtered_prompts, min(count, len(filtered_prompts)))
    current_app.logger.info("Generated %d prompts: %s at %s", len(selected_prompts), selected_prompts, datetime.now(timezone.utc).isoformat())
    return jsonify({"prompts": selected_prompts}), 200