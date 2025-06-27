from flask import Blueprint, request, jsonify, current_app, g
import uuid
import re
import requests
from datetime import datetime, date, timedelta, timezone
import json
import time
from typing import Dict, Any, Optional, List
import os
from app.routes.auth import auth_required
import google.generativeai as genai
from google.api_core import exceptions
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set")
genai.configure(api_key=GEMINI_API_KEY)

mood_bp = Blueprint('mood', __name__)

# UUID validation regex
uuid_regex = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)

MODEL_NAME = "gemini-1.5-flash-latest"

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
    """Enhanced mood analysis class with direct Gemini AI approach"""
    
    def __init__(self):
        self.max_retries = 3
        self.use_ai_first = True
    
    def analyze_mood(self, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        print(f'🧠 Starting GEMINI AI mood analysis for content length: {len(content)}')
        
        for attempt in range(self.max_retries):
            print(f'🤖 Gemini AI Analysis attempt {attempt + 1}/{self.max_retries}')
            ai_result = self._call_gemini_direct(content, questionnaire_data, attempt)
            
            if ai_result and self._is_valid_analysis(ai_result):
                print(f'✅ Gemini AI analysis successful on attempt {attempt + 1} with score: {ai_result.get("score")}')
                ai_result['source'] = 'gemini-direct'
                ai_result['attempt'] = attempt + 1
                return ai_result
            
            if attempt < self.max_retries - 1:
                print(f'⚠️ Gemini AI attempt {attempt + 1} failed, retrying...')
                time.sleep(2 ** attempt)
        
        print('❌ Gemini AI analysis failed after all attempts, using enhanced local analysis as last resort')
        local_result = self._create_local_analysis(content, questionnaire_data)
        local_result['ai_failed'] = True
        local_result['ai_attempts'] = self.max_retries
        return local_result
    
    def _call_gemini_direct(self, content: str, questionnaire_data: Dict[str, Any], attempt: int) -> Optional[Dict[str, Any]]:
        try:
            print(f'🌐 Initializing Gemini model: {MODEL_NAME}')
            model = genai.GenerativeModel(
                model_name=MODEL_NAME,
                generation_config={
                    "temperature": 0.7,
                    "top_k": 40,
                    "top_p": 0.9,
                    "max_output_tokens": 300
                },
                safety_settings=[
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
                ]
            )

            mood_scale = self._extract_mood_scale(questionnaire_data)
            mood_word = self._extract_mood_word(questionnaire_data)
            positive_experience = self._extract_positive_experience(questionnaire_data)
            affecting_factor = self._extract_concerns(questionnaire_data)

            prompt = self._create_comprehensive_prompt(content, mood_scale, mood_word, positive_experience, affecting_factor)
            print(f'📊 Sending prompt to Gemini, attempt {attempt + 1}/{self.max_retries}')

            response = model.generate_content(prompt)
            json_string = response.text.strip()

            # Clean and parse JSON
            json_string = json_string.replace("```json\n", "").replace("```", "").strip()
            if not json_string.startswith("{"):
                json_string = "{" + json_string + "}"

            try:
                result = json.loads(json_string)
                # Validate response
                if (
                    isinstance(result.get("score"), (int, float)) and 0 <= result["score"] <= 10 and
                    isinstance(result.get("emoji"), str) and
                    isinstance(result.get("sentiment"), str) and
                    isinstance(result.get("insights"), str) and
                    isinstance(result.get("suggestions"), list) and len(result["suggestions"]) == 4 and
                    isinstance(result.get("themes"), list) and len(result["themes"]) > 0 and
                    isinstance(result.get("confidence"), (int, float)) and 0 <= result["confidence"] <= 1 and
                    isinstance(result.get("mood_category"), str) and
                    isinstance(result.get("intensity"), str)
                ):
                    print(f'✅ Gemini response validated: score={result["score"]}, sentiment={result["sentiment"]}')
                    return result
                else:
                    print(f'❌ Invalid Gemini response format: {json_string}')
                    return None
            except json.JSONDecodeError as e:
                print(f'❌ Failed to parse Gemini JSON response: {json_string}, error: {e}')
                return None
        except exceptions.ResourceExhausted as e:
            print(f'⏰ Quota exceeded error: {e}, attempt {attempt + 1}/{self.max_retries}')
            if attempt == self.max_retries - 1:
                return {
                    "error": f"Failed to analyze mood with Gemini: {e}. You have exceeded the free tier quota (50 requests/day). Wait until 07:00 +07 on June 28, 2025, for reset or upgrade your plan. See https://ai.google.dev/gemini-api/docs/rate-limits for details.",
                    "score": 5.0,
                    "emoji": "😐",
                    "sentiment": "neutral",
                    "insights": "Analysis failed due to quota limit.",
                    "suggestions": [
                        "Wait for quota reset.",
                        "Consider a paid plan.",
                        "Check usage at https://ai.google.dev/gemini-api/docs/rate-limits.",
                        "Try again later."
                    ],
                    "themes": ["unknown"],
                    "confidence": 0.0,
                    "mood_category": "unknown",
                    "intensity": "low"
                }
            return None
        except exceptions.InvalidArgument as e:
            print(f'❌ API key error: {e}')
            return {
                "error": f"Failed to analyze mood with Gemini: {e}. The API key is invalid or expired. Renew it at https://aistudio.google.com/app/apikey.",
                "score": 5.0,
                "emoji": "😐",
                "sentiment": "neutral",
                "insights": "Analysis failed due to an invalid API key.",
                "suggestions": [
                    "Renew your API key.",
                    "Update GEMINI_API_KEY in .env.",
                    "Retry after updating.",
                    "Contact support if needed."
                ],
                "themes": ["unknown"],
                "confidence": 0.0,
                "mood_category": "unknown",
                "intensity": "low"
            }
        except Exception as e:
            print(f'❌ Error in Gemini analysis: {e}')
            return None
    
    def _create_comprehensive_prompt(self, content: str, mood_scale: int, mood_word: str, 
                                   positive_experience: str, concerns: str) -> str:
        prompt = f"""
You are an empathetic AI mood analyzer. Analyze this mood journal entry and provide a structured JSON response.

JOURNAL ENTRY:
{content or 'No content provided'}

MOOD SELF-RATING: {mood_scale}/10
MOOD WORD: {mood_word or 'Not specified'}
POSITIVE EXPERIENCE: {positive_experience or 'Not specified'}
CONCERNS/CHALLENGES: {concerns or 'Not specified'}

Respond with ONLY a JSON object in this exact format:
{{
    "score": [float between 0-10],
    "emoji": "[single emoji representing mood]",
    "sentiment": "[very negative/negative/slightly negative/neutral/slightly positive/positive/very positive]",
    "insights": "[2-3 sentences of personalized insights using 'you' language]",
    "suggestions": ["suggestion1", "suggestion2", "suggestion3", "suggestion4"],
    "themes": ["theme1", "theme2", "theme3"],
    "confidence": [float between 0-1],
    "mood_category": "[primary mood category]",
    "intensity": "[low/medium/high]"
}}

Be empathetic, supportive, and provide actionable suggestions. Use 'you' language to address the user directly.
"""
        return prompt
    
    def _extract_mood_scale(self, questionnaire_data: Dict[str, Any]) -> int:
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return 5
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] == 'feeling_scale':
                try:
                    scale = int(float(response['user_response']))
                    return max(1, min(10, scale))
                except (ValueError, TypeError):
                    pass
        
        return 5
    
    def _extract_mood_word(self, questionnaire_data: Dict[str, Any]) -> str:
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] == 'mood_word':
                return str(response['user_response']).strip()
        
        return ""
    
    def _extract_positive_experience(self, questionnaire_data: Dict[str, Any]) -> str:
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] in ['positive_experience', 'gratitude']:
                return str(response['user_response']).strip()
        
        return ""
    
    def _extract_concerns(self, questionnaire_data: Dict[str, Any]) -> str:
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        concerns_list = []
        for response in questionnaire_data['questionnaire_responses']:
            if response['question_id'] in ['challenging_experience', 'stress_level', 'concerns']:
                concerns_list.append(str(response['user_response']).strip())
        
        return "; ".join(concerns_list) if concerns_list else ""
    
    def _transform_gemini_response(self, gemini_result: Dict[str, Any]) -> Dict[str, Any]:
        try:
            score = gemini_result.get('score', 5.0)
            emoji = gemini_result.get('emoji', '😐')
            sentiment = gemini_result.get('sentiment', 'neutral')
            insights = gemini_result.get('insights', 'No insights provided.')
            suggestions = gemini_result.get('suggestions', [
                "Try again later.",
                "Reflect on your day.",
                "Practice self-care.",
                "Contact support if needed."
            ])
            themes = gemini_result.get('themes', ['mood_analysis'])
            confidence = gemini_result.get('confidence', 0.95)
            mood_category = gemini_result.get('mood_category', 'neutral')
            intensity = gemini_result.get('intensity', 'low')

            transformed = {
                'score': round(float(score), 1),
                'emoji': emoji,
                'sentiment': sentiment,
                'insights': insights,
                'suggestions': suggestions[:4],
                'themes': themes,
                'confidence': confidence,
                'mood_category': mood_category,
                'intensity': intensity,
                'source': 'gemini-direct',
                'timestamp': datetime.utcnow().isoformat(),
                'original_response': gemini_result
            }
        
            print(f'✅ Transformed Gemini response: Score {score}, Sentiment {sentiment}')
            return transformed
        
        except Exception as e:
            print(f'❌ Error transforming Gemini response: {e}')
            print(f'❌ Original response: {gemini_result}')
            return None
    
    def _is_valid_analysis(self, analysis: Dict[str, Any]) -> bool:
        if not analysis:
            return False
        
        required_fields = ['score', 'sentiment', 'insights']
        
        if not all(field in analysis for field in required_fields):
            missing = [f for f in required_fields if f not in analysis]
            print(f'❌ Analysis missing fields: {missing}')
            return False
        
        try:
            score = float(analysis['score'])
            if not 0 <= score <= 10:
                print(f'❌ Invalid score: {score}')
                return False
        except (ValueError, TypeError):
            print(f'❌ Score not numeric: {analysis["score"]}')
            return False
        
        insights = analysis['insights']
        if not isinstance(insights, str) or len(insights.strip()) < 10:
            print(f'❌ Invalid insights: {insights}')
            return False
        
        print('✅ Analysis validation passed')
        return True
    
    def _create_local_analysis(self, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        print('🔧 Creating FALLBACK local analysis (Gemini AI unavailable)')
        
        base_score = self._extract_base_score(questionnaire_data)
        content_adjustment = self._analyze_content_sentiment(content)
        questionnaire_adjustment = self._analyze_questionnaire_responses(questionnaire_data)
        
        final_score = max(0.0, min(10.0, base_score + content_adjustment + questionnaire_adjustment))
        
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
        if score >= 8.5 or score <= 1.5:
            return 'high'
        elif score >= 6.5 or score <= 3.5:
            return 'medium'
        else:
            return 'low'
    
    def _generate_insights(self, score: float, content: str, questionnaire_data: Dict[str, Any]) -> str:
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
        if not insights:
            return insights
        
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
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.analyzer = MoodAnalyzer()
    
    def check_daily_mood_exists(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            today_utc = datetime.now(timezone.utc).date()
            start_of_day = datetime.combine(today_utc, datetime.min.time(), tzinfo=timezone.utc).isoformat()
            end_of_day = datetime.combine(today_utc, datetime.max.time(), tzinfo=timezone.utc).isoformat()
            
            print(f'🔍 Server UTC time: {datetime.now(timezone.utc).isoformat()}')
            print(f'🔍 Checking daily mood for user {user_id} on {today_utc} (UTC)')
            print(f'🔍 Query range: {start_of_day} to {end_of_day}')
            
            response = self.supabase.table('mood_entries')\
                .select('mood_id, analysis, created_at, mood, content')\
                .eq('user_id', user_id)\
                .gte('created_at', start_of_day)\
                .lte('created_at', end_of_day)\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            print(f'🔍 Supabase response: {response.data}')
            
            if response.data and len(response.data) > 0:
                entry = response.data[0]
                print(f'✅ Found existing mood entry: {entry["mood_id"]} at {entry["created_at"]}')
                return entry
            
            print(f'✅ No mood entry found for today ({today_utc})')
            return None
            
        except Exception as e:
            print(f'❌ Error checking daily mood: {e}')
            return None
    
    def save_mood_entry(self, user_id: str, mood: str, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            print(f'💾 Starting mood entry save for user: {user_id}')
            
            print('🧠 Starting Gemini AI mood analysis...')
            analysis_start = time.time()
            analysis = self.analyzer.analyze_mood(content, questionnaire_data)
            analysis_time = time.time() - analysis_start
            print(f'✅ Analysis completed in {analysis_time:.2f}s')
            
            mood_entry = {
                'mood_id': str(uuid.uuid4()),
                'user_id': user_id,
                'mood': mood,
                'content': content,
                'analysis': analysis,
                'questionnaire_data': questionnaire_data,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
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

@mood_bp.route('/mood/check-today', methods=['GET'])
@auth_required
def check_today_mood():
    user_id = request.args.get('userId')
    if not user_id:
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    
    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403
    
    try:
        mood_service = MoodService(current_app.supabase)
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
@auth_required
def save_mood_entry():
    start_time = time.time()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
        
    user_id = data.get('userId')
    mood = data.get('mood')
    content = data.get('content')
    questionnaire_data = data.get('questionnaireData', {})

    if not user_id:
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    
    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403
    
    if not mood or not content:
        return jsonify({'error': 'Missing required fields: mood and content'}), 400

    try:
        print(f'💾 Processing mood entry for user: {user_id}')
        mood_service = MoodService(current_app.supabase)
        
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
                'nextSubmissionAllowed': f'{(datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()}T00:00:00'
            }), 200
        
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
@auth_required
def get_mood_entries():
    user_id = request.args.get('userId')
    if not user_id:
        return jsonify({'error': 'Invalid or missing user_id'}), 400
    
    try:
        _validate_user_id(user_id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    authenticated_user_id = g.user.id
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id not in test_user_ids and authenticated_user_id != user_id:
        return jsonify({'error': 'Unauthorized: User ID mismatch'}), 403

    try:
        mood_service = MoodService(current_app.supabase)
        entries = mood_service.get_recent_mood_entries(user_id)
        
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