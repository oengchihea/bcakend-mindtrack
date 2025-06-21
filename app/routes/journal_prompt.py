from flask import Blueprint, request, jsonify, current_app
import random

journal_prompt_bp = Blueprint('journal_prompt_bp', __name__)

@journal_prompt_bp.route('/api/journal-prompt/generate', methods=['POST'])
def generate_journal_prompts():
    current_app.logger.info("Received request for journal prompts at %s", datetime.now(timezone.utc).isoformat())
    data = request.get_json()
    if not data:
        current_app.logger.warning("No JSON data received for journal prompt generation")
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

    if mood:
        prompts = [p for p in prompts if mood.lower() in p.lower()]
    if topic:
        prompts = [p for p in prompts if topic.lower() in p.lower()]

    if not prompts:
        current_app.logger.warning("No prompts available after filtering by mood=%s and topic=%s", mood, topic)
        return jsonify({"error": "No prompts available for the given filters"}), 400

    selected_prompts = random.sample(prompts, min(count, len(prompts)))
    current_app.logger.info("Generated %d prompts: %s", len(selected_prompts), selected_prompts)
    return jsonify({"prompts": selected_prompts}), 200