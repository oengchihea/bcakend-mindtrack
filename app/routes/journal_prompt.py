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
# Updated for deployment - v1.3 (Enhanced feeling-based prompts)
GUIDED_PROMPTS = [
    "Take a moment to pause and breathe. What emotions are flowing through you right now, and what might have sparked them?",
    "Think about the most meaningful interaction you had today. How did it make you feel, and what did you learn about yourself?",
    "What's one thing that happened today that you want to remember forever? Describe not just what happened, but how it made your heart feel.",
    "If your current mood had a color and texture, what would it be? What experiences today contributed to creating this emotional landscape?",
    "What challenge did you face today, and how did working through it reveal something new about your inner strength?",
    "Describe a moment today when you felt most like yourself. What were you doing, and what emotions were present?",
    "What's stirring in your heart about tomorrow? Are there feelings of excitement, worry, hope, or something else entirely?",
    "Think about your energy levels today. What drained you, what energized you, and how does that make you feel about your choices?",
    "What's one thing you're grateful for right now, and how does acknowledging it shift the emotional tone of your day?",
    "If you could send a message to yourself from a week ago, knowing what you know now about today's emotions, what would you say?",
    "What story is your body telling you today? Are you holding tension, feeling light, or experiencing something else entirely?",
    "Describe a small victory from today, no matter how tiny. How did achieving it make you feel about your capabilities?",
    "What relationship in your life is on your mind right now, and what emotions come up when you think about that person?",
    "If your day had a soundtrack, what would the main song be, and how does that music capture your emotional journey?",
    "What's one thing you learned about yourself today through the way you handled your emotions and experiences?"
]

MOOD_PROMPTS = {
    "happy": {
        "color": "#FFD700",  # Gold
        "prompts": [
            "Your happiness is radiating today! What specific moment made your heart sing, and how can you carry this joy forward?",
            "There's a lightness in your spirit right now. What actions, thoughts, or people contributed to creating this beautiful feeling?",
            "You're glowing with positivity! Describe the physical sensations of your happiness and what you want to remember about this moment.",
            "This joyful energy is precious. What meaningful connections or accomplishments are fueling your happiness today?",
            "Your smile seems to come from deep within. What unexpected blessing or realization brought this warmth to your heart?"
        ]
    },
    "sad": {
        "color": "#4682B4",  # Steel Blue
        "prompts": [
            "Your heart feels heavy right now, and that's okay. What specific situation or memory is weighing on you, and how can you be gentle with yourself?",
            "Sadness often carries important messages. What is this feeling trying to tell you about what matters most in your life?",
            "You're experiencing some deep emotions today. Where do you feel this sadness in your body, and what kind of comfort would help right now?",
            "Sometimes sadness connects us to our humanity. What loss, disappointment, or change is your heart processing right now?",
            "Your emotional depth is a gift, even when it hurts. What would you want to say to a dear friend who was feeling exactly as you do now?"
        ]
    },
    "anxious": {
        "color": "#9370DB",  # Medium Purple
        "prompts": [
            "Your mind seems to be racing with worries. What specific thoughts or upcoming events are creating this anxious energy in your body?",
            "Anxiety can feel overwhelming, but you're stronger than you know. What's the biggest fear your mind is focused on, and what would help you feel more grounded?",
            "Your nervous system is activated right now. What strategies have helped you find calm before, and how can you show yourself compassion in this moment?",
            "Sometimes anxiety is our mind's way of trying to protect us. What situation is triggering these feelings, and what control do you actually have over it?",
            "You're feeling uncertain about something important. What would you need to feel more secure, and what small step could help you move toward that feeling?"
        ]
    },
    "excited": {
        "color": "#FFA500",  # Orange
        "prompts": [
            "Your excitement is contagious! What future possibility or current experience has your heart racing with anticipation and joy?",
            "There's electric energy flowing through you. What dreams, plans, or opportunities are making you feel so alive and motivated right now?",
            "Your enthusiasm is beautiful to witness. How is this excitement changing the way you see possibilities in your life?",
            "You're buzzing with positive energy! What creative ideas or adventures are sparking this incredible feeling of aliveness?",
            "This excitement feels like pure life force. What does this energy tell you about what truly matters to you and lights you up inside?"
        ]
    },
    "tired": {
        "color": "#778899",  # Light Slate Gray
        "prompts": [
            "Your energy feels depleted today, and rest is calling. What demands or experiences have been drawing from your reserves, and what kind of restoration do you crave?",
            "Exhaustion often signals we've been giving more than we have. What responsibilities are weighing you down, and how can you be more protective of your energy?",
            "Your body and mind are asking for gentleness. What would true rest look like for you right now - physical, emotional, or mental?",
            "Sometimes tiredness reveals what we've been avoiding or pushing through. What emotions or situations might you need to address to find your vitality again?",
            "You deserve to honor your need for rest without guilt. What small changes could help you feel more energized and cared for in the coming days?"
        ]
    },
    "frustrated": {
        "color": "#CD5C5C",  # Indian Red
        "prompts": [
            "Frustration is pulsing through you, and that energy wants expression. What specific situation or person is triggering this feeling, and what do you really need right now?",
            "Your patience has been tested today. What expectations or hopes have been disappointed, and how can you channel this intensity constructively?",
            "Something important to you feels blocked or misunderstood. What values or needs aren't being met, and how might you advocate for yourself differently?",
            "This frustration has wisdom to offer. What is it revealing about your boundaries, standards, or deep desires that deserve attention?",
            "You're feeling the heat of unmet needs or blocked progress. What would resolution actually look like, and what's one step you could take toward it?"
        ]
    },
    "calm": {
        "color": "#98FB98",  # Pale Green
        "prompts": [
            "There's a beautiful stillness within you right now. What practices, thoughts, or experiences helped cultivate this sense of inner peace today?",
            "Your nervous system feels settled and grounded. What does this calmness reveal about what you need to thrive, and how can you protect this state?",
            "This tranquility is a gift you've given yourself. What wisdom or insights are emerging from this peaceful space in your heart and mind?",
            "You've found your center amidst life's chaos. What internal or external factors contributed to creating this sanctuary of calm?",
            "Peace radiates from you today. How does this serenity change your perspective on recent challenges or upcoming decisions?"
        ]
    },
    "overwhelmed": {
        "color": "#B22222",  # Fire Brick
        "prompts": [
            "Everything feels like too much right now, and that's a valid human experience. What specific responsibilities or emotions are creating this sense of drowning?",
            "Your plate feels impossibly full. What commitments or worries are demanding your attention, and which ones might you be able to release or delegate?",
            "The weight of everything is pressing down on you. What would it feel like to have just one area of your life feel manageable and under control?",
            "Sometimes overwhelm is our system's way of saying 'slow down.' What messages is your body sending you, and what would true relief look like?",
            "You're juggling so many pieces that something's got to give. What's the most important thing on your mind, and what can wait until you catch your breath?"
        ]
    },
    "grateful": {
        "color": "#DDA0DD",  # Plum
        "prompts": [
            "Gratitude is flowing through your heart like warm honey. What unexpected gift or blessing has opened your eyes to abundance today?",
            "You're seeing beauty in the ordinary today. What simple pleasure or meaningful connection has filled you with appreciation and wonder?",
            "Your heart is full of thankfulness. What person, experience, or personal growth are you most grateful for, and how has it changed you?",
            "Appreciation is your superpower today. What challenge or difficulty has revealed hidden gifts or strength you didn't know you possessed?",
            "This gratitude feels transformative. How is acknowledging these blessings shifting your perspective on other areas of your life?"
        ]
    },
    "hopeful": {
        "color": "#87CEEB",  # Sky Blue
        "prompts": [
            "Hope is lighting up your inner landscape like dawn breaking. What positive possibility or emerging change is making your heart feel lighter?",
            "You can sense better days ahead. What small signs of progress or improvement are you noticing in yourself or your circumstances?",
            "There's a spark of optimism in your chest. What dreams or goals feel more achievable now, and what's shifted to create this sense of possibility?",
            "Hope is your compass pointing toward brighter tomorrows. What vision of your future is inspiring you to keep moving forward with faith?",
            "This feeling of hope is medicine for your soul. What or who has reminded you that growth, healing, and positive change are always possible?"
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
            
            # For mood-based prompts, return both prompts and colors
            if prompt_type == "mood" and mood and 'colors' in result:
                return {
                    "prompts": result['prompts'],
                    "colors": result.get('colors', [MOOD_PROMPTS.get(mood.lower(), {}).get("color", "#808080")] * len(result['prompts']))
                }
            else:
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
    colors = []
    
    if prompt_type == 'mood' and mood:
        mood_lower = mood.lower()
        available_prompts = []
        mood_color = "#808080"  # Default gray
        
        if mood_lower in MOOD_PROMPTS:
            mood_data = MOOD_PROMPTS[mood_lower]
            available_prompts.extend(mood_data['prompts'])
            mood_color = mood_data['color']
        
        # Add some general prompts if needed
        available_prompts.extend(GUIDED_PROMPTS)
        
        # Shuffle and select
        random.shuffle(available_prompts)
        prompts = available_prompts[:count]
        colors = [mood_color] * len(prompts)
        
    elif prompt_type == 'topic' and topic:
        topic_lower = topic.lower()
        available_prompts = []
        
        if topic_lower in TOPIC_PROMPTS:
            available_prompts.extend(TOPIC_PROMPTS[topic_lower])
        available_prompts.extend(GUIDED_PROMPTS)
        
        random.shuffle(available_prompts)
        prompts = available_prompts[:count]
        colors = ["#6B73FF"] * len(prompts)  # Default blue for topics
        
    else:
        # General guided prompts
        available_prompts = GUIDED_PROMPTS.copy()
        random.shuffle(available_prompts)
        prompts = available_prompts[:count]
        colors = ["#6B73FF"] * len(prompts)  # Default blue

    # Ensure we have the requested number of prompts
    while len(prompts) < count and len(GUIDED_PROMPTS) > 0:
        additional_prompts = [p for p in GUIDED_PROMPTS if p not in prompts]
        if additional_prompts:
            new_prompt = random.choice(additional_prompts)
            prompts.append(new_prompt)
            colors.append("#6B73FF" if prompt_type != 'mood' else mood_color)
        else:
            break

    return {"prompts": prompts, "colors": colors} if prompt_type == 'mood' and mood else prompts

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
        prompts_result = generate_prompts_with_ai(prompt_type, count, mood, topic)
        
        # Handle different response formats
        if isinstance(prompts_result, dict) and 'prompts' in prompts_result:
            # Mood-based response with colors
            prompts = prompts_result['prompts']
            colors = prompts_result.get('colors', [])
            
            if not prompts:
                current_app.logger.error("Failed to generate any prompts")
                fallback_result = generate_fallback_prompts(prompt_type, count, mood, topic)
                if isinstance(fallback_result, dict):
                    return jsonify({
                        "prompts": fallback_result['prompts'], 
                        "colors": fallback_result['colors'],
                        "message": "Failed to generate prompts. Fallback prompts used."
                    }), 200
                else:
                    return jsonify({
                        "prompts": fallback_result, 
                        "message": "Failed to generate prompts. Fallback prompts used."
                    }), 200

            current_app.logger.info(f"Successfully generated {len(prompts)} prompts with colors")
            return jsonify({
                "prompts": prompts, 
                "colors": colors,
                "message": "Prompts generated successfully."
            }), 200
            
        elif isinstance(prompts_result, list):
            # Standard response format
            prompts = prompts_result
            
            if not prompts:
                current_app.logger.error("Failed to generate any prompts")
                fallback_prompts = generate_fallback_prompts(prompt_type, count, mood, topic)
                if isinstance(fallback_prompts, dict):
                    return jsonify({
                        "prompts": fallback_prompts['prompts'], 
                        "colors": fallback_prompts.get('colors', []),
                        "message": "Failed to generate prompts. Fallback prompts used."
                    }), 200
                else:
                    return jsonify({
                        "prompts": fallback_prompts, 
                        "message": "Failed to generate prompts. Fallback prompts used."
                    }), 200

            current_app.logger.info(f"Successfully generated {len(prompts)} prompts")
            return jsonify({"prompts": prompts, "message": "Prompts generated successfully."}), 200
        
        else:
            # Fallback case
            current_app.logger.error("Invalid prompts result format")
            fallback_result = generate_fallback_prompts(prompt_type, count, mood, topic)
            if isinstance(fallback_result, dict):
                return jsonify({
                    "prompts": fallback_result['prompts'], 
                    "colors": fallback_result.get('colors', []),
                    "message": "Using fallback prompts."
                }), 200
            else:
                return jsonify({
                    "prompts": fallback_result, 
                    "message": "Using fallback prompts."
                }), 200

    except Exception as e:
        current_app.logger.error(f"Error generating prompts: {e}", exc_info=True)
        # Return fallback prompts, not a 500 error
        fallback_result = generate_fallback_prompts(prompt_type, count, mood, topic)
        if isinstance(fallback_result, dict):
            return jsonify({
                "prompts": fallback_result['prompts'], 
                "colors": fallback_result.get('colors', []),
                "message": "Fallback prompts used due to error."
            }), 200
        else:
            return jsonify({
                "prompts": fallback_result, 
                "message": "Fallback prompts used due to error."
            }), 200

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