import os
import random
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone

journal_prompt_bp = Blueprint('journal_prompt_bp', __name__)

# Local prompt templates for different types
# Updated for deployment - v1.1
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

@journal_prompt_bp.route('/journal-prompt/generate', methods=['POST'])
def generate_journal_prompts():
    """
    Generate journal prompts based on the request parameters.
    """
    current_app.logger.info(f"Generating journal prompts at {datetime.now(timezone.utc).isoformat()}")

    # Get the request data
    incoming_data = request.get_json()
    if not incoming_data:
        current_app.logger.warning("No JSON data received for journal prompt generation.")
        return jsonify({"error": "No data provided"}), 400

    prompt_type = incoming_data.get('promptType', 'guided')
    count = incoming_data.get('count', 3)
    mood = incoming_data.get('mood')
    topic = incoming_data.get('topic')

    current_app.logger.info(f"Generating {count} prompts of type: {prompt_type}, mood: {mood}, topic: {topic}")

    try:
        prompts = []
        
        if prompt_type == 'mood' and mood:
            # Generate mood-specific prompts
            mood_lower = mood.lower()
            available_prompts = []
            
            # Get prompts for the specific mood
            if mood_lower in MOOD_PROMPTS:
                available_prompts.extend(MOOD_PROMPTS[mood_lower])
            
            # Add some general guided prompts as fallback
            available_prompts.extend(GUIDED_PROMPTS)
            
            # Shuffle and select the requested number
            random.shuffle(available_prompts)
            prompts = available_prompts[:count]
            
        elif prompt_type == 'topic' and topic:
            # Generate topic-specific prompts
            topic_lower = topic.lower()
            available_prompts = []
            
            # Get prompts for the specific topic
            if topic_lower in TOPIC_PROMPTS:
                available_prompts.extend(TOPIC_PROMPTS[topic_lower])
            
            # Add some general guided prompts as fallback
            available_prompts.extend(GUIDED_PROMPTS)
            
            # Shuffle and select the requested number
            random.shuffle(available_prompts)
            prompts = available_prompts[:count]
            
        else:
            # Generate general guided prompts
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

        current_app.logger.info(f"Successfully generated {len(prompts)} prompts")
        return jsonify({"prompts": prompts}), 200

    except Exception as e:
        current_app.logger.error(f"Error generating prompts: {e}", exc_info=True)
        return jsonify({"error": "Failed to generate prompts"}), 500