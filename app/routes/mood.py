from flask import Blueprint, request, jsonify, current_app
import uuid
import re
import requests
from datetime import datetime, date
import json
import time

mood_bp = Blueprint('mood', __name__, url_prefix='/api')

# UUID validation regex
uuid_regex = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

def verify_token(token):
    """Verify Supabase JWT token."""
    try:
        response = current_app.supabase.auth.get_user(token)
        if not response or not response.user:
            return None
        user_id = response.user.id
        if not user_id or not uuid_regex.match(user_id):
            return None
        return user_id
    except Exception as e:
        print(f'Token verification error: {str(e)}')
        return None

def create_authenticated_supabase_client(token):
    """Create a Supabase client with proper authentication headers."""
    from supabase import create_client
    
    client = create_client(
        current_app.supabase.supabase_url,
        current_app.supabase.supabase_key
    )
    
    client.postgrest.session.headers.update({
        'Authorization': f'Bearer {token}'
    })
    
    return client

def create_enhanced_analysis_prompt(content, questionnaire_data):
    """Create a comprehensive prompt for AI analysis with questions and answers."""
    
    prompt = f"""
Please analyze this person's mood and mental state based on their journal entry and detailed questionnaire responses.

JOURNAL ENTRY:
"{content}"

QUESTIONNAIRE RESPONSES:
"""

    if questionnaire_data and 'questionnaire_responses' in questionnaire_data:
        for response in questionnaire_data['questionnaire_responses']:
            prompt += f"""
Q: {response['question']}
A: {response['user_response']}
"""
    
    prompt += f"""

ANALYSIS INSTRUCTIONS:
1. Provide a mood score from 0-10 (where 0 is extremely negative, 5 is neutral, 10 is extremely positive)
2. Select an appropriate emoji that reflects their emotional state
3. Write personalized insights that reference specific answers from their questionnaire
4. Provide 4 actionable suggestions based on their specific situation
5. Identify key themes from their responses
6. Consider the relationship between their journal entry and questionnaire answers

IMPORTANT: Ensure the score varies based on the actual responses. Don't default to neutral (5) unless the responses truly indicate neutrality.

Please respond in this exact JSON format:
{{
    "score": [number between 0-10],
    "emoji": "[single emoji character]",
    "sentiment": "[very negative/negative/neutral/positive/very positive]",
    "insights": "[2-3 sentences of personalized insights referencing their specific answers]",
    "suggestions": [
        "[specific suggestion based on their responses]",
        "[specific suggestion based on their responses]", 
        "[specific suggestion based on their responses]",
        "[specific suggestion based on their responses]"
    ],
    "themes": ["[theme1]", "[theme2]", "[theme3]"],
    "confidence": [number between 0-1]
}}
"""
    
    return prompt

def call_enhanced_analyze_api(content, questionnaire_data=None, max_retries=2):
    """Call AI analysis API with enhanced prompt including questions and answers."""
    
    print(f'Calling enhanced analyze API with structured questionnaire data')
    
    for attempt in range(max_retries):
        try:
            # Create enhanced prompt with questions and answers
            analysis_prompt = create_enhanced_analysis_prompt(content, questionnaire_data)
            
            payload = {
                'prompt': analysis_prompt,
                'content': content,
                'questionnaire_data': questionnaire_data,
                'analysis_type': 'comprehensive_with_context',
                'include_questions': True,
                'requestId': str(uuid.uuid4())
            }
            
            print(f'Sending enhanced payload with {len(questionnaire_data.get("questionnaire_responses", []))} questionnaire responses')
            
            response = requests.post(
                'https://ai-mindtrack.vercel.app/api/analyze-data',
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'MindTrack-Enhanced/1.0',
                },
                timeout=30
            )
            
            print(f'Enhanced API Response Status: {response.status_code}')
            
            if response.status_code == 200:
                result = response.json()
                if 'analysis' in result:
                    analysis = result['analysis']
                    # Add source information
                    analysis['source'] = 'enhanced-ai-analysis'
                    analysis['questionnaire_context'] = True
                    print(f'Enhanced AI analysis: Score {analysis.get("score")}, Emoji {analysis.get("emoji")}')
                    return analysis
                    
        except Exception as e:
            print(f'Enhanced API call failed (attempt {attempt + 1}): {str(e)}')
            continue
    
    print('Enhanced API analysis failed, falling back to local analysis')
    return None

def analyze_with_enhanced_variation(content, mood, questionnaire_data=None):
    """Enhanced local analysis that ensures varied outputs based on inputs."""
    
    print(f'=== ENHANCED VARIATION ANALYSIS ===')
    print(f'Content: {content[:100]}...')
    print(f'Mood: {mood}')
    print(f'Questionnaire responses: {len(questionnaire_data.get("questionnaire_responses", []))}')
    
    # Initialize scoring system
    base_score = 5.0  # Start neutral
    score_adjustments = []
    confidence = 0.8
    themes = []
    positive_indicators = []
    areas_of_concern = []
    
    # Process questionnaire responses with detailed scoring
    if questionnaire_data and 'questionnaire_responses' in questionnaire_data:
        responses = questionnaire_data['questionnaire_responses']
        
        for response in responses:
            question_id = response['question_id']
            user_answer = str(response['user_response']).strip()
            question_text = response['question']
            
            print(f'Processing: {question_id} = "{user_answer}"')
            
            # Detailed analysis for each question type
            if question_id == 'feeling_scale':
                try:
                    feeling_score = float(user_answer)
                    # Use feeling scale as primary base score
                    base_score = feeling_score
                    score_adjustments.append(f'Base feeling scale: {feeling_score}')
                    print(f'Set base score from feeling scale: {base_score}')
                    
                    if feeling_score >= 8:
                        positive_indicators.append(f'High mood rating: {feeling_score}/10')
                    elif feeling_score <= 3:
                        areas_of_concern.append(f'Low mood rating: {feeling_score}/10')
                        
                except ValueError:
                    print(f'Could not parse feeling scale: {user_answer}')
                    
            elif question_id == 'mood_word':
                mood_word = user_answer.lower()
                
                # Comprehensive mood word analysis with scoring
                very_positive_moods = ['ecstatic', 'euphoric', 'elated', 'overjoyed', 'blissful', 'thrilled']
                positive_moods = ['happy', 'excited', 'joyful', 'content', 'grateful', 'peaceful', 'energetic', 'optimistic']
                neutral_moods = ['okay', 'fine', 'alright', 'neutral', 'calm', 'stable']
                negative_moods = ['sad', 'down', 'disappointed', 'frustrated', 'tired', 'stressed', 'worried']
                very_negative_moods = ['depressed', 'devastated', 'hopeless', 'angry', 'furious', 'anxious', 'overwhelmed']
                
                if any(vm in mood_word for vm in very_positive_moods):
                    base_score += 2.5
                    positive_indicators.append(f'Very positive mood: {user_answer}')
                    score_adjustments.append(f'Very positive mood word: +2.5')
                elif any(pm in mood_word for pm in positive_moods):
                    base_score += 1.5
                    positive_indicators.append(f'Positive mood: {user_answer}')
                    score_adjustments.append(f'Positive mood word: +1.5')
                elif any(nm in mood_word for nm in neutral_moods):
                    # No adjustment for neutral
                    score_adjustments.append(f'Neutral mood word: 0')
                elif any(neg in mood_word for neg in negative_moods):
                    base_score -= 1.5
                    areas_of_concern.append(f'Negative mood: {user_answer}')
                    score_adjustments.append(f'Negative mood word: -1.5')
                elif any(vneg in mood_word for vneg in very_negative_moods):
                    base_score -= 2.5
                    areas_of_concern.append(f'Very negative mood: {user_answer}')
                    score_adjustments.append(f'Very negative mood word: -2.5')
                    
            elif question_id == 'energy_level':
                try:
                    energy = float(user_answer)
                    if energy >= 8:
                        base_score += 1.0
                        positive_indicators.append(f'High energy level: {energy}/10')
                        score_adjustments.append(f'High energy: +1.0')
                    elif energy >= 6:
                        base_score += 0.5
                        positive_indicators.append(f'Good energy level: {energy}/10')
                        score_adjustments.append(f'Good energy: +0.5')
                    elif energy <= 3:
                        base_score -= 1.0
                        areas_of_concern.append(f'Low energy level: {energy}/10')
                        score_adjustments.append(f'Low energy: -1.0')
                    elif energy <= 5:
                        base_score -= 0.5
                        areas_of_concern.append(f'Below average energy: {energy}/10')
                        score_adjustments.append(f'Below average energy: -0.5')
                    themes.append('energy')
                except ValueError:
                    pass
                    
            elif question_id == 'sleep_quality':
                sleep_quality = user_answer.lower()
                if 'excellent' in sleep_quality:
                    base_score += 1.0
                    positive_indicators.append(f'Excellent sleep quality')
                    score_adjustments.append(f'Excellent sleep: +1.0')
                elif 'good' in sleep_quality:
                    base_score += 0.5
                    positive_indicators.append(f'Good sleep quality')
                    score_adjustments.append(f'Good sleep: +0.5')
                elif 'poor' in sleep_quality:
                    base_score -= 0.8
                    areas_of_concern.append(f'Poor sleep quality')
                    score_adjustments.append(f'Poor sleep: -0.8')
                    themes.append('sleep')
                elif 'very poor' in sleep_quality:
                    base_score -= 1.5
                    areas_of_concern.append(f'Very poor sleep quality')
                    score_adjustments.append(f'Very poor sleep: -1.5')
                    themes.append('sleep')
                    
            elif question_id == 'stress_level':
                try:
                    stress = float(user_answer)
                    if stress >= 8:
                        base_score -= 2.0
                        areas_of_concern.append(f'Very high stress level: {stress}/10')
                        score_adjustments.append(f'Very high stress: -2.0')
                        themes.append('stress')
                    elif stress >= 6:
                        base_score -= 1.0
                        areas_of_concern.append(f'High stress level: {stress}/10')
                        score_adjustments.append(f'High stress: -1.0')
                        themes.append('stress')
                    elif stress <= 3:
                        base_score += 0.5
                        positive_indicators.append(f'Low stress level: {stress}/10')
                        score_adjustments.append(f'Low stress: +0.5')
                except ValueError:
                    pass
                    
            elif question_id == 'positive_experience':
                if user_answer and len(user_answer.strip()) > 15:
                    # Analyze the content of positive experience
                    pos_content = user_answer.lower()
                    if any(word in pos_content for word in ['amazing', 'wonderful', 'fantastic', 'incredible']):
                        base_score += 1.5
                        score_adjustments.append(f'Very positive experience: +1.5')
                    elif any(word in pos_content for word in ['good', 'nice', 'pleasant', 'enjoyable']):
                        base_score += 1.0
                        score_adjustments.append(f'Positive experience: +1.0')
                    else:
                        base_score += 0.5
                        score_adjustments.append(f'Some positive experience: +0.5')
                    
                    positive_indicators.append('Identified meaningful positive experiences')
                    themes.append('gratitude')
                    
            elif question_id == 'challenging_experience':
                if user_answer and len(user_answer.strip()) > 15:
                    # Analyze the severity of challenges
                    challenge_content = user_answer.lower()
                    if any(word in challenge_content for word in ['terrible', 'awful', 'devastating', 'overwhelming']):
                        base_score -= 1.5
                        score_adjustments.append(f'Severe challenges: -1.5')
                    elif any(word in challenge_content for word in ['difficult', 'hard', 'stressful', 'frustrating']):
                        base_score -= 1.0
                        score_adjustments.append(f'Moderate challenges: -1.0')
                    else:
                        base_score -= 0.5
                        score_adjustments.append(f'Minor challenges: -0.5')
                    
                    areas_of_concern.append('Facing significant challenges')
                    themes.append('challenges')
                    
            elif question_id == 'social_interaction':
                social = user_answer.lower()
                if 'very positive' in social:
                    base_score += 1.0
                    positive_indicators.append(f'Very positive social interactions')
                    score_adjustments.append(f'Very positive social: +1.0')
                elif 'positive' in social:
                    base_score += 0.5
                    positive_indicators.append(f'Positive social interactions')
                    score_adjustments.append(f'Positive social: +0.5')
                elif 'negative' in social or 'very negative' in social:
                    base_score -= 1.0
                    areas_of_concern.append(f'Negative social interactions')
                    score_adjustments.append(f'Negative social: -1.0')
                elif 'no social interaction' in social:
                    base_score -= 0.3
                    areas_of_concern.append('Social isolation')
                    score_adjustments.append(f'Social isolation: -0.3')
                    themes.append('isolation')
                themes.append('social')
                    
            elif question_id == 'physical_activity':
                activity = user_answer.lower()
                if 'intense' in activity:
                    base_score += 1.0
                    positive_indicators.append(f'Intense physical activity')
                    score_adjustments.append(f'Intense exercise: +1.0')
                elif 'moderate' in activity:
                    base_score += 0.7
                    positive_indicators.append(f'Moderate physical activity')
                    score_adjustments.append(f'Moderate exercise: +0.7')
                elif 'light' in activity:
                    base_score += 0.3
                    positive_indicators.append(f'Light physical activity')
                    score_adjustments.append(f'Light activity: +0.3')
                elif 'no activity' in activity:
                    base_score -= 0.5
                    areas_of_concern.append('Lack of physical activity')
                    score_adjustments.append(f'No activity: -0.5')
                themes.append('exercise')
                    
            elif question_id == 'gratitude':
                if user_answer and len(user_answer.strip()) > 10:
                    base_score += 0.8
                    positive_indicators.append('Practicing gratitude')
                    score_adjustments.append(f'Gratitude practice: +0.8')
                    themes.append('gratitude')
    
    # Enhanced content analysis with weighted keywords
    content_lower = content.lower()
    
    # Weighted positive keywords
    positive_keywords = {
        'amazing': 2.0, 'incredible': 2.0, 'fantastic': 2.0, 'wonderful': 1.8,
        'excellent': 1.5, 'great': 1.2, 'good': 1.0, 'happy': 1.5, 'excited': 1.8,
        'joyful': 1.8, 'love': 1.5, 'grateful': 1.5, 'accomplished': 1.8,
        'proud': 1.5, 'successful': 1.6, 'blessed': 1.4, 'peaceful': 1.3
    }
    
    # Weighted negative keywords
    negative_keywords = {
        'terrible': -2.0, 'awful': -2.0, 'horrible': -2.0, 'devastating': -2.5,
        'bad': -1.2, 'sad': -1.5, 'depressed': -2.0, 'angry': -1.8,
        'frustrated': -1.5, 'worried': -1.3, 'anxious': -1.6, 'stressed': -1.4,
        'overwhelmed': -1.8, 'exhausted': -1.5, 'hopeless': -2.3, 'lonely': -1.6
    }
    
    # Apply content-based scoring
    content_score_adjustment = 0.0
    for word, weight in positive_keywords.items():
        if word in content_lower:
            content_score_adjustment += weight
            print(f'Found positive word "{word}" with weight {weight}')
    
    for word, weight in negative_keywords.items():
        if word in content_lower:
            content_score_adjustment += weight  # weight is already negative
            print(f'Found negative word "{word}" with weight {weight}')
    
    if content_score_adjustment != 0:
        base_score += content_score_adjustment
        score_adjustments.append(f'Content analysis: {content_score_adjustment:+.1f}')
    
    # Ensure score is within bounds
    final_score = max(0.0, min(10.0, base_score))
    
    print(f'Score calculation:')
    for adjustment in score_adjustments:
        print(f'  - {adjustment}')
    print(f'Final score: {final_score:.1f}')
    
    # Determine sentiment and emoji based on final score with more granular ranges
    if final_score >= 8.5:
        sentiment = 'very positive'
        emoji = '😄'
    elif final_score >= 7.0:
        sentiment = 'positive'
        emoji = '😊'
    elif final_score >= 6.0:
        sentiment = 'slightly positive'
        emoji = '🙂'
    elif final_score >= 4.5:
        sentiment = 'neutral'
        emoji = '😐'
    elif final_score >= 3.0:
        sentiment = 'slightly negative'
        emoji = '😕'
    elif final_score >= 1.5:
        sentiment = 'negative'
        emoji = '😔'
    else:
        sentiment = 'very negative'
        emoji = '😢'
    
    # Generate contextual insights
    insights = generate_detailed_insights(
        final_score, sentiment, mood, content, questionnaire_data, 
        positive_indicators, areas_of_concern, score_adjustments
    )
    
    # Generate contextual suggestions
    suggestions = generate_varied_suggestions(
        final_score, questionnaire_data, positive_indicators, areas_of_concern, themes
    )
    
    analysis = {
        'mood': mood,
        'sentiment': sentiment,
        'score': round(final_score, 1),
        'insights': insights,
        'suggestions': suggestions,
        'emoji': emoji,
        'themes': list(set(themes)),
        'confidence': confidence,
        'apiError': False,
        'timestamp': datetime.utcnow().isoformat(),
        'source': 'enhanced-local-analysis-with-variation',
        'questionnaire_context': True,
        'key_factors': {
            'positive_indicators': positive_indicators,
            'areas_of_concern': areas_of_concern,
            'score_adjustments': score_adjustments
        },
        'debug': {
            'base_score': base_score,
            'final_score': final_score,
            'content_adjustment': content_score_adjustment,
            'positive_count': len(positive_indicators),
            'concern_count': len(areas_of_concern)
        }
    }
    
    print(f'=== ANALYSIS COMPLETE ===')
    print(f'Final Score: {final_score:.1f}, Emoji: {emoji}, Sentiment: {sentiment}')
    print(f'Positive indicators: {len(positive_indicators)}, Concerns: {len(areas_of_concern)}')
    
    return analysis

def generate_detailed_insights(score, sentiment, mood, content, questionnaire_data, positive_indicators, areas_of_concern, score_adjustments):
    """Generate detailed insights that reference specific questionnaire responses and scoring."""
    
    insights = f"Based on your comprehensive responses, you're experiencing {sentiment} emotions with a wellness score of {score}/10. "
    
    # Reference specific positive aspects
    if positive_indicators:
        if len(positive_indicators) == 1:
            insights += f"A key positive aspect is: {positive_indicators[0]}. "
        else:
            insights += f"Key positive aspects include: {', '.join(positive_indicators[:2])}. "
    
    # Reference specific concerns
    if areas_of_concern:
        if len(areas_of_concern) == 1:
            insights += f"An area that may need attention is: {areas_of_concern[0]}. "
        else:
            insights += f"Areas that may need attention include: {', '.join(areas_of_concern[:2])}. "
    
    # Add contextual advice based on score range
    if score >= 8:
        insights += "You're in an excellent emotional space - continue the practices and activities that are contributing to your well-being."
    elif score >= 6.5:
        insights += "You're in a good emotional state with strong positive momentum. Keep building on what's working well."
    elif score >= 4.5:
        insights += "Your emotional state appears balanced, with opportunities to enhance your well-being in certain areas."
    elif score >= 3:
        insights += "You're experiencing some challenges, but there are positive elements to build upon. Be patient and gentle with yourself."
    else:
        insights += "You're going through a difficult time. It's important to prioritize self-care and consider reaching out for support."
    
    return insights

def generate_varied_suggestions(score, questionnaire_data, positive_indicators, areas_of_concern, themes):
    """Generate varied suggestions based on specific analysis results."""
    
    suggestions = []
    
    # Suggestions based on specific areas of concern
    if any('stress' in concern.lower() for concern in areas_of_concern):
        suggestions.append("Practice stress-reduction techniques like deep breathing, meditation, or progressive muscle relaxation to manage your stress levels")
    
    if any('sleep' in concern.lower() for concern in areas_of_concern):
        suggestions.append("Focus on improving sleep hygiene: maintain a consistent bedtime, limit screens before bed, and create a relaxing sleep environment")
    
    if any('energy' in concern.lower() for concern in areas_of_concern):
        suggestions.append("Boost your energy levels through gentle physical activity, proper nutrition, adequate hydration, and sufficient rest")
    
    if any('social' in concern.lower() for concern in areas_of_concern):
        suggestions.append("Reach out to trusted friends or family members for meaningful social connection and emotional support")
    
    # Suggestions based on positive indicators to maintain
    if any('exercise' in indicator.lower() or 'activity' in indicator.lower() for indicator in positive_indicators):
        suggestions.append("Continue your physical activity routine as it's making a positive contribution to your overall well-being")
    
    if any('gratitude' in indicator.lower() for indicator in positive_indicators):
        suggestions.append("Keep practicing gratitude - consider expanding your gratitude practice with a daily journal or sharing appreciation with others")
    
    if any('positive' in indicator.lower() and 'mood' in indicator.lower() for indicator in positive_indicators):
        suggestions.append("Build on your positive mood by engaging in more activities that bring you joy and fulfillment")
    
    # Fill remaining suggestions based on score ranges
    while len(suggestions) < 4:
        if score >= 8:
            remaining = [
                "Share your positive energy and enthusiasm with others who might benefit from your optimism",
                "Take time to reflect on and appreciate the specific factors contributing to your excellent mood",
                "Consider setting new positive goals or challenges to maintain this upward momentum",
                "Practice mindfulness to fully experience and remember these wonderful feelings"
            ]
        elif score >= 6.5:
            remaining = [
                "Continue building on this positive foundation with activities that align with your values",
                "Practice gratitude for the good things happening in your life right now",
                "Strengthen your support network by connecting with people who uplift and inspire you",
                "Maintain the healthy habits and routines that are contributing to your well-being"
            ]
        elif score >= 4.5:
            remaining = [
                "Engage in activities that typically boost your mood and bring you a sense of accomplishment",
                "Take dedicated time for self-reflection and gentle self-care practices",
                "Reach out to someone you trust for meaningful conversation and emotional connection",
                "Try incorporating small positive activities or rituals into your daily routine"
            ]
        elif score >= 3:
            remaining = [
                "Be extra gentle and compassionate with yourself as you navigate these challenges",
                "Practice grounding techniques like deep breathing, mindfulness, or gentle movement",
                "Consider reaching out to a trusted friend, family member, or mental health professional",
                "Focus on small, manageable self-care activities that provide comfort and stability"
            ]
        else:
            remaining = [
                "Prioritize your mental health and well-being above all else during this difficult time",
                "Strongly consider speaking with a mental health professional for additional support and guidance",
                "Engage in very gentle self-care activities like warm baths, calming music, or light reading",
                "Remember that these intense feelings are temporary, and reaching out for help is a sign of strength"
            ]
        
        for suggestion in remaining:
            if suggestion not in suggestions and len(suggestions) < 4:
                suggestions.append(suggestion)
    
    return suggestions[:4]

@mood_bp.route('/mood', methods=['POST'])
def save_mood_entry():
    start_time = time.time()
    
    # Check authorization
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id = verify_token(token)
    if not authenticated_user_id:
        return jsonify({'error': 'Invalid access token'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    user_id = data.get('userId')
    mood = data.get('mood')
    content = data.get('content')
    questionnaire_data = data.get('questionnaireData')

    # Validate inputs
    if not user_id or not uuid_regex.match(user_id):
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    if authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403
    if not mood or not content:
        return jsonify({'error': 'Missing required fields: mood and content are required'}), 400

    try:
        print(f'=== PROCESSING ENHANCED MOOD ENTRY ===')
        print(f'User ID: {user_id}')
        print(f'Mood: {mood}')
        print(f'Content length: {len(content)}')
        print(f'Questionnaire responses: {len(questionnaire_data.get("questionnaire_responses", []))}')
        
        # Create authenticated Supabase client
        authenticated_supabase = create_authenticated_supabase_client(token)
        
        # Check daily limit
        today = date.today().isoformat()
        existing_check = authenticated_supabase.table('mood_entries')\
            .select('mood_id, analysis')\
            .eq('user_id', user_id)\
            .gte('created_at', today)\
            .lt('created_at', f'{today}T23:59:59')\
            .limit(1)\
            .execute()
        
        if existing_check.data and len(existing_check.data) > 0:
            existing_entry = existing_check.data[0]
            return jsonify({
                'redirectToHome': True,
                'message': 'You have already created a mood entry for today.',
                'analysis': existing_entry.get('analysis', {}),
                'existingEntry': True
            }), 200
        
        # Try enhanced AI analysis first
        print('Attempting enhanced AI analysis with questionnaire context...')
        api_analysis = call_enhanced_analyze_api(content, questionnaire_data)
        
        if api_analysis and api_analysis.get('score') != 5.0:  # Avoid default neutral scores
            print(f'Using enhanced AI analysis with score: {api_analysis.get("score")}')
            final_analysis = api_analysis
        else:
            print('Using enhanced local analysis with variation')
            final_analysis = analyze_with_enhanced_variation(content, mood, questionnaire_data)

        # Generate mood_id
        mood_id = str(uuid.uuid4())

        # Prepare mood entry data
        mood_entry = {
            'mood_id': mood_id,
            'mood': mood,
            'content': content,
            'analysis': final_analysis,
            'questionnaire_data': questionnaire_data,
            'user_id': user_id,
            'created_at': datetime.utcnow().isoformat()
        }

        print(f'Saving mood entry with analysis:')
        print(f'  Score: {final_analysis.get("score")}')
        print(f'  Emoji: {final_analysis.get("emoji")}')
        print(f'  Sentiment: {final_analysis.get("sentiment")}')
        print(f'  Source: {final_analysis.get("source")}')

        # Insert into mood_entries table
        response = authenticated_supabase.table('mood_entries').insert(mood_entry).execute()
        
        processing_time = time.time() - start_time
        print(f'Total processing time: {processing_time:.2f}s')
        
        if response.data and len(response.data) > 0:
            print(f'Enhanced mood entry saved successfully with mood_id: {mood_id}')
            return jsonify({
                'id': mood_id,
                'analysis': final_analysis,
                'success': True,
                'processingTime': round(processing_time, 2),
                'enhanced': True,
                'varied': True
            }), 201
        else:
            return jsonify({'error': 'Failed to save mood entry'}), 500

    except Exception as e:
        processing_time = time.time() - start_time
        print(f'Error saving enhanced mood entry (after {processing_time:.2f}s): {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error'}), 500

@mood_bp.route('/mood', methods=['GET'])
def get_mood_entries():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id = verify_token(token)
    if not authenticated_user_id:
        return jsonify({'error': 'Invalid access token'}), 401

    user_id = request.args.get('userId')
    if not user_id or not uuid_regex.match(user_id):
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    if authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403

    try:
        authenticated_supabase = create_authenticated_supabase_client(token)

        response = authenticated_supabase.table('mood_entries')\
            .select('mood_id, user_id, content, mood, created_at, analysis, questionnaire_data')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
        
        if response.data is not None:
            entries = [
                {
                    'id': entry['mood_id'],
                    'userId': entry['user_id'],
                    'content': entry['content'],
                    'mood': entry['mood'],
                    'date': entry['created_at'],
                    'analysis': entry['analysis'],
                    'questionnaireData': entry['questionnaire_data']
                }
                for entry in response.data
            ]
            return jsonify(entries), 200
        else:
            return jsonify([]), 200

    except Exception as e:
        print(f'Error fetching mood entries: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@mood_bp.route('/mood/test-variation', methods=['POST'])
def test_analysis_variation():
    """Test endpoint to verify analysis variation with different inputs."""
    
    data = request.get_json() or {}
    
    test_cases = [
        {
            'content': 'I feel amazing today! Got a promotion at work and celebrated with friends. Everything is going perfectly.',
            'mood': 'ecstatic',
            'questionnaire_data': {
                'questionnaire_responses': [
                    {'question_id': 'feeling_scale', 'question': 'How are you feeling?', 'user_response': '9'},
                    {'question_id': 'mood_word', 'question': 'Describe your mood', 'user_response': 'ecstatic'},
                    {'question_id': 'energy_level', 'question': 'Energy level?', 'user_response': '9'},
                    {'question_id': 'positive_experience', 'question': 'Positive experience?', 'user_response': 'Got promoted and celebrated with friends'}
                ]
            }
        },
        {
            'content': 'Having a terrible day. Everything is going wrong and I feel overwhelmed.',
            'mood': 'awful',
            'questionnaire_data': {
                'questionnaire_responses': [
                    {'question_id': 'feeling_scale', 'question': 'How are you feeling?', 'user_response': '2'},
                    {'question_id': 'mood_word', 'question': 'Describe your mood', 'user_response': 'awful'},
                    {'question_id': 'stress_level', 'question': 'Stress level?', 'user_response': '9'},
                    {'question_id': 'challenging_experience', 'question': 'Challenges?', 'user_response': 'Everything going wrong, feeling overwhelmed'}
                ]
            }
        },
        {
            'content': 'Just an ordinary day. Nothing special happened.',
            'mood': 'neutral',
            'questionnaire_data': {
                'questionnaire_responses': [
                    {'question_id': 'feeling_scale', 'question': 'How are you feeling?', 'user_response': '5'},
                    {'question_id': 'mood_word', 'question': 'Describe your mood', 'user_response': 'neutral'}
                ]
            }
        }
    ]
    
    results = []
    for i, test_case in enumerate(test_cases):
        print(f'\n=== TESTING CASE {i+1} ===')
        analysis = analyze_with_enhanced_variation(
            test_case['content'], 
            test_case['mood'], 
            test_case['questionnaire_data']
        )
        
        results.append({
            'test_case': i + 1,
            'input': {
                'content': test_case['content'][:50] + '...',
                'mood': test_case['mood'],
                'feeling_scale': test_case['questionnaire_data']['questionnaire_responses'][0]['user_response']
            },
            'output': {
                'score': analysis['score'],
                'emoji': analysis['emoji'],
                'sentiment': analysis['sentiment'],
                'source': analysis['source']
            }
        })
    
    return jsonify({
        'message': 'Analysis variation test completed',
        'results': results,
        'variation_confirmed': len(set(r['output']['score'] for r in results)) > 1
    }), 200
