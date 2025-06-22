from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone
import random

journal_prompt_bp = Blueprint('journal_prompt_bp', __name__)

@journal_prompt_bp.route('/journal-prompt/generate', methods=['POST'])
def generate_journal_prompts():
    current_app.logger.info("Received request for /api/journal-prompt/generate at %s", datetime.now(timezone.utc).isoformat())
    data = request.get_json()
    if not data:
        current_app.logger.warning("No JSON data received for journal prompt generation at %s", datetime.now(timezone.utc).isoformat())
        return jsonify({"error": "No data provided"}), 400

    count = data.get('count', 3)
    mood = data.get('mood')
    topic = data.get('topic')
    prompt_type = data.get('promptType', 'guided')

    current_app.logger.info("Request parameters: count=%d, mood=%s, topic=%s, promptType=%s at %s", 
                            count, mood, topic, prompt_type, datetime.now(timezone.utc).isoformat())

    # Sample prompt list
    prompts = [
        "What was a highlight of your day, big or small?",
        "What challenged you today, and how did you approach it?",
        "Describe something you're grateful for right now.",
        "What's one thing you learned today?",
        "How are you feeling physically and emotionally at this moment?",
        "What's a goal you're working toward, and what progress did you make today?",
        "Describe a moment that made you smile recently.",
        "What's something you wish you had done differently today?",
        "How did you take care of yourself today?",
        "What's a memory from this week that stands out to you?"
    ]

    # Filter prompts based on mood, topic, or promptType
    filtered_prompts = prompts
    if prompt_type.lower() == 'mood' and mood:
        filtered_prompts = [p for p in filtered_prompts if mood.lower() in p.lower()]
    elif prompt_type.lower() == 'topic' and topic:
        filtered_prompts = [p for p in filtered_prompts if topic.lower() in p.lower()]

    # If no prompts match filters, return default prompts
    if not filtered_prompts:
        current_app.logger.info("No prompts matched filters (promptType=%s, mood=%s, topic=%s), returning %d default prompts at %s",
                                prompt_type, mood, topic, min(count, len(prompts)), datetime.now(timezone.utc).isoformat())
        filtered_prompts = prompts

    selected_prompts = random.sample(filtered_prompts, min(count, len(filtered_prompts)))
    current_app.logger.info("Generated %d prompts: %s at %s", len(selected_prompts), selected_prompts, datetime.now(timezone.utc).isoformat())
    return jsonify({"prompts": selected_prompts}), 200