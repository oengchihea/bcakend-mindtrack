from flask import Blueprint, request, jsonify, current_app
import uuid
import re
import requests
from datetime import datetime
import json

mood_bp = Blueprint('mood', __name__, url_prefix='/api')

# UUID validation regex
uuid_regex = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

def verify_token(token):
    """Verify Supabase JWT token and return user_id using Supabase client."""
    try:
        response = current_app.supabase.auth.get_user(token)
        if not response or not response.user:
            print(f'Token verification failed: No user data in response')
            return None
        user_id = response.user.id
        if not user_id or not uuid_regex.match(user_id):
            print(f'Invalid user_id in token response: {user_id}')
            return None
        print(f'Token verified successfully for user_id: {user_id}')
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

def convert_questionnaire_to_analyze_data_format(content, questionnaire_data):
    """Convert questionnaire data to the format expected by your /api/analyze-data endpoint."""
    
    # Extract relevant data from questionnaire
    user_data = {}
    
    # Map common questionnaire fields to your analyze-data API format
    if questionnaire_data:
        # Feeling scale (1-10)
        if 'feeling_scale' in questionnaire_data:
            user_data['feeling'] = str(questionnaire_data['feeling_scale'])
        elif 'feeling' in questionnaire_data:
            user_data['feeling'] = str(questionnaire_data['feeling'])
        elif 'mood_scale' in questionnaire_data:
            user_data['feeling'] = str(questionnaire_data['mood_scale'])
        else:
            # Try to extract a number from content or default to 5
            user_data['feeling'] = str(extract_number_from_content(content) or 5)
        
        # Mood word
        if 'mood_word' in questionnaire_data:
            user_data['moodWord'] = str(questionnaire_data['mood_word'])
        elif 'mood' in questionnaire_data:
            user_data['moodWord'] = str(questionnaire_data['mood'])
        else:
            user_data['moodWord'] = extract_mood_word_from_content(content)
        
        # Positive experience
        if 'positive_experience' in questionnaire_data:
            user_data['positiveExperience'] = str(questionnaire_data['positive_experience'])
        elif 'good_things' in questionnaire_data:
            user_data['positiveExperience'] = str(questionnaire_data['good_things'])
        else:
            user_data['positiveExperience'] = extract_positive_from_content(content)
        
        # Affecting factors (negative factors)
        if 'negative_factors' in questionnaire_data:
            user_data['affectingFactor'] = str(questionnaire_data['negative_factors'])
        elif 'affecting_factors' in questionnaire_data:
            user_data['affectingFactor'] = str(questionnaire_data['affecting_factors'])
        elif 'stress_factors' in questionnaire_data:
            user_data['affectingFactor'] = str(questionnaire_data['stress_factors'])
        else:
            user_data['affectingFactor'] = extract_challenges_from_content(content)
    else:
        # No questionnaire data, extract from content
        user_data = {
            'feeling': str(extract_number_from_content(content) or 5),
            'moodWord': extract_mood_word_from_content(content),
            'positiveExperience': extract_positive_from_content(content),
            'affectingFactor': extract_challenges_from_content(content)
        }
    
    return user_data

def extract_number_from_content(content):
    """Extract a number (1-10) from content for mood scale."""
    import re
    
    # Look for patterns like "feeling 7/10", "mood is 8", "rate it 6"
    patterns = [
        r'(?:feeling|mood|rate|score).*?(\d+)(?:/10|out of 10)?',
        r'(\d+)(?:/10|out of 10)',
        r'(\d+)\s*(?:out of|/)\s*10'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content.lower())
        if match:
            num = int(match.group(1))
            if 1 <= num <= 10:
                return num
    
    return None

def extract_mood_word_from_content(content):
    """Extract mood words from content."""
    content_lower = content.lower()
    
    mood_words = [
        'happy', 'sad', 'angry', 'anxious', 'excited', 'depressed', 'joyful',
        'frustrated', 'calm', 'stressed', 'content', 'worried', 'peaceful',
        'overwhelmed', 'grateful', 'lonely', 'confident', 'tired', 'energetic'
    ]
    
    found_words = []
    for word in mood_words:
        if word in content_lower:
            found_words.append(word)
    
    return ', '.join(found_words) if found_words else 'neutral'

def extract_positive_from_content(content):
    """Extract positive experiences from content."""
    content_lower = content.lower()
    
    positive_indicators = [
        'accomplished', 'achieved', 'success', 'good', 'great', 'wonderful',
        'amazing', 'fantastic', 'excellent', 'proud', 'grateful', 'thankful'
    ]
    
    for indicator in positive_indicators:
        if indicator in content_lower:
            # Try to extract the sentence containing the positive word
            sentences = content.split('.')
            for sentence in sentences:
                if indicator in sentence.lower():
                    return sentence.strip()
    
    return "None provided"

def extract_challenges_from_content(content):
    """Extract challenges or negative factors from content."""
    content_lower = content.lower()
    
    challenge_indicators = [
        'stress', 'problem', 'issue', 'difficult', 'hard', 'struggle',
        'challenge', 'worry', 'concern', 'trouble', 'upset', 'frustrated'
    ]
    
    for indicator in challenge_indicators:
        if indicator in content_lower:
            # Try to extract the sentence containing the challenge
            sentences = content.split('.')
            for sentence in sentences:
                if indicator in sentence.lower():
                    return sentence.strip()
    
    return "None provided"

def call_analyze_data_api(content, questionnaire_data=None, max_retries=2):
    """Call your existing /api/analyze-data endpoint with improved data mapping."""
    
    print(f'Calling analyze-data API with content: {content[:100]}...')
    print(f'Questionnaire data: {questionnaire_data}')
    
    # Convert data to the format expected by your analyze-data API
    user_data = convert_questionnaire_to_analyze_data_format(content, questionnaire_data)
    
    # Add the original content to provide more context
    user_data['originalContent'] = content
    
    for attempt in range(max_retries):
        try:
            print(f'Attempt {attempt + 1}/{max_retries} - Calling analyze-data API')
            
            payload = {
                'userData': user_data,
                'analysisType': 'comprehensive-mood',  # Changed to comprehensive for better analysis
                'includeContext': True,  # Request more contextual analysis
                'requestId': str(uuid.uuid4())  # Add request tracking
            }
            
            print(f'Sending enhanced payload: {json.dumps(payload, indent=2)}')
            
            response = requests.post(
                'https://ai-mindtrack.vercel.app/api/analyze-data',
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'MindTrack-Flask/2.0',
                    'Accept': 'application/json',
                    'X-Request-Source': 'flask-backend'
                },
                timeout=60  # Increased timeout for better analysis
            )
            
            print(f'Analyze-data API Response Status: {response.status_code}')
            print(f'Analyze-data API Response Headers: {dict(response.headers)}')
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    print(f'Analyze-data API Response: {json.dumps(result, indent=2)}')
                    
                    # Extract analysis from the response
                    if 'analysis' in result:
                        analysis = result['analysis']
                        
                        # Validate that analysis has required fields
                        required_fields = ['score', 'insights']
                        missing_fields = [field for field in required_fields if field not in analysis]
                        
                        if missing_fields:
                            print(f'Analysis missing required fields: {missing_fields}')
                            continue
                        
                        # Convert response to your expected format with enhanced processing
                        converted_analysis = convert_analyze_data_response_enhanced(analysis, user_data, content)
                        return converted_analysis
                    else:
                        print('No analysis field in response')
                        print(f'Available fields: {list(result.keys())}')
                        continue
                        
                except json.JSONDecodeError as e:
                    print(f'Failed to parse JSON response: {str(e)}')
                    print(f'Raw response: {response.text[:500]}...')
                    continue
                    
            else:
                print(f'Analyze-data API Error Response ({response.status_code}): {response.text}')
                
                # If it's a server error, try again
                if response.status_code >= 500:
                    continue
                else:
                    # Client error, don't retry
                    break
                
        except requests.exceptions.Timeout:
            print(f'Timeout calling analyze-data API (attempt {attempt + 1})')
            continue
            
        except requests.exceptions.ConnectionError as e:
            print(f'Connection error calling analyze-data API: {str(e)}')
            continue
            
        except requests.exceptions.RequestException as e:
            print(f'Request error calling analyze-data API: {str(e)}')
            continue
            
        except Exception as e:
            print(f'Unexpected error calling analyze-data API: {str(e)}')
            import traceback
            traceback.print_exc()
            continue
    
    print(f'All analyze-data API attempts failed after {max_retries} retries')
    return None

def convert_analyze_data_response_enhanced(analysis, user_data, original_content):
    """Enhanced conversion of analyze-data API response with better context understanding."""
    
    # Map emoji text to actual emojis with more options
    emoji_map = {
        'sad': '😔',
        'slightly_sad': '😕',
        'neutral': '😐',
        'slightly_happy': '🙂',
        'happy': '😊',
        'very_happy': '😄',
        'very_sad': '😢',
        'anxious': '😰',
        'calm': '😌',
        'excited': '🤗',
        'angry': '😡',
        'frustrated': '😤',
        'content': '😊',
        'peaceful': '😌'
    }
    
    # Get score and ensure it's valid
    score = analysis.get('score', 3)
    try:
        score = float(score)
        if score < 1 or score > 5:
            score = 3  # Default to neutral
    except (ValueError, TypeError):
        score = 3
    
    # Convert score (1-5) to (0-10) scale with better mapping
    normalized_score = min(10, max(0, round((score - 1) * 2.5, 1)))
    
    # Enhanced sentiment mapping
    sentiment_map = {
        1: 'very negative',
        1.5: 'very negative',
        2: 'negative', 
        2.5: 'negative',
        3: 'neutral',
        3.5: 'neutral',
        4: 'positive',
        4.5: 'positive',
        5: 'very positive'
    }
    
    # Get insights and enhance them with context
    original_insights = analysis.get('insights', 'Mood analysis completed successfully.')
    enhanced_insights = enhance_insights_with_context(original_insights, user_data, original_content)
    
    # Generate contextual suggestions
    suggestions = generate_contextual_suggestions(score, user_data, original_content, analysis)
    
    # Get emoji from analysis or map from score and content
    emoji = analysis.get('emoji', 'neutral')
    if emoji in emoji_map:
        emoji = emoji_map[emoji]
    else:
        # Enhanced emoji selection based on content and score
        emoji = select_contextual_emoji(score, original_content, user_data)
    
    # Extract themes from content and analysis
    themes = extract_themes_from_content(original_content, analysis)
    
    converted = {
        'mood': user_data.get('moodWord', 'neutral'),
        'sentiment': sentiment_map.get(score, 'neutral'),
        'score': normalized_score,
        'insights': enhanced_insights,
        'suggestions': suggestions,
        'emoji': emoji,
        'themes': themes,
        'confidence': analysis.get('confidence', 0.85),
        'apiError': False,
        'timestamp': datetime.utcnow().isoformat(),
        'source': 'analyze-data-enhanced',
        'context': {
            'originalScore': score,
            'hasQuestionnaireData': bool(user_data.get('feeling') != '5'),
            'contentLength': len(original_content),
            'moodWords': user_data.get('moodWord', 'neutral')
        }
    }
    
    print(f'Enhanced converted analysis: {json.dumps(converted, indent=2)}')
    return converted

def enhance_insights_with_context(original_insights, user_data, content):
    """Enhance insights with more context and personalization."""
    
    # If insights are too generic, make them more specific
    if len(original_insights) < 50 or 'analysis completed' in original_insights.lower():
        mood_word = user_data.get('moodWord', 'neutral')
        feeling_scale = user_data.get('feeling', '5')
        
        # Create more personalized insights
        if mood_word != 'neutral' and mood_word:
            if int(feeling_scale) >= 7:
                enhanced = f"You're experiencing {mood_word} emotions, which is wonderful to see. Your mood rating of {feeling_scale}/10 suggests you're in a positive emotional space."
            elif int(feeling_scale) <= 3:
                enhanced = f"I notice you're feeling {mood_word} with a mood rating of {feeling_scale}/10. It's important to acknowledge these difficult feelings and be gentle with yourself."
            else:
                enhanced = f"Your mood appears to be {mood_word} with a rating of {feeling_scale}/10. This suggests you're experiencing some mixed emotions, which is completely normal."
        else:
            enhanced = f"Based on your entry, your mood seems relatively balanced with a rating of {feeling_scale}/10. Continue monitoring your emotional patterns."
        
        return enhanced
    
    # If insights are good but could be shorter
    if len(original_insights) > 250:
        sentences = original_insights.split('.')
        # Take first 2 meaningful sentences
        short_insights = []
        for sentence in sentences[:3]:
            sentence = sentence.strip()
            if sentence and len(sentence) > 15:
                short_insights.append(sentence)
            if len(short_insights) == 2:
                break
        
        result = '. '.join(short_insights)
        if result and not result.endswith('.'):
            result += '.'
        return result or original_insights
    
    return original_insights

def generate_contextual_suggestions(score, user_data, content, analysis):
    """Generate more contextual and specific suggestions."""
    
    mood_word = user_data.get('moodWord', 'neutral').lower()
    feeling_scale = int(user_data.get('feeling', '5'))
    positive_exp = user_data.get('positiveExperience', '').lower()
    affecting_factor = user_data.get('affectingFactor', '').lower()
    
    suggestions = []
    
    # Base suggestions on feeling scale
    if feeling_scale >= 8:  # Very positive
        suggestions = [
            f"Continue engaging in activities that contribute to your {mood_word} mood",
            "Share your positive energy with friends or family",
            "Reflect on what specifically is working well in your life right now",
            "Consider journaling about this positive experience for future reference"
        ]
    elif feeling_scale >= 6:  # Moderately positive
        suggestions = [
            f"Build on your current {mood_word} feelings with activities you enjoy",
            "Practice gratitude for the positive aspects of your day",
            "Connect with supportive people in your life",
            "Maintain the habits that are contributing to your well-being"
        ]
    elif feeling_scale >= 4:  # Neutral
        suggestions = [
            "Consider engaging in activities that typically boost your mood",
            "Take a moment to check in with yourself and your needs",
            "Try a small act of self-care or kindness",
            "Reach out to someone you care about"
        ]
    elif feeling_scale >= 2:  # Low mood
        suggestions = [
            f"Be extra gentle with yourself while experiencing {mood_word} feelings",
            "Try a grounding technique like deep breathing or mindfulness",
            "Consider reaching out to a trusted friend or family member",
            "Engage in a small, comforting activity that usually helps"
        ]
    else:  # Very low mood
        suggestions = [
            "Please be very compassionate with yourself during this difficult time",
            "Consider speaking with a mental health professional if you haven't already",
            "Try gentle self-care activities like a warm bath or listening to calming music",
            "Remember that difficult feelings are temporary and you're not alone"
        ]
    
    # Add specific suggestions based on affecting factors
    if 'stress' in affecting_factor or 'work' in affecting_factor:
        suggestions.append("Consider stress-reduction techniques like short breaks or time management strategies")
    elif 'relationship' in affecting_factor or 'family' in affecting_factor:
        suggestions.append("Think about healthy communication strategies for your relationships")
    elif 'health' in affecting_factor or 'sleep' in affecting_factor:
        suggestions.append("Focus on basic self-care like adequate sleep, nutrition, and gentle movement")
    
    # Add suggestions based on positive experiences
    if 'exercise' in positive_exp or 'workout' in positive_exp:
        suggestions.append("Continue incorporating physical activity that you enjoy")
    elif 'friend' in positive_exp or 'social' in positive_exp:
        suggestions.append("Keep nurturing your social connections and relationships")
    
    return suggestions[:4]  # Limit to 4 suggestions

def select_contextual_emoji(score, content, user_data):
    """Select emoji based on multiple factors."""
    
    content_lower = content.lower()
    mood_word = user_data.get('moodWord', '').lower()
    
    # Specific mood word mapping
    mood_emoji_map = {
        'happy': '😊',
        'excited': '🤗',
        'joyful': '😄',
        'sad': '😔',
        'depressed': '😢',
        'anxious': '😰',
        'worried': '😟',
        'angry': '😡',
        'frustrated': '😤',
        'calm': '😌',
        'peaceful': '😌',
        'content': '🙂',
        'grateful': '😊',
        'stressed': '😰',
        'overwhelmed': '😵',
        'tired': '😴',
        'energetic': '⚡'
    }
    
    # Check for specific mood words first
    for mood, emoji in mood_emoji_map.items():
        if mood in mood_word:
            return emoji
    
    # Fall back to score-based selection
    if score >= 4.5:
        return '😄'
    elif score >= 3.5:
        return '😊'
    elif score >= 2.5:
        return '🙂'
    elif score >= 1.5:
        return '😐'
    elif score >= 1:
        return '😕'
    else:
        return '😔'

def extract_themes_from_content(content, analysis):
    """Extract emotional and situational themes from content."""
    
    content_lower = content.lower()
    themes = []
    
    # Emotional themes
    if any(word in content_lower for word in ['stress', 'pressure', 'overwhelm']):
        themes.append('stress')
    if any(word in content_lower for word in ['grateful', 'thankful', 'appreciate']):
        themes.append('gratitude')
    if any(word in content_lower for word in ['relationship', 'friend', 'family', 'partner']):
        themes.append('relationships')
    if any(word in content_lower for word in ['work', 'job', 'career', 'office']):
        themes.append('work')
    if any(word in content_lower for word in ['health', 'exercise', 'sleep', 'tired']):
        themes.append('health')
    if any(word in content_lower for word in ['goal', 'achievement', 'accomplish', 'success']):
        themes.append('achievement')
    if any(word in content_lower for word in ['worry', 'anxious', 'nervous', 'fear']):
        themes.append('anxiety')
    if any(word in content_lower for word in ['lonely', 'alone', 'isolated']):
        themes.append('loneliness')
    
    # Add themes from analysis if available
    if 'themes' in analysis and isinstance(analysis['themes'], list):
        themes.extend(analysis['themes'])
    
    return list(set(themes))  # Remove duplicates

def create_enhanced_fallback_analysis(mood, content, questionnaire_data=None):
    """Create an enhanced fallback analysis when the API fails."""
    
    content_lower = content.lower()
    
    # Enhanced sentiment analysis
    positive_words = ['happy', 'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'joy', 'love', 'excited', 'grateful', 'accomplished', 'proud']
    negative_words = ['sad', 'bad', 'terrible', 'awful', 'horrible', 'depressed', 'angry', 'frustrated', 'worried', 'anxious', 'stressed', 'overwhelmed']
    
    positive_count = sum(1 for word in positive_words if word in content_lower)
    negative_count = sum(1 for word in negative_words if word in content_lower)
    
    # Determine sentiment and score
    if positive_count > negative_count:
        sentiment = 'positive'
        score = min(7 + positive_count, 10)
        emoji = '😊'
    elif negative_count > positive_count:
        sentiment = 'negative'
        score = max(3 - negative_count, 0)
        emoji = '😕'
    else:
        sentiment = 'neutral'
        score = 5
        emoji = '😐'
    
    # Create contextual insights
    if questionnaire_data and 'feeling_scale' in questionnaire_data:
        feeling = questionnaire_data['feeling_scale']
        insights = f"Based on your mood entry and rating of {feeling}/10, you seem to be experiencing {sentiment} emotions. Your mood appears to be {mood.lower()}."
    else:
        insights = f"Your mood entry suggests you're experiencing {sentiment} emotions. Your overall mood appears to be {mood.lower()}."
    
    # Generate contextual suggestions
    user_data = convert_questionnaire_to_analyze_data_format(content, questionnaire_data)
    suggestions = generate_contextual_suggestions(score/2.5 + 1, user_data, content, {})
    
    return {
        'mood': mood,
        'sentiment': sentiment,
        'score': score,
        'insights': insights,
        'suggestions': suggestions,
        'emoji': emoji,
        'themes': extract_themes_from_content(content, {}),
        'confidence': 0.6,
        'apiError': True,
        'error': 'Analysis service temporarily unavailable - using enhanced basic analysis',
        'timestamp': datetime.utcnow().isoformat(),
        'source': 'enhanced-fallback'
    }

@mood_bp.route('/mood', methods=['POST'])
def save_mood_entry():
    # Check authorization
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        print('Missing or invalid Authorization header')
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id = verify_token(token)
    if not authenticated_user_id:
        print('Invalid access token')
        return jsonify({'error': 'Invalid access token'}), 401

    data = request.get_json()
    if not data:
        print('No JSON data provided')
        return jsonify({'error': 'No data provided'}), 400
        
    user_id = data.get('userId')
    mood = data.get('mood')
    content = data.get('content')
    questionnaire_data = data.get('questionnaireData')
    analysis = data.get('analysis')  # Pre-provided analysis from client

    # Validate inputs
    if not user_id or not uuid_regex.match(user_id):
        print(f'Invalid or missing user_id: {user_id}')
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    if authenticated_user_id != user_id:
        print(f'Unauthorized: Token user_id {authenticated_user_id} does not match requested user_id {user_id}')
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403
    if not mood or not content:
        print('Missing required fields: mood or content')
        return jsonify({'error': 'Missing required fields: mood and content are required'}), 400

    try:
        print(f'Processing mood entry for user_id: {user_id}')
        print(f'Mood: {mood}, Content: {content[:100]}...')
        print(f'Questionnaire data: {questionnaire_data}')
        
        # Use provided analysis if valid, otherwise call analyze-data API
        final_analysis = analysis
        if not final_analysis or final_analysis.get('apiError') == True:
            print('No valid pre-provided analysis, calling enhanced analyze-data API...')
            
            # Try to get analysis from analyze-data API with enhanced processing
            api_analysis = call_analyze_data_api(content, questionnaire_data)
            
            if api_analysis:
                final_analysis = api_analysis
                print('Successfully got enhanced analysis from analyze-data API')
            else:
                print('Analyze-data API analysis failed, creating enhanced fallback analysis')
                final_analysis = create_enhanced_fallback_analysis(mood, content, questionnaire_data)
        else:
            print('Using pre-provided analysis')
            # Ensure the pre-provided analysis has the right source
            final_analysis['source'] = final_analysis.get('source', 'client')

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

        print(f'Attempting to save mood entry with mood_id: {mood_id}')
        print(f'Final analysis source: {final_analysis.get("source", "unknown")}')

        # Create authenticated Supabase client
        authenticated_supabase = create_authenticated_supabase_client(token)
        
        # Insert into mood_entries table
        response = authenticated_supabase.table('mood_entries').insert(mood_entry).execute()
        
        if response.data and len(response.data) > 0:
            print(f'Mood entry saved successfully with mood_id: {mood_id}')
            return jsonify({
                'id': mood_id,
                'analysis': final_analysis,
                'success': True
            }), 201
        else:
            print(f'Failed to save mood entry - no data returned: {response}')
            return jsonify({'error': 'Failed to save mood entry - database insert failed'}), 500

    except Exception as e:
        print(f'Unexpected error saving mood entry: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error'}), 500

# Test endpoint for enhanced analyze-data API
@mood_bp.route('/mood/test-enhanced', methods=['POST'])
def test_enhanced_analysis():
    """Test the enhanced analyze-data API processing."""
    data = request.get_json() or {}
    content = data.get('content', 'I feel happy today and accomplished a lot at work')
    questionnaire_data = data.get('questionnaireData', {
        'feeling_scale': 7,
        'mood_word': 'happy',
        'positive_experience': 'completed project at work',
        'negative_factors': 'none'
    })
    
    print(f'Testing enhanced analyze-data API with content: {content}')
    print(f'Questionnaire data: {questionnaire_data}')
    
    result = call_analyze_data_api(content, questionnaire_data)
    
    if result:
        return jsonify({
            'success': True,
            'analysis': result,
            'message': 'Enhanced analysis completed successfully'
        }), 200
    else:
        fallback = create_enhanced_fallback_analysis('Happy', content, questionnaire_data)
        return jsonify({
            'success': False,
            'fallback_analysis': fallback,
            'message': 'Analyze-data API failed, enhanced fallback analysis created'
        }), 200

@mood_bp.route('/mood', methods=['GET'])
def get_mood_entries():
    # [Keep your existing GET method unchanged]
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        print('Missing or invalid Authorization header')
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id = verify_token(token)
    if not authenticated_user_id:
        print('Invalid access token')
        return jsonify({'error': 'Invalid access token'}), 401

    user_id = request.args.get('userId')
    if not user_id or not uuid_regex.match(user_id):
        print(f'Invalid or missing user_id: {user_id}')
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    if authenticated_user_id != user_id:
        print(f'Unauthorized: Token user_id {authenticated_user_id} does not match requested user_id {user_id}')
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403

    try:
        print(f'Fetching mood entries for user_id: {user_id}')
        
        authenticated_supabase = create_authenticated_supabase_client(token)

        response = authenticated_supabase.table('mood_entries')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
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
            print(f'Successfully fetched {len(entries)} mood entries for user_id: {user_id}')
            return jsonify(entries), 200
        else:
            print(f'No mood entries found for user_id: {user_id}')
            return jsonify([]), 200

    except Exception as e:
        print(f'Error fetching mood entries: {str(e)}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error'}), 500
