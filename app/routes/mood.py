from flask import Blueprint, request, jsonify, current_app
import uuid
import re
import requests
from datetime import datetime, date, timedelta
import json
import time
from typing import Dict, Any, Optional, List
import os

mood_bp = Blueprint('mood', __name__, url_prefix='/api')

# UUID validation regex
uuid_regex = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

def _validate_user_id(user_id):
    """Validate user ID - allow test IDs during development"""
    if not user_id or user_id.strip() == '':
        raise ValueError("User ID cannot be empty")
    
    # Allow test user IDs during development
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id in test_user_ids:
        print(f'⚠️ Using test user ID: {user_id}')
        return True
    
    # Validate UUID format for production
    if not uuid_regex.match(user_id):
        print(f'❌ Invalid UUID format for user_id: "{user_id}"')
        raise ValueError(f'Invalid userId format: {user_id}')
    
    return True

class MoodAnalyzer:
    """Enhanced mood analysis class with Gemini AI-first approach"""
    
    def __init__(self):
        # UPDATED: Use the correct base URL and endpoint
        self.ai_base_url = "https://ai-mindtrack.vercel.app"
        self.ai_api_url = f"{self.ai_base_url}/api/analyze-data"
        self.ai_api_key = os.getenv('AI_SERVICE_API_KEY', '')
        self.max_retries = 3
        self.timeout = 45
        self.use_ai_first = True
    
    def analyze_mood(self, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """ENHANCED: Gemini AI-first analysis method"""
        print(f'🧠 Starting GEMINI AI mood analysis for content length: {len(content)}')
        
        # Try Gemini AI analysis with multiple attempts
        for attempt in range(self.max_retries):
            print(f'🤖 Gemini AI Analysis attempt {attempt + 1}/{self.max_retries}')
            ai_result = self._call_gemini_ai_api(content, questionnaire_data)
            
            if ai_result and self._is_valid_analysis(ai_result):
                print(f'✅ Gemini AI analysis successful on attempt {attempt + 1} with score: {ai_result.get("score")}')
                ai_result['source'] = 'gemini-ai-api'
                ai_result['attempt'] = attempt + 1
                return ai_result
            
            if attempt < self.max_retries - 1:
                print(f'⚠️ Gemini AI attempt {attempt + 1} failed, retrying...')
                time.sleep(2 ** attempt)  # Exponential backoff
        
        # Fallback to local analysis if Gemini AI fails
        print('❌ Gemini AI analysis failed after all attempts, using enhanced local analysis as last resort')
        local_result = self._create_local_analysis(content, questionnaire_data)
        local_result['ai_failed'] = True
        local_result['ai_attempts'] = self.max_retries
        return local_result
    
    def _call_gemini_ai_api(self, content: str, questionnaire_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Call Gemini AI analyze-data API with correct format"""
        try:
            # Extract questionnaire responses for the API format
            mood_scale = self._extract_mood_scale(questionnaire_data)
            mood_word = self._extract_mood_word(questionnaire_data)
            positive_experience = self._extract_positive_experience(questionnaire_data)
            affecting_factor = self._extract_concerns(questionnaire_data)
        
            # Create userData object matching the API specification
            user_data = {
                "feeling": str(mood_scale),  # 1-10 scale as string
                "moodWord": mood_word or "neutral",
                "positiveExperience": positive_experience or "",
                "affectingFactor": affecting_factor or "",
                "responseStyle": "Use 'you' language - speak directly to the user in second person"
            }
        
            # Create payload matching the API specification
            payload = {
                "userData": user_data,
                "analysisType": "immediate-mood"
            }
        
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'MindTrack-Enhanced/2.0',
                'Accept': 'application/json'
            }
        
            # Add API key if available
            if self.ai_api_key:
                headers['Authorization'] = f'Bearer {self.ai_api_key}'
                headers['X-API-Key'] = self.ai_api_key
        
            print(f'🌐 Calling Gemini AI API: {self.ai_api_url}')
            print(f'📊 Payload: feeling={mood_scale}, moodWord={mood_word}, analysisType=immediate-mood')
        
            response = requests.post(
                self.ai_api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=True
            )
        
            print(f'📊 Gemini AI Response: {response.status_code}')
        
            if response.status_code == 200:
                result = response.json()
                print(f'✅ Gemini AI success: {list(result.keys())}')
            
                # Transform Gemini AI response to our format
                transformed_result = self._transform_gemini_response(result)
                return transformed_result
            else:
                print(f'❌ Gemini AI error {response.status_code}: {response.text}')
                return None
            
        except requests.exceptions.Timeout:
            print(f'⏰ Gemini AI timeout after {self.timeout}s')
            return None
        except requests.exceptions.ConnectionError:
            print('🌐 Gemini AI connection error')
            return None
        except Exception as e:
            print(f'❌ Gemini AI exception: {str(e)}')
            return None
    
    def _create_comprehensive_prompt(self, content: str, mood_scale: int, mood_word: str, 
                                   positive_experience: str, concerns: str) -> str:
        """Create comprehensive prompt for Gemini AI analysis"""
        prompt = f"""
You are an empathetic AI mood analyzer. Analyze this mood journal entry and provide a structured JSON response.

JOURNAL ENTRY:
{content}

MOOD SELF-RATING: {mood_scale}/10
MOOD WORD: {mood_word or 'Not specified'}
POSITIVE EXPERIENCE: {positive_experience or 'Not specified'}
CONCERNS/CHALLENGES: {concerns or 'Not specified'}

Respond with ONLY a JSON object in this exact format:
{{
    "score": [float between 0-10],
    "emoji": "[single emoji representing mood]",
    "sentiment": "[very negative/negative/slightly negative/neutral/slightly positive/positive/very positive]",
    "insights": "[2-3 sentences of personalized insights]",
    "suggestions": ["suggestion1", "suggestion2", "suggestion3", "suggestion4"],
    "themes": ["theme1", "theme2", "theme3"],
    "confidence": [float between 0-1],
    "mood_category": "[primary mood category]",
    "intensity": "[low/medium/high]"
}}

Be empathetic, supportive, and provide actionable suggestions.
"""
        return prompt
    
    def _extract_mood_scale(self, questionnaire_data: Dict[str, Any]) -> int:
        """Extract mood scale (1-10) from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return 5
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] == 'feeling_scale':
                try:
                    scale = int(float(response['user_response']))
                    return max(1, min(10, scale))  # Ensure 1-10 range
                except (ValueError, TypeError):
                    pass
        
        return 5  # Default neutral
    
    def _extract_mood_word(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract mood word from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] == 'mood_word':
                return str(response['user_response']).strip()
        
        return ""
    
    def _extract_positive_experience(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract positive experience from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] in ['positive_experience', 'gratitude']:
                return str(response['user_response']).strip()
        
        return ""
    
    def _extract_concerns(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract concerns/challenges from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        concerns_list = []
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] in ['challenging_experience', 'stress_level', 'concerns']:
                concerns_list.append(str(response['user_response']).strip())
        
        return "; ".join(concerns_list) if concerns_list else ""
    
    def _transform_gemini_response(self, gemini_result: Dict[str, Any]) -> Dict[str, Any]:
        """Transform Gemini AI response to our standard format"""
        try:
            # The API returns { analysis: { score, emoji, insights } }
            if 'analysis' in gemini_result:
                analysis_data = gemini_result['analysis']
            else:
                analysis_data = gemini_result
        
            # Extract fields from the API response
            score = analysis_data.get('score', 3)  # API returns 1-5 scale
            emoji_text = analysis_data.get('emoji', 'neutral')
            insights = analysis_data.get('insights', '')
        
            # Convert 1-5 scale to 0-10 scale for our system
            converted_score = ((score - 1) / 4) * 10  # Convert 1-5 to 0-10
            converted_score = max(0.0, min(10.0, converted_score))
        
            # Convert emoji text to actual emoji
            emoji_map = {
                'sad': '😢',
                'slightly_sad': '😔',
                'neutral': '😐',
                'slightly_happy': '🙂',
                'happy': '😊'
            }
            emoji = emoji_map.get(emoji_text, '😐')
        
            # Generate sentiment from converted score
            sentiment = self._get_sentiment_from_score(converted_score)
        
            # Generate additional fields that our system expects
            suggestions = self._generate_suggestions(converted_score, {})
            themes = ['mood_analysis']  # Default theme
        
            # Ensure insights is meaningful and in second person
            if not insights or len(insights.strip()) < 20:
                insights = self._generate_insights(converted_score, '', {})
            else:
                # Convert third person to second person
                insights = self._convert_to_second_person(insights)
        
            transformed = {
                'score': round(converted_score, 1),
                'emoji': emoji,
                'sentiment': sentiment,
                'insights': insights,
                'suggestions': suggestions[:4],  # Limit to 4 suggestions
                'themes': themes,
                'confidence': 0.95,  # High confidence since it's from Gemini
                'mood_category': self._get_mood_category_from_score(converted_score),
                'intensity': self._get_intensity_from_score(converted_score),
                'source': 'gemini-ai-api',
                'timestamp': datetime.utcnow().isoformat(),
                'original_response': gemini_result,
                'api_score': score,  # Keep original 1-5 score for reference
                'api_emoji': emoji_text  # Keep original emoji text
            }
        
            print(f'✅ Transformed Gemini response: API Score {score} -> Our Score {converted_score}, Sentiment {sentiment}')
            return transformed
        
        except Exception as e:
            print(f'❌ Error transforming Gemini response: {e}')
            print(f'❌ Original response: {gemini_result}')
            return None
    
    def _is_valid_analysis(self, analysis: Dict[str, Any]) -> bool:
        """Validate analysis response"""
        if not analysis:
            return False
        
        required_fields = ['score', 'sentiment', 'insights']
        
        # Check required fields exist
        if not all(field in analysis for field in required_fields):
            missing = [f for f in required_fields if f not in analysis]
            print(f'❌ Analysis missing fields: {missing}')
            return False
        
        # Validate score
        try:
            score = float(analysis['score'])
            if not 0 <= score <= 10:
                print(f'❌ Invalid score: {score}')
                return False
        except (ValueError, TypeError):
            print(f'❌ Score not numeric: {analysis["score"]}')
            return False
        
        # Validate insights
        insights = analysis['insights']
        if not isinstance(insights, str) or len(insights.strip()) < 10:
            print(f'❌ Invalid insights: {insights}')
            return False
        
        print('✅ Analysis validation passed')
        return True
    
    def _create_local_analysis(self, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced local analysis as fallback"""
        print('🔧 Creating FALLBACK local analysis (Gemini AI unavailable)')
        
        # Extract base score from questionnaire
        base_score = self._extract_base_score(questionnaire_data)
        
        # Analyze content sentiment
        content_adjustment = self._analyze_content_sentiment(content)
        
        # Apply questionnaire adjustments
        questionnaire_adjustment = self._analyze_questionnaire_responses(questionnaire_data)
        
        # Calculate final score
        final_score = max(0.0, min(10.0, base_score + content_adjustment + questionnaire_adjustment))
        
        # Generate analysis components
        sentiment = self._get_sentiment_from_score(final_score)
        emoji = self._get_emoji_from_score(final_score)
        insights = self._generate_insights(final_score, content, questionnaire_data)
        suggestions = self._generate_suggestions(final_score, questionnaire_data)
        themes = self._extract_themes(content, questionnaire_data)
        
        analysis = {
            'score': round(final_score, 1),
            'emoji': emoji,
            'sentiment': sentiment,
            'insights': insights,
            'suggestions': suggestions,
            'themes': themes,
            'confidence': 0.7,
            'mood_category': self._get_mood_category_from_score(final_score),
            'intensity': self._get_intensity_from_score(final_score),
            'source': 'enhanced-local-analysis',
            'timestamp': datetime.utcnow().isoformat(),
            'fallback_reason': 'Gemini AI analysis unavailable'
        }
        
        print(f'✅ Fallback local analysis complete: Score {final_score}, Sentiment {sentiment}')
        return analysis
    
    def _extract_base_score(self, questionnaire_data: Dict[str, Any]) -> float:
        """Extract base score from questionnaire responses"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return 5.0
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] == 'feeling_scale':
                try:
                    return float(response['user_response'])
                except (ValueError, TypeError):
                    pass
        
        return 5.0
    
    def _analyze_content_sentiment(self, content: str) -> float:
        """Analyze content for sentiment keywords"""
        content_lower = content.lower()
        
        positive_words = {
            'amazing': 2.0, 'excellent': 1.8, 'fantastic': 2.0, 'wonderful': 1.8,
            'great': 1.5, 'good': 1.0, 'happy': 1.5, 'excited': 1.8, 'joyful': 1.8,
            'love': 1.5, 'grateful': 1.5, 'accomplished': 1.8, 'proud': 1.5
        }
        
        negative_words = {
            'terrible': -2.0, 'awful': -2.0, 'horrible': -2.0, 'devastating': -2.5,
            'bad': -1.2, 'sad': -1.5, 'depressed': -2.0, 'angry': -1.8,
            'frustrated': -1.5, 'worried': -1.3, 'anxious': -1.6, 'stressed': -1.4,
            'overwhelmed': -1.8, 'exhausted': -1.5, 'hopeless': -2.3
        }
        
        adjustment = 0.0
        for word, weight in positive_words.items():
            if word in content_lower:
                adjustment += weight
        
        for word, weight in negative_words.items():
            if word in content_lower:
                adjustment += weight
        
        return max(-3.0, min(3.0, adjustment))
    
    def _analyze_questionnaire_responses(self, questionnaire_data: Dict[str, Any]) -> float:
        """Analyze questionnaire responses for additional scoring"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return 0.0
        
        adjustment = 0.0
        
        for response in questionnaire_data['questionnaire_responses']:
            question_id = response['question_id']
            user_answer = str(response['user_response']).lower()
            
            if question_id == 'stress_level':
                try:
                    stress = float(response['user_response'])
                    adjustment -= (stress - 5) * 0.3
                except (ValueError, TypeError):
                    pass
            
            elif question_id == 'energy_level':
                try:
                    energy = float(response['user_response'])
                    adjustment += (energy - 5) * 0.2
                except (ValueError, TypeError):
                    pass
            
            elif question_id == 'sleep_quality':
                if 'excellent' in user_answer:
                    adjustment += 1.0
                elif 'good' in user_answer:
                    adjustment += 0.5
                elif 'poor' in user_answer:
                    adjustment -= 0.8
        
        return max(-2.0, min(2.0, adjustment))
    
    def _get_sentiment_from_score(self, score: float) -> str:
        """Get sentiment label from score"""
        if score >= 8.5:
            return 'very positive'
        elif score >= 7.0:
            return 'positive'
        elif score >= 6.0:
            return 'slightly positive'
        elif score >= 4.5:
            return 'neutral'
        elif score >= 3.0:
            return 'slightly negative'
        elif score >= 1.5:
            return 'negative'
        else:
            return 'very negative'
    
    def _get_emoji_from_score(self, score: float) -> str:
        """Get emoji from score"""
        if score >= 9.0:
            return '😄'
        elif score >= 7.5:
            return '😊'
        elif score >= 6.0:
            return '🙂'
        elif score >= 4.5:
            return '😐'
        elif score >= 3.0:
            return '😕'
        elif score >= 1.5:
            return '😔'
        else:
            return '😢'
    
    def _get_mood_category_from_score(self, score: float) -> str:
        """Get mood category from score"""
        if score >= 8.5:
            return 'joyful'
        elif score >= 7.0:
            return 'happy'
        elif score >= 6.0:
            return 'content'
        elif score >= 4.5:
            return 'neutral'
        elif score >= 3.0:
            return 'sad'
        elif score >= 1.5:
            return 'distressed'
        else:
            return 'very distressed'
    
    def _get_intensity_from_score(self, score: float) -> str:
        """Get emotional intensity from score"""
        if score >= 8.5 or score <= 1.5:
            return 'high'
        elif score >= 6.5 or score <= 3.5:
            return 'medium'
        else:
            return 'low'
    
    def _generate_insights(self, score: float, content: str, questionnaire_data: Dict[str, Any]) -> str:
        """Generate personalized insights"""
        insights = f"Based on your responses, you're experiencing {self._get_sentiment_from_score(score)} emotions with a wellness score of {score}/10. "
        
        if score >= 8:
            insights += "You're in an excellent emotional space - continue the practices that are contributing to your well-being."
        elif score >= 6:
            insights += "You're in a good emotional state with positive momentum. Keep building on what's working well."
        elif score >= 4:
            insights += "Your emotional state appears balanced with opportunities to enhance your well-being."
        else:
            insights += "You're experiencing some challenges. Be patient and gentle with yourself during this time."
        
        return insights
    
    def _generate_suggestions(self, score: float, questionnaire_data: Dict[str, Any]) -> List[str]:
        """Generate score-appropriate suggestions"""
        if score >= 8:
            return [
                "Continue the activities that are making you feel so positive",
                "Share your positive energy with others around you",
                "Take time to appreciate and celebrate this wonderful feeling",
                "Consider what specifically contributed to this great mood"
            ]
        elif score >= 6:
            return [
                "Build on this positive momentum with activities you enjoy",
                "Practice gratitude for the good things in your life",
                "Connect with supportive people who lift your spirits",
                "Maintain the habits contributing to your well-being"
            ]
        elif score >= 4:
            return [
                "Engage in activities that typically boost your mood",
                "Take time for self-reflection and gentle self-care",
                "Reach out to someone you trust for connection",
                "Try incorporating small positive activities into your day"
            ]
        else:
            return [
                "Be extra gentle and compassionate with yourself",
                "Practice grounding techniques like deep breathing",
                "Consider reaching out to a trusted friend or counselor",
                "Engage in small, comforting activities that help you"
            ]
    
    def _extract_themes(self, content: str, questionnaire_data: Dict[str, Any]) -> List[str]:
        """Extract themes from content and questionnaire"""
        themes = []
        content_lower = content.lower()
        
        theme_keywords = {
            'stress': ['stress', 'pressure', 'overwhelm'],
            'gratitude': ['grateful', 'thankful', 'appreciate'],
            'relationships': ['friend', 'family', 'partner'],
            'work': ['work', 'job', 'career'],
            'health': ['health', 'exercise', 'sleep'],
            'achievement': ['goal', 'accomplish', 'success']
        }
        
        for theme, keywords in theme_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                themes.append(theme)
        
        return themes[:3]

    def _convert_to_second_person(self, insights: str) -> str:
        """Convert third person insights to second person"""
        if not insights:
            return insights
        
        # Common third person to second person conversions
        conversions = [
            ("The user reports", "You reported"),
            ("The user describes", "You described"),
            ("The user's", "Your"),
            ("the user", "you"),
            ("The user", "You"),
            ("their mood", "your mood"),
            ("their", "your"),
            ("They", "You"),
            ("they", "you"),
            ("This user", "You"),
            ("this user", "you"),
            ("The individual", "You"),
            ("the individual", "you"),
            ("The person", "You"),
            ("the person", "you")
        ]
        
        converted_insights = insights
        for old_phrase, new_phrase in conversions:
            converted_insights = converted_insights.replace(old_phrase, new_phrase)
        
        return converted_insights

class MoodService:
    """Enhanced mood service with strict daily limit checking"""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.analyzer = MoodAnalyzer()
    
    def check_daily_mood_exists(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Strict daily mood checking"""
        today = date.today().isoformat()
        
        try:
            print(f'🔍 Checking daily mood for user {user_id} on {today}')
            
            response = self.supabase.table('mood_entries')\
                .select('mood_id, analysis, created_at, mood, content')\
                .eq('user_id', user_id)\
                .gte('created_at', f'{today}T00:00:00')\
                .lt('created_at', f'{today}T23:59:59')\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                entry = response.data[0]
                print(f'✅ Found existing mood entry: {entry["mood_id"]} at {entry["created_at"]}')
                return entry
            
            print(f'✅ No mood entry found for today')
            return None
            
        except Exception as e:
            print(f'❌ Error checking daily mood: {e}')
            return None
    
    def save_mood_entry(self, user_id: str, mood: str, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save new mood entry with Gemini AI analysis"""
        try:
            print(f'💾 Starting mood entry save for user: {user_id}')
            
            # Generate analysis with Gemini AI
            print('🧠 Starting Gemini AI mood analysis...')
            analysis_start = time.time()
            analysis = self.analyzer.analyze_mood(content, questionnaire_data)
            analysis_time = time.time() - analysis_start
            print(f'✅ Analysis completed in {analysis_time:.2f}s')
            
            # Create mood entry
            mood_entry = {
                'mood_id': str(uuid.uuid4()),
                'user_id': user_id,
                'mood': mood,
                'content': content,
                'analysis': analysis,
                'questionnaire_data': questionnaire_data,
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Save to database
            print('💾 Saving mood entry to database...')
            response = self.supabase.table('mood_entries').insert(mood_entry).execute()
            
            if response.data and len(response.data) > 0:
                print(f'✅ Mood entry saved successfully: {mood_entry["mood_id"]}')
                return {
                    'id': mood_entry['mood_id'],
                    'analysis': analysis,
                    'success': True,
                    'processing_time': round(analysis_time, 2)
                }
            else:
                raise Exception('Failed to save mood entry to database')
                
        except Exception as e:
            print(f'❌ Error saving mood entry: {e}')
            raise e
    
    def get_recent_mood_entries(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get user's recent mood entries"""
        try:
            response = self.supabase.table('mood_entries')\
                .select('mood_id, mood, content, analysis, created_at')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            return response.data or []
        except Exception as e:
            print(f'❌ Error fetching mood entries: {str(e)}')
            return []

def verify_token(token):
    """Verify Supabase JWT token"""
    try:
        response = current_app.supabase.auth.get_user(token)
        if not response or not response.user:
            return None
        user_id = response.user.id
        if not user_id:
            return None
        
        # Allow test user IDs
        test_user_ids = ['user123', 'test-user', 'demo-user']
        if user_id in test_user_ids:
            return user_id
            
        if not uuid_regex.match(user_id):
            return None
        return user_id
    except Exception as e:
        print(f'❌ Token verification error: {str(e)}')
        return None

def create_authenticated_supabase_client(token):
    """Create authenticated Supabase client"""
    from supabase import create_client
    
    client = create_client(
        current_app.supabase.supabase_url,
        current_app.supabase.supabase_key
    )
    
    client.postgrest.session.headers.update({
        'Authorization': f'Bearer {token}'
    })
    
    return client

@mood_bp.route('/mood/check-today', methods=['GET'])
def check_today_mood():
    """Check if user has submitted mood today with strict enforcement"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id = verify_token(token)
    if not authenticated_user_id:
        return jsonify({'error': 'Invalid access token'}), 401
    
    user_id = request.args.get('userId')
    if not user_id:
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    
    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Skip user ID mismatch check for test users
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403
    
    try:
        authenticated_supabase = create_authenticated_supabase_client(token)
        mood_service = MoodService(authenticated_supabase)
        
        existing_entry = mood_service.check_daily_mood_exists(user_id)
        
        if existing_entry:
            print(f'🔄 User {user_id} already has mood entry for today - should redirect to home')
            return jsonify({
                'hasEntry': True,
                'shouldRedirect': True,
                'message': 'You have already submitted your mood for today. Come back tomorrow!',
                'analysis': existing_entry.get('analysis', {}),
                'entryId': existing_entry['mood_id'],
                'submittedAt': existing_entry['created_at'],
                'redirectTo': '/home'
            }), 200
        else:
            print(f'✅ User {user_id} can submit mood entry for today')
            return jsonify({
                'hasEntry': False,
                'shouldRedirect': False,
                'message': 'Ready to submit today\'s mood entry',
                'canSubmit': True
            }), 200
            
    except Exception as e:
        print(f'❌ Error checking today mood: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@mood_bp.route('/mood', methods=['POST'])
def save_mood_entry():
    """Save new mood entry with strict daily limit and Gemini AI analysis"""
    start_time = time.time()
    
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
    questionnaire_data = data.get('questionnaireData', {})

    # Validate inputs
    if not user_id:
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    
    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Skip user ID mismatch check for test users
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403
    
    if not mood or not content:
        return jsonify({'error': 'Missing required fields: mood and content'}), 400

    try:
        print(f'💾 Processing mood entry for user: {user_id}')
        
        authenticated_supabase = create_authenticated_supabase_client(token)
        mood_service = MoodService(authenticated_supabase)
        
        # Strict daily limit check FIRST
        print('🔍 Checking daily limit enforcement...')
        existing_entry = mood_service.check_daily_mood_exists(user_id)
        if existing_entry:
            print(f'🚫 DAILY LIMIT REACHED - User {user_id} already submitted mood today')
            return jsonify({
                'redirectToHome': True,
                'message': 'You have already created a mood entry for today. Come back tomorrow!',
                'analysis': existing_entry.get('analysis', {}),
                'existingEntry': True,
                'submittedAt': existing_entry['created_at'],
                'dailyLimitReached': True,
                'nextSubmissionAllowed': f'{(date.today() + timedelta(days=1)).isoformat()}T00:00:00'
            }), 200
        
        # Proceed with Gemini AI mood entry save
        print('✅ Daily limit check passed, proceeding with Gemini AI analysis')
        result = mood_service.save_mood_entry(user_id, mood, content, questionnaire_data)
        
        processing_time = time.time() - start_time
        print(f'✅ Mood entry saved successfully in {processing_time:.2f}s')
        
        return jsonify({
            'id': result['id'],
            'analysis': result['analysis'],
            'success': True,
            'processingTime': round(processing_time, 2),
            'analysisSource': result['analysis'].get('source', 'unknown'),
            'aiUsed': not result['analysis'].get('ai_failed', False)
        }), 201

    except Exception as e:
        processing_time = time.time() - start_time
        print(f'❌ Error saving mood entry (after {processing_time:.2f}s): {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500

@mood_bp.route('/mood', methods=['GET'])
def get_mood_entries():
    """Get user's mood entries"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id = verify_token(token)
    if not authenticated_user_id:
        return jsonify({'error': 'Invalid access token'}), 401

    user_id = request.args.get('userId')
    if not user_id:
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    
    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    # Skip user ID mismatch check for test users
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403

    try:
        authenticated_supabase = create_authenticated_supabase_client(token)
        mood_service = MoodService(authenticated_supabase)
        
        entries = mood_service.get_recent_mood_entries(user_id)
        
        # Format entries for response
        formatted_entries = [
            {
                'id': entry['mood_id'],
                'userId': user_id,
                'content': entry['content'],
                'mood': entry['mood'],
                'date': entry['created_at'],
                'analysis': entry['analysis']
            }
            for entry in entries
        ]
        
        return jsonify(formatted_entries), 200

    except Exception as e:
        print(f'❌ Error fetching mood entries: {str(e)}')
        return jsonify({'error': 'Internal server error'}), 500
