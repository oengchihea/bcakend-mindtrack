import os
import random
import json
import logging
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Try to import google.generativeai, but make it optional
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

journal_prompt_bp = Blueprint('journal_prompt_bp', __name__)
MODEL_NAME = "gemini-1.5-flash-latest"

# Debug logging
logging.info("Journal prompt blueprint created successfully")

# Local prompt templates for fallback
# Updated for deployment - v1.2 (FIXED 404 ERROR)
GUIDED_PROMPTS = [
    "What was a highlight of your day, big or small?",
    "What challenged you today, and how did you approach it?",
    "Describe something you're grateful for right now.",
    "What's one thing you learned today?",
    "How are you feeling physically and emotionally at this moment?",
    "What would you like to improve about yourself?",
    "Describe a moment today that made you smile.",
    "What's something you're looking forward to?",
    "How did you take care of yourself today?",
    "What's a goal you're working towards?",
    "Describe a recent interaction that impacted you.",
    "What's something you're curious about?",
    "How did you handle stress today?",
    "What's a small victory you had today?",
    "What would you tell your future self about today?",
    "What's a habit you'd like to develop or break?",
    "Describe a place that makes you feel peaceful.",
    "What's something you're proud of accomplishing?",
    "How do you want to grow as a person?",
    "What's a dream or aspiration you have?",
]

MOOD_PROMPTS = {
    "happy": [
        "What made you feel so happy today?",
        "How can you share this happiness with others?",
        "What would you like to remember about this joyful moment?",
        "What's something that always brings a smile to your face?",
        "How can you create more moments like this?",
    ],
    "sad": [
        "What's weighing on your mind right now?",
        "How can you be kind to yourself during this difficult time?",
        "What would help you feel better right now?",
        "What's something that usually comforts you?",
        "How can you practice self-compassion today?",
    ],
    "anxious": [
        "What's causing you to feel anxious?",
        "What coping strategies work best for you?",
        "How can you practice self-compassion right now?",
        "What would help you feel more grounded?",
        "What's one small step you can take to reduce this anxiety?",
    ],
    "excited": [
        "What are you excited about?",
        "How can you channel this energy positively?",
        "What's the next step towards your excitement?",
        "How can you share this excitement with others?",
        "What does this excitement tell you about what matters to you?",
    ],
    "tired": [
        "What drained your energy today?",
        "How can you rest and recharge?",
        "What would help you feel more energized?",
        "What's something that helps you feel refreshed?",
        "How can you prioritize rest without feeling guilty?",
    ],
    "frustrated": [
        "What's frustrating you right now?",
        "How can you address this frustration constructively?",
        "What would help you feel more at peace?",
        "What's a different perspective you could consider?",
        "How can you channel this frustration into positive action?",
    ],
    "calm": [
        "What's contributing to your sense of calm?",
        "How can you maintain this peaceful state?",
        "What does this calmness teach you about yourself?",
        "How can you share this calm energy with others?",
        "What practices help you stay centered?",
    ]
}

TOPIC_PROMPTS = {
    "work": [
        "How did work go today?",
        "What's a challenge you're facing at work?",
        "What achievement at work are you proud of?",
        "What would make your work more fulfilling?",
        "How do you want to grow in your career?",
    ],
    "relationships": [
        "How are your relationships with others?",
        "What interaction stood out to you today?",
        "How can you strengthen your connections?",
        "What's a relationship you'd like to improve?",
        "How do you show love and care to others?",
    ],
    "health": [
        "How are you taking care of your health?",
        "What's your energy level like today?",
        "How can you prioritize your well-being?",
        "What's a health goal you're working towards?",
        "How does your body feel right now?",
    ],
    "personal_growth": [
        "What's something you're learning about yourself?",
        "How have you grown recently?",
        "What would you like to improve?",
        "What's a skill you'd like to develop?",
        "How do you want to evolve as a person?",
    ],
    "creativity": [
        "What creative project are you working on?",
        "How do you express your creativity?",
        "What inspires you to create?",
        "What's a creative challenge you're facing?",
        "How can you make more time for creative pursuits?",
    ]
}

def generate_prompts_with_ai(prompt_type, count, mood=None, topic=None):
    """Generate prompts using Gemini AI if available, otherwise use fallback"""
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        current_app.logger.warning("GEMINI_API_KEY not available or google-generativeai not installed, using fallback prompts")
        return generate_fallback_prompts(prompt_type, count, mood, topic)
    
    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            generation_config={
                "temperature": 0.8,
                "top_k": 40,
                "top_p": 0.9,
                "max_output_tokens": 350
            },
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
            ]
        )

        # Build the instruction based on prompt type
        if prompt_type == "mood" and mood:
            instruction = f"""Generate {count} empathetic, radically distinct, and deeply insightful journal questions for someone feeling "{mood}", for the "Mindtrack" app. Each question must help them explore this specific mood "{mood}" from a genuinely unique dimensional perspective. Ensure maximum variety in meaning and focus with every new set of prompts.

Return the prompts as a JSON object with a 'prompts' array in this exact format: {{"prompts": ["prompt1", "prompt2", "prompt3"]}}. DO NOT include any text before or after the JSON."""
        elif prompt_type == "topic" and topic:
            instruction = f"""Generate {count} radically distinct and deeply insightful journal questions about "{topic}" for the "Mindtrack" app. Each question must encourage focused reflection on how this topic uniquely influences the user's current mood, thoughts, and feelings from a different dimensional perspective each time.

Return the prompts as a JSON object with a 'prompts' array in this exact format: {{"prompts": ["prompt1", "prompt2", "prompt3"]}}. DO NOT include any text before or after the JSON."""
        else:
            instruction = f"""Generate {count} radically distinct and deeply insightful journal questions for the "Mindtrack" app. Each question must offer a unique dimensional exploration of the user's current emotional landscape, ensuring maximum variety in meaning and focus with every new set of prompts.

Return the prompts as a JSON object with a 'prompts' array in this exact format: {{"prompts": ["prompt1", "prompt2", "prompt3"]}}. DO NOT include any text before or after the JSON."""

        response = model.generate_content(instruction)
        json_string = response.text.strip()
        
        # Clean and parse JSON
        json_string = json_string.replace("```json\n", "").replace("```", "").strip()
        if not json_string.startswith("{"):
            json_string = "{" + json_string + "}"

        result = json.loads(json_string)
        if result.get('prompts') and isinstance(result['prompts'], list) and len(result['prompts']) > 0:
            current_app.logger.info(f"Successfully generated {len(result['prompts'])} AI prompts")
            return result['prompts']
        else:
            current_app.logger.warning("Invalid AI response format, using fallback")
            return generate_fallback_prompts(prompt_type, count, mood, topic)
            
    except Exception as e:
        current_app.logger.error(f"Error generating AI prompts: {e}")
        return generate_fallback_prompts(prompt_type, count, mood, topic)

def generate_fallback_prompts(prompt_type, count, mood=None, topic=None):
    """Generate prompts using local templates"""
    prompts = []
    
    if prompt_type == 'mood' and mood:
        mood_lower = mood.lower()
        available_prompts = []
        
        if mood_lower in MOOD_PROMPTS:
            available_prompts.extend(MOOD_PROMPTS[mood_lower])
        available_prompts.extend(GUIDED_PROMPTS)
        
        random.shuffle(available_prompts)
        prompts = available_prompts[:count]
        
    elif prompt_type == 'topic' and topic:
        topic_lower = topic.lower()
        available_prompts = []
        
        if topic_lower in TOPIC_PROMPTS:
            available_prompts.extend(TOPIC_PROMPTS[topic_lower])
        available_prompts.extend(GUIDED_PROMPTS)
        
        random.shuffle(available_prompts)
        prompts = available_prompts[:count]
        
    else:
        available_prompts = GUIDED_PROMPTS.copy()
        random.shuffle(available_prompts)
        prompts = available_prompts[:count]

    # Ensure we have the requested number of prompts
    while len(prompts) < count and len(GUIDED_PROMPTS) > 0:
        additional_prompts = [p for p in GUIDED_PROMPTS if p not in prompts]
        if additional_prompts:
            prompts.append(random.choice(additional_prompts))
        else:
            break

    return prompts

@journal_prompt_bp.route('/journal-prompt/test', methods=['GET'])
def test_journal_prompt():
    """Test endpoint to verify the blueprint is working"""
    return jsonify({"message": "Journal prompt blueprint is working!", "status": "success"}), 200

@journal_prompt_bp.route('/journal-prompt/generate', methods=['GET', 'POST'])
def generate_journal_prompts():
    """
    Generate journal prompts based on the request parameters.
    """
    current_app.logger.info(f"Generating journal prompts at {datetime.now(timezone.utc).isoformat()}")
    current_app.logger.info(f"Request method: {request.method}")

    if request.method == 'GET':
        # Return sample prompts for testing
        sample_prompts = [
            "What was a highlight of your day, big or small?",
            "What challenged you today, and how did you approach it?",
            "Describe something you're grateful for right now."
        ]
        return jsonify({"prompts": sample_prompts, "message": "Sample prompts for testing"}), 200

    # POST method handling
    # Get the request data
    incoming_data = request.get_json()
    if not incoming_data:
        current_app.logger.warning("No JSON data received for journal prompt generation.")
        # Return fallback prompts with message
        fallback_prompts = generate_fallback_prompts('guided', 3)
        return jsonify({"prompts": fallback_prompts, "message": "No data provided. Fallback prompts used."}), 200

    prompt_type = incoming_data.get('promptType', 'guided')
    count = incoming_data.get('count', 3)
    mood = incoming_data.get('mood')
    topic = incoming_data.get('topic')

    current_app.logger.info(f"Generating {count} prompts of type: {prompt_type}, mood: {mood}, topic: {topic}")

    try:
        # Try AI generation first, fallback to local prompts
        prompts = generate_prompts_with_ai(prompt_type, count, mood, topic)
        if not prompts:
            current_app.logger.error("Failed to generate any prompts")
            fallback_prompts = generate_fallback_prompts(prompt_type, count, mood, topic)
            return jsonify({"prompts": fallback_prompts, "message": "Failed to generate prompts. Fallback prompts used."}), 200

        current_app.logger.info(f"Successfully generated {len(prompts)} prompts")
        return jsonify({"prompts": prompts, "message": "Prompts generated successfully."}), 200

    except Exception as e:
        current_app.logger.error(f"Error generating prompts: {e}", exc_info=True)
        # Return fallback prompts, not a 500 error
        fallback_prompts = generate_fallback_prompts(prompt_type, count, mood, topic)
        return jsonify({"prompts": fallback_prompts, "message": "Fallback prompts used due to error."}), 200

# Alternative route for compatibility
@journal_prompt_bp.route('/journalPrompt/generate', methods=['GET', 'POST'])
def generate_journal_prompts_alt():
    """Alternative route for journal prompt generation"""
    return generate_journal_prompts()

# Debug: Print when module is loaded
print("Journal prompt module loaded successfully!")

@journal_prompt_bp.route('/', methods=['GET'])
def root():
    """Root route for journal prompt blueprint"""
    return jsonify({"message": "Journal prompt blueprint root route", "status": "success"}), 200