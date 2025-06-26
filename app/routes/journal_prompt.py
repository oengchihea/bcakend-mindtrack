import os
import random
import json
import logging
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY_V2") or os.getenv("GEMINI_API_KEY_V1") or os.getenv("GEMINI_API_KEY")

# Debug logging for API key
if GEMINI_API_KEY:
    print(f"✅ GEMINI_API_KEY found: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-4:]}")
    logging.info(f"✅ GEMINI_API_KEY configured: {GEMINI_API_KEY[:10]}...")
else:
    print("❌ GEMINI_API_KEY not found in environment variables")
    logging.error("❌ GEMINI_API_KEY not found in environment variables")

# Try to import google.generativeai, but make it optional
try:
    import google.generativeai as genai
    if GEMINI_API_KEY:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
        print("✅ Gemini AI configured successfully")
        logging.info("✅ Gemini AI configured successfully")
    else:
        GEMINI_AVAILABLE = False
        print("❌ Gemini AI not available - missing API key")
        logging.warning("❌ Gemini AI not available - missing API key")
except ImportError as e:
    GEMINI_AVAILABLE = False
    genai = None
    print(f"❌ google-generativeai import failed: {e}")
    logging.error(f"❌ google-generativeai import failed: {e}")

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
    "happy": {
        "color": "#FFD700",  # Gold
        "prompts": [
            "What specific moment today made your heart feel light and joyful?",
            "How did you share your happiness with others today?",
            "What accomplishment, big or small, brought you this joy?",
            "Describe the physical sensations of your happiness right now.",
            "What positive changes in your life are making you feel this way?"
        ]
    },
    "sad": {
        "color": "#4682B4",  # Steel Blue
        "prompts": [
            "What specific situation is causing these heavy feelings?",
            "How are you physically experiencing this sadness?",
            "What kind of support would be most helpful right now?",
            "When did you start noticing these feelings today?",
            "What usually helps lift your spirits when you feel this way?"
        ]
    },
    "anxious": {
        "color": "#9370DB",  # Medium Purple
        "prompts": [
            "Can you pinpoint what's triggering your anxiety right now?",
            "Where in your body do you feel this anxiety most strongly?",
            "What grounding techniques have helped you before?",
            "What's the worst-case scenario you're worried about?",
            "What would help you feel more secure in this moment?"
        ]
    },
    "excited": {
        "color": "#FFA500",  # Orange
        "prompts": [
            "What future event is making your heart race with anticipation?",
            "How is this excitement affecting your energy levels?",
            "What creative ideas are flowing from this excitement?",
            "How can you channel this positive energy productively?",
            "What does this excitement tell you about your passions?"
        ]
    },
    "tired": {
        "color": "#778899",  # Light Slate Gray
        "prompts": [
            "What activities today consumed most of your energy?",
            "How is this fatigue affecting your thoughts and emotions?",
            "What type of rest do you need most right now?",
            "When did you last feel truly refreshed?",
            "What small steps could help restore your energy?"
        ]
    },
    "frustrated": {
        "color": "#CD5C5C",  # Indian Red
        "prompts": [
            "What specific situation is causing this frustration?",
            "How is this frustration manifesting in your body?",
            "What aspects of this situation are within your control?",
            "How could you approach this differently?",
            "What would resolution look like for you?"
        ]
    },
    "calm": {
        "color": "#98FB98",  # Pale Green
        "prompts": [
            "What helped create this sense of peace today?",
            "How does this calmness feel in your body?",
            "What practices helped you reach this state?",
            "How can you maintain this tranquility?",
            "What insights come to you in this peaceful state?"
        ]
    },
    "overwhelmed": {
        "color": "#B22222",  # Fire Brick
        "prompts": [
            "What responsibilities are weighing heaviest on you?",
            "How is this feeling of being overwhelmed showing up physically?",
            "What tasks could you delegate or postpone?",
            "When did you last take a real break?",
            "What small step could help reduce this pressure?"
        ]
    },
    "grateful": {
        "color": "#DDA0DD",  # Plum
        "prompts": [
            "What unexpected blessing caught your attention today?",
            "Who has positively impacted your life recently?",
            "What simple pleasure are you most thankful for?",
            "How has gratitude shifted your perspective?",
            "What personal growth are you grateful for?"
        ]
    },
    "hopeful": {
        "color": "#87CEEB",  # Sky Blue
        "prompts": [
            "What positive change are you looking forward to?",
            "What small signs of progress do you see?",
            "How is this hope influencing your actions?",
            "What dreams feel more possible now?",
            "Who or what has inspired this hope?"
        ]
    }
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
    print(f"🔍 AI Generation Request:")
    print(f"   GEMINI_AVAILABLE: {GEMINI_AVAILABLE}")
    print(f"   GEMINI_API_KEY present: {'✅' if GEMINI_API_KEY else '❌'}")
    print(f"   Prompt type: {prompt_type}, Count: {count}, Mood: {mood}, Topic: {topic}")
    
    current_app.logger.info(f"🔍 AI Generation - Available: {GEMINI_AVAILABLE}, API Key: {'Present' if GEMINI_API_KEY else 'Missing'}")
    
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        print("❌ AI generation not available - using fallback prompts")
        current_app.logger.warning("GEMINI_API_KEY not available or google-generativeai not installed, using fallback prompts")
        return generate_fallback_prompts(prompt_type, count, mood, topic)
    
    try:
        print(f"🚀 Initializing Gemini model: {MODEL_NAME}")
        current_app.logger.info(f"🚀 Initializing Gemini model: {MODEL_NAME}")
        
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

        # Build the instruction based on prompt type and mood
        if prompt_type == "mood" and mood:
            mood_color = MOOD_PROMPTS.get(mood.lower(), {}).get("color", "#808080")  # Default to gray if no color found
            instruction = f"""Generate {count} empathetic, deeply personal journal questions for someone feeling "{mood}". Each question should:
1. Help explore the specific emotion of "{mood}" from a unique perspective
2. Be colored with the hex code {mood_color} in the UI
3. Focus on physical sensations, thoughts, and emotional experiences
4. Be specific and direct about the feeling
5. Encourage detailed self-reflection

Return the prompts as a JSON object with 'prompts' and 'colors' arrays:
{{"prompts": ["prompt1", "prompt2"], "colors": ["{mood_color}", "{mood_color}"]}}

DO NOT include any text before or after the JSON."""
        elif prompt_type == "topic" and topic:
            instruction = f"""Generate {count} focused journal questions about "{topic}" that:
1. Connect the topic to current emotional state
2. Encourage detailed self-reflection
3. Explore personal growth and insights
4. Consider both challenges and opportunities
5. Prompt actionable self-discovery

Return the prompts as a JSON object with a 'prompts' array:
{{"prompts": ["prompt1", "prompt2"]}}

DO NOT include any text before or after the JSON."""
        else:
            instruction = """Generate {count} insightful journal questions that:
1. Explore current emotional state
2. Encourage mindful self-reflection
3. Focus on personal growth
4. Consider both challenges and achievements
5. Prompt actionable insights

Return the prompts as a JSON object with a 'prompts' array:
{{"prompts": ["prompt1", "prompt2"]}}

DO NOT include any text before or after the JSON."""

        print(f"🎯 Sending request to Gemini AI...")
        current_app.logger.info(f"🎯 Sending request to Gemini AI with instruction length: {len(instruction)}")
        
        response = model.generate_content(instruction)
        json_string = response.text.strip()
        
        print(f"📨 Gemini response received: {len(json_string)} characters")
        current_app.logger.info(f"📨 Gemini response received: {json_string[:200]}...")
        
        # Clean and parse JSON
        json_string = json_string.replace("```json\n", "").replace("```", "").strip()
        if not json_string.startswith("{"):
            json_string = "{" + json_string + "}"

        result = json.loads(json_string)
        if result.get('prompts') and isinstance(result['prompts'], list) and len(result['prompts']) > 0:
            print(f"✅ Successfully generated {len(result['prompts'])} AI prompts")
            current_app.logger.info(f"✅ Successfully generated {len(result['prompts'])} AI prompts")
            return result['prompts']
        else:
            print("❌ Invalid AI response format, using fallback")
            current_app.logger.warning("Invalid AI response format, using fallback")
            return generate_fallback_prompts(prompt_type, count, mood, topic)
            
    except Exception as e:
        print(f"❌ AI generation failed: {str(e)}")
        current_app.logger.error(f"❌ Error generating AI prompts: {e}", exc_info=True)
        return generate_fallback_prompts(prompt_type, count, mood, topic)

def generate_fallback_prompts(prompt_type, count, mood=None, topic=None):
    """Generate prompts using local templates"""
    prompts = []
    
    if prompt_type == 'mood' and mood:
        mood_lower = mood.lower()
        available_prompts = []
        
        if mood_lower in MOOD_PROMPTS:
            available_prompts.extend(MOOD_PROMPTS[mood_lower]['prompts'])
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