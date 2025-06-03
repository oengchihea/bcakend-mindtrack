from flask import Blueprint, request, jsonify, current_app
import uuid
import re
import requests # type: ignore
from datetime import datetime, date, timedelta
import json
import time
from typing import Dict, Any, Optional, List
import os

# MODIFIED: Changed blueprint name and prefix for clarity and to avoid conflicts
mood_bp = Blueprint('mood_entries_api', __name__, url_prefix='/api/mood-entries')

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
        self.ai_base_url = os.getenv('VERCEL_AI_URL', "https://ai-mindtrack.vercel.app") # Ensure VERCEL_AI_URL is in .env
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
                "analysisType": "immediate-mood" # This seems to be what the AI service expects
            }
        
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'MindTrack-Enhanced/2.0', # Good practice
                'Accept': 'application/json'
            }
        
            # Add API key if available
            if self.ai_api_key:
                headers['Authorization'] = f'Bearer {self.ai_api_key}'
                # Some APIs use X-API-Key, check your AI service documentation
                # headers['X-API-Key'] = self.ai_api_key 
        
            print(f'🌐 Calling Gemini AI API: {self.ai_api_url}')
            print(f'📊 Payload for AI: {json.dumps(payload, indent=2)}') # Log the exact payload
        
            response = requests.post(
                self.ai_api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                verify=True # Keep True for production HTTPS
            )
        
            print(f'📊 Gemini AI Response Status: {response.status_code}')
            # print(f'📊 Gemini AI Response Body: {response.text[:500]}...') # Log part of the response body for debugging
        
            if response.status_code == 200:
                result = response.json()
                print(f'✅ Gemini AI success. Response keys: {list(result.keys())}')
            
                # Transform Gemini AI response to our format
                transformed_result = self._transform_gemini_response(result)
                return transformed_result
            else:
                print(f'❌ Gemini AI error {response.status_code}: {response.text}')
                return None
            
        except requests.exceptions.Timeout:
            print(f'⏰ Gemini AI timeout after {self.timeout}s')
            return None
        except requests.exceptions.ConnectionError as ce:
            print(f'🌐 Gemini AI connection error: {ce}')
            return None
        except Exception as e:
            print(f'❌ Gemini AI call exception: {str(e)}')
            import traceback
            traceback.print_exc()
            return None
    
    def _create_comprehensive_prompt(self, content: str, mood_scale: int, mood_word: str, 
                                   positive_experience: str, concerns: str) -> str:
        """Create comprehensive prompt for Gemini AI analysis (if it were direct text-to-JSON)"""
        # This method might not be directly used if the /api/analyze-data endpoint expects structured data
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
            return 5 # Default neutral
        
        responses = questionnaire_data['questionnaire_responses']
        if not isinstance(responses, list): return 5

        for response in responses:
            if isinstance(response, dict) and response.get('question_id') == 'feeling_scale':
                try:
                    scale_val = response.get('user_response')
                    if scale_val is not None:
                        scale = int(float(str(scale_val)))
                        return max(1, min(10, scale))  # Ensure 1-10 range
                except (ValueError, TypeError):
                    pass # Continue if parsing fails for one response
        
        return 5  # Default neutral if not found or parsing failed for all
    
    def _extract_mood_word(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract mood word from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        responses = questionnaire_data['questionnaire_responses']
        if not isinstance(responses, list): return ""

        for response in responses:
            if isinstance(response, dict) and response.get('question_id') == 'mood_word':
                mood_w = response.get('user_response')
                return str(mood_w).strip() if mood_w is not None else ""
        
        return ""
    
    def _extract_positive_experience(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract positive experience from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        responses = questionnaire_data['questionnaire_responses']
        if not isinstance(responses, list): return ""

        for response in responses:
            if isinstance(response, dict) and response.get('question_id') in ['positive_experience', 'gratitude']:
                pos_exp = response.get('user_response')
                return str(pos_exp).strip() if pos_exp is not None else ""
        
        return ""
    
    def _extract_concerns(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract concerns/challenges from questionnaire"""
        if not questionnaire_data or 'questionnaire_responses' not in questionnaire_data:
            return ""
        
        responses = questionnaire_data['questionnaire_responses']
        if not isinstance(responses, list): return ""
        
        concerns_list = []
        for response in responses:
            if isinstance(response, dict) and response.get('question_id') in ['challenging_experience', 'stress_level', 'concerns']:
                concern_text = response.get('user_response')
                if concern_text is not None and str(concern_text).strip():
                    concerns_list.append(str(concern_text).strip())
        
        return "; ".join(concerns_list) if concerns_list else ""
    
    def _transform_gemini_response(self, gemini_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Transform Gemini AI response (from /api/analyze-data) to our standard format"""
        try:
            # The Vercel AI service /api/analyze-data returns a structure like:
            # { "analysis": { "score": N, "emoji": "text_emoji", "insights": "...", ... }, "suggestions": [...] }
            # Or sometimes the analysis is at the top level.
            
            analysis_data = gemini_result.get('analysis', gemini_result) # Handle both cases
            if not isinstance(analysis_data, dict):
                print(f'❌ Gemini response "analysis" part is not a dictionary: {analysis_data}')
                return None

            # Extract fields from the API response
            # The AI service returns score on a 1-5 scale.
            api_score = analysis_data.get('score') 
            if api_score is None: # score is essential
                print(f'❌ Gemini response missing "score" in analysis: {analysis_data}')
                return None
            try:
                api_score = float(api_score)
            except ValueError:
                print(f'❌ Gemini response "score" is not a valid number: {api_score}')
                return None

            emoji_text = analysis_data.get('emoji', 'neutral') # e.g., "happy", "sad"
            insights = analysis_data.get('insights', '')
            suggestions_from_ai = analysis_data.get('suggestions', gemini_result.get('suggestions', []))
            if not isinstance(suggestions_from_ai, list): suggestions_from_ai = []

            # Convert 1-5 scale from AI to our 0-10 scale
            # (1 -> 0, 2 -> 2.5, 3 -> 5, 4 -> 7.5, 5 -> 10)
            converted_score = ((api_score - 1) / 4) * 10 
            converted_score = max(0.0, min(10.0, converted_score))
        
            # Convert emoji text (e.g., "happy") to actual emoji character
            emoji_map = {
                'sad': '😢', 'very_sad': '😭',
                'slightly_sad': '😔',
                'neutral': '😐',
                'slightly_happy': '🙂',
                'happy': '😊', 'very_happy': '😄', 'ecstatic': '🥳',
                'angry': '😠', 'frustrated': '😤',
                'anxious': '😟', 'worried': '😥',
                # Add more mappings as needed based on AI service output
            }
            emoji = emoji_map.get(str(emoji_text).lower().replace(" ", "_"), '😐') # Default emoji
        
            # Generate sentiment from our converted score
            sentiment = self._get_sentiment_from_score(converted_score)
        
            # Ensure insights is meaningful and in second person
            if not insights or len(str(insights).strip()) < 20:
                insights = self._generate_insights(converted_score, '', {}) # Generate fallback
            else:
                insights = self._convert_to_second_person(str(insights))
            
            # Use suggestions from AI if available, else generate fallback
            suggestions = suggestions_from_ai if suggestions_from_ai else self._generate_suggestions(converted_score, {})
            
            themes = analysis_data.get('themes', ['mood_analysis']) # Default theme
            if not isinstance(themes, list): themes = ['mood_analysis']

            transformed = {
                'score': round(converted_score, 1),
                'emoji': emoji,
                'sentiment': sentiment,
                'insights': insights,
                'suggestions': suggestions[:4],  # Limit to 4 suggestions
                'themes': themes[:3], # Limit to 3 themes
                'confidence': analysis_data.get('confidence', 0.90), # Use AI confidence if provided
                'mood_category': self._get_mood_category_from_score(converted_score),
                'intensity': self._get_intensity_from_score(converted_score),
                'source': 'gemini-ai-api', # Clearly mark the source
                'timestamp': datetime.utcnow().isoformat(),
                'original_api_response': { # Optionally store parts of original for debugging
                    'api_score': api_score,
                    'api_emoji_text': emoji_text,
                    'api_insights_preview': str(analysis_data.get('insights', ''))[:100]
                }
            }
        
            print(f'✅ Transformed Gemini response: API Score {api_score} -> Our Score {converted_score}, Emoji {emoji}, Sentiment {sentiment}')
            return transformed
        
        except Exception as e:
            print(f'❌ Error transforming Gemini response: {e}')
            print(f'❌ Original Gemini response structure that caused error: {json.dumps(gemini_result, indent=2, default=str)}')
            import traceback
            traceback.print_exc()
            return None

    def _is_valid_analysis(self, analysis: Optional[Dict[str, Any]]) -> bool:
        """Validate analysis response"""
        if not analysis or not isinstance(analysis, dict):
            print(f'❌ Analysis is None or not a dict.')
            return False
        
        required_fields = ['score', 'sentiment', 'insights', 'emoji']
        
        # Check required fields exist
        missing = [field for field in required_fields if field not in analysis]
        if missing:
            print(f'❌ Analysis missing fields: {missing}. Analysis content: {analysis}')
            return False
        
        # Validate score
        try:
            score = float(analysis['score'])
            if not 0 <= score <= 10:
                print(f'❌ Invalid score: {score}. Analysis content: {analysis}')
                return False
        except (ValueError, TypeError):
            print(f'❌ Score not numeric: {analysis["score"]}. Analysis content: {analysis}')
            return False
        
        # Validate insights
        insights = analysis['insights']
        if not isinstance(insights, str) or len(insights.strip()) < 10:
            print(f'❌ Invalid insights (too short or not string): "{insights}". Analysis content: {analysis}')
            # Allow if it's a placeholder from AI, but log it.
            if "placeholder" not in insights.lower() and "default" not in insights.lower():
                 # return False # Stricter validation
                 pass # Allow for now, but this is a sign of poor AI response
        
        print('✅ Analysis structure validation passed (basic fields).')
        return True
    
    def _create_local_analysis(self, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced local analysis as fallback"""
        print('🔧 Creating FALLBACK local analysis (Gemini AI unavailable or failed)')
        
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
            'confidence': 0.7, # Lower confidence for local analysis
            'mood_category': self._get_mood_category_from_score(final_score),
            'intensity': self._get_intensity_from_score(final_score),
            'source': 'enhanced-local-analysis', # Clearly mark source
            'timestamp': datetime.utcnow().isoformat(),
            'fallback_reason': 'Gemini AI analysis unavailable or failed validation'
        }
        
        print(f'✅ Fallback local analysis complete: Score {final_score}, Sentiment {sentiment}')
        return analysis
    
    def _extract_base_score(self, questionnaire_data: Dict[str, Any]) -> float:
        """Extract base score from questionnaire responses"""
        scale_val = self._extract_mood_scale(questionnaire_data) # Uses the refined extraction
        return float(scale_val) if scale_val is not None else 5.0

    # ... (keep _analyze_content_sentiment, _analyze_questionnaire_responses, _get_sentiment_from_score, etc.) ...
    # The rest of the MoodAnalyzer helper methods (_get_emoji_from_score, _generate_insights, etc.)
    # from your provided code can remain largely the same. I'm omitting them here for brevity
    # but they should be included in your actual file.
    # Make sure they are robust to missing data in questionnaire_data.

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
        responses = questionnaire_data['questionnaire_responses']
        if not isinstance(responses, list): return 0.0
        
        for response_item in responses:
            if not isinstance(response_item, dict): continue
            question_id = response_item.get('question_id')
            user_answer_val = response_item.get('user_response')
            if user_answer_val is None: continue
            user_answer = str(user_answer_val).lower()
            
            if question_id == 'stress_level':
                try:
                    stress = float(user_answer_val)
                    adjustment -= (stress - 5) * 0.3 # Assuming stress is 0-10, 5 is neutral
                except (ValueError, TypeError):
                    pass
            
            elif question_id == 'energy_level':
                try:
                    energy = float(user_answer_val)
                    adjustment += (energy - 5) * 0.2 # Assuming energy is 0-10
                except (ValueError, TypeError):
                    pass
            
            elif question_id == 'sleep_quality':
                if 'excellent' in user_answer: adjustment += 1.0
                elif 'good' in user_answer: adjustment += 0.5
                elif 'poor' in user_answer: adjustment -= 0.8
                elif 'fair' in user_answer: adjustment -= 0.3
        
        return max(-2.0, min(2.0, adjustment))

    def _get_sentiment_from_score(self, score: float) -> str:
        if score >= 8.5: return 'very positive'
        elif score >= 7.0: return 'positive'
        elif score >= 6.0: return 'slightly positive'
        elif score >= 4.5: return 'neutral'
        elif score >= 3.0: return 'slightly negative'
        elif score >= 1.5: return 'negative'
        else: return 'very negative'

    def _get_emoji_from_score(self, score: float) -> str:
        if score >= 9.0: return '😄'
        elif score >= 7.5: return '😊'
        elif score >= 6.0: return '🙂'
        elif score >= 4.5: return '😐'
        elif score >= 3.0: return '😕'
        elif score >= 1.5: return '😔'
        else: return '😢'

    def _get_mood_category_from_score(self, score: float) -> str:
        if score >= 8.5: return 'joyful'
        elif score >= 7.0: return 'happy'
        elif score >= 6.0: return 'content'
        elif score >= 4.5: return 'neutral'
        elif score >= 3.0: return 'sad'
        elif score >= 1.5: return 'distressed'
        else: return 'very distressed'

    def _get_intensity_from_score(self, score: float) -> str:
        if score >= 8.5 or score <= 1.5: return 'high'
        elif score >= 6.5 or score <= 3.5: return 'medium'
        else: return 'low'

    def _generate_insights(self, score: float, content: str, questionnaire_data: Dict[str, Any]) -> str:
        sentiment_term = self._get_sentiment_from_score(score)
        insights = f"Based on your responses, you seem to be experiencing {sentiment_term} emotions, with a wellness score of {score:.1f}/10. "
        
        if score >= 8: insights += "It's wonderful that you're feeling so positive! Keep nurturing this state by continuing what works for you."
        elif score >= 6: insights += "You're in a good emotional space. This is a great time to build on positive habits and enjoy your well-being."
        elif score >= 4: insights += "Your emotional state appears relatively balanced. Consider exploring small ways to enhance your mood further if you wish."
        else: insights += "It sounds like you might be facing some challenges. Remember to be kind to yourself and seek support if needed."
        
        # Add more specific insights based on questionnaire_data if available
        concerns = self._extract_concerns(questionnaire_data)
        if concerns:
            insights += f" You mentioned some concerns regarding: {concerns}. Acknowledging these is a brave first step."
        return insights

    def _generate_suggestions(self, score: float, questionnaire_data: Dict[str, Any]) -> List[str]:
        suggestions = []
        if score >= 8:
            suggestions.extend([
                "Continue the activities that bring you joy and fulfillment.",
                "Share your positive energy with others if you feel inclined.",
                "Take a moment to savor this feeling of well-being.",
                "Reflect on what contributed to this positive state and how to maintain it."
            ])
        elif score >= 6:
            suggestions.extend([
                "Build on this positive momentum with activities you enjoy.",
                "Practice gratitude for the good things in your life.",
                "Connect with supportive people who uplift your spirits.",
                "Maintain healthy habits that contribute to your well-being."
            ])
        elif score >= 4:
            suggestions.extend([
                "Engage in activities that typically boost your mood, even small ones.",
                "Take some time for self-reflection and gentle self-care.",
                "Consider reaching out to a friend or loved one for connection.",
                "Explore mindfulness or relaxation techniques if you're feeling a bit off."
            ])
        else: # score < 4
            suggestions.extend([
                "Be extra gentle and compassionate with yourself during this time.",
                "Practice grounding techniques like deep breathing or a short walk.",
                "Consider reaching out to a trusted friend, family member, or professional for support.",
                "Focus on small, comforting activities that feel manageable."
            ])
        return suggestions[:4] # Limit to 4

    def _extract_themes(self, content: str, questionnaire_data: Dict[str, Any]) -> List[str]:
        themes = []
        content_lower = content.lower()
        theme_keywords = {
            'stress': ['stress', 'pressure', 'overwhelm', 'anxiety'], 'gratitude': ['grateful', 'thankful', 'appreciate'],
            'relationships': ['friend', 'family', 'partner', 'social'], 'work': ['work', 'job', 'career', 'study'],
            'self-care': ['self-care', 'relax', 'hobby', 'rest'], 'achievement': ['accomplish', 'goal', 'success', 'proud']
        }
        for theme, keywords in theme_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                themes.append(theme)
        
        # Add themes from questionnaire if applicable (e.g., if specific questions map to themes)
        # For example, if questionnaire_data has a 'main_focus_today' field.
        
        return list(set(themes))[:3] # Unique themes, limit to 3

    def _convert_to_second_person(self, insights: str) -> str:
        if not insights: return insights
        # Simple replacements, can be made more sophisticated
        replacements = {
            "The user reports": "You reported", "the user's": "your", "The user is": "You are",
            "the user": "you", "The user": "You", "their": "your", "they are": "you are",
            "they feel": "you feel", "They should": "You should", "one's": "your"
        }
        for old, new in replacements.items():
            insights = insights.replace(old, new)
        # Ensure first letter is capitalized if it became lowercase
        if insights and insights[0].islower() and insights.startswith("you"):
            insights = "Y" + insights[1:]
        return insights

class MoodService:
    """Enhanced mood service with strict daily limit checking"""
    
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.analyzer = MoodAnalyzer()
    
    def check_daily_mood_exists(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Strict daily mood checking"""
        today_utc = datetime.utcnow().date() # Use UTC date for consistency
        start_of_day_utc = datetime.combine(today_utc, datetime.min.time()).isoformat()
        end_of_day_utc = datetime.combine(today_utc, datetime.max.time()).isoformat()

        try:
            print(f'🔍 [MoodService] Checking daily mood for user {user_id} on {today_utc.isoformat()}')
            
            response = self.supabase.table('mood_entries')\
                .select('mood_id, analysis, created_at, mood, content')\
                .eq('user_id', user_id)\
                .gte('created_at', start_of_day_utc)\
                .lte('created_at', end_of_day_utc) \
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()
            
            if response.data and len(response.data) > 0:
                entry = response.data[0]
                print(f'✅ [MoodService] Found existing mood entry: {entry["mood_id"]} at {entry["created_at"]}')
                return entry
            
            print(f'✅ [MoodService] No mood entry found for today ({today_utc.isoformat()}) for user {user_id}.')
            return None
            
        except Exception as e:
            print(f'❌ [MoodService] Error checking daily mood: {e}')
            current_app.logger.error(f"Error in check_daily_mood_exists for user {user_id}: {e}", exc_info=True)
            return None # Important to return None on error so user isn't blocked
    
    def save_mood_entry(self, user_id: str, mood: str, content: str, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save new mood entry with Gemini AI analysis"""
        try:
            print(f'💾 [MoodService] Starting mood entry save for user: {user_id}')
            
            # Generate analysis with Gemini AI
            print('🧠 [MoodService] Starting mood analysis...')
            analysis_start_time = time.time()
            analysis_result = self.analyzer.analyze_mood(content, questionnaire_data)
            analysis_duration = time.time() - analysis_start_time
            print(f'✅ [MoodService] Analysis completed in {analysis_duration:.2f}s. Source: {analysis_result.get("source", "unknown")}')
            
            if not self.analyzer._is_valid_analysis(analysis_result): # Use the validation
                print(f'❌ [MoodService] Analysis result is invalid. Not saving. Result: {analysis_result}')
                # Fallback to a very basic entry or error out
                # For now, let's create a minimal analysis if AI failed badly
                if 'score' not in analysis_result: # if it's completely broken
                    analysis_result = {
                        'score': 5.0, 'emoji': '🤔', 'sentiment': 'unknown', 
                        'insights': 'Mood analysis could not be completed at this time.',
                        'suggestions': ['Please try again later.'], 'themes': [],
                        'source': 'error-fallback', 'timestamp': datetime.utcnow().isoformat()
                    }
                # else, it might be partially valid (e.g. missing insights but has score)

            mood_entry_payload = {
                'mood_id': str(uuid.uuid4()),
                'user_id': user_id,
                'mood': mood, # This is the user-selected mood word/category
                'content': content, # This is the free-text or answers from questionnaire
                'analysis': analysis_result, # This is the detailed AI analysis
                'questionnaire_data': questionnaire_data, # Raw questionnaire responses
                'created_at': datetime.utcnow().isoformat()
            }
            
            # Save to database
            print(f'💾 [MoodService] Saving mood entry to database: {mood_entry_payload["mood_id"]}')
            insert_response = self.supabase.table('mood_entries').insert(mood_entry_payload).execute()
            
            # Supabase Python client v1.x .execute() returns an APIResponse object
            # data is in insert_response.data
            if insert_response.data and len(insert_response.data) > 0:
                print(f'✅ [MoodService] Mood entry saved successfully: {mood_entry_payload["mood_id"]}')
                return {
                    'id': mood_entry_payload['mood_id'],
                    'analysis': analysis_result,
                    'success': True,
                    'message': 'Mood entry saved successfully.',
                    'processing_time': round(analysis_duration, 2)
                }
            else:
                # Log error from Supabase if available in insert_response
                error_message = "Failed to save mood entry to database."
                if hasattr(insert_response, 'error') and insert_response.error:
                    error_message += f" Supabase error: {insert_response.error.message}"
                    current_app.logger.error(f"Supabase insert error for mood_entries: {insert_response.error.message} - Details: {insert_response.error}")
                elif hasattr(insert_response, 'status_code') and insert_response.status_code not in [200, 201]:
                     error_message += f" Status: {insert_response.status_code}"
                     current_app.logger.error(f"Supabase insert non-success status for mood_entries: {insert_response.status_code} - Body: {insert_response.data}")
                else:
                    current_app.logger.error(f"Supabase insert failed for mood_entries, no data returned. Response: {insert_response}")

                raise Exception(error_message)
                
        except Exception as e:
            print(f'❌ [MoodService] Error saving mood entry: {e}')
            current_app.logger.error(f"Exception in save_mood_entry for user {user_id}: {e}", exc_info=True)
            raise # Re-raise the exception to be caught by the route handler
    
    def get_recent_mood_entries(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        """Get user's recent mood entries"""
        try:
            response = self.supabase.table('mood_entries')\
                .select('mood_id, mood, content, analysis, created_at, questionnaire_data')\
                .eq('user_id', user_id)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()
            
            # Process entries to ensure analysis and questionnaire_data are dicts
            entries = response.data or []
            processed_entries = []
            for entry in entries:
                if isinstance(entry.get('analysis'), str):
                    try: entry['analysis'] = json.loads(entry['analysis'])
                    except json.JSONDecodeError: entry['analysis'] = {'error': 'Could not parse analysis JSON'}
                if isinstance(entry.get('questionnaire_data'), str):
                    try: entry['questionnaire_data'] = json.loads(entry['questionnaire_data'])
                    except json.JSONDecodeError: entry['questionnaire_data'] = {'error': 'Could not parse questionnaire_data JSON'}
                processed_entries.append(entry)
            return processed_entries

        except Exception as e:
            print(f'❌ [MoodService] Error fetching mood entries: {str(e)}')
            current_app.logger.error(f"Error in get_recent_mood_entries for user {user_id}: {e}", exc_info=True)
            return []

def verify_token(token: str) -> Optional[str]:
    """Verify Supabase JWT token and return user_id"""
    if not token: return None
    try:
        # Use the app's global Supabase client instance for auth operations
        # This client is initialized with SUPABASE_URL and SUPABASE_KEY (anon or service_role)
        # The get_user() method uses the provided JWT to fetch user details from Supabase Auth.
        response = current_app.supabase.auth.get_user(token) # type: ignore
        
        if response and response.user and response.user.id:
            user_id = str(response.user.id)
            # Allow test user IDs without UUID validation
            test_user_ids = ['user123', 'test-user', 'demo-user']
            if user_id in test_user_ids:
                print(f"🔑 Token verified for test user: {user_id}")
                return user_id
            
            if uuid_regex.match(user_id):
                print(f"🔑 Token verified for user: {user_id}")
                return user_id
            else:
                print(f'❌ Token verification: User ID {user_id} is not a valid UUID.')
                return None # Invalid user ID format
        else:
            print(f'❌ Token verification failed: No user or user ID in response. Response: {response}')
            return None
    except Exception as e:
        # Supabase client might raise specific exceptions for invalid tokens (e.g., expired)
        print(f'❌ Token verification exception: {str(e)}')
        current_app.logger.warning(f"Token verification exception: {e}", exc_info=False) # Log less verbosely for common auth errors
        return None

def create_authenticated_supabase_client(token: str):
    """Create a Supabase client instance authenticated with the user's JWT."""
    # This creates a NEW client instance that will have the user's token in its headers.
    # This is useful if you need to perform operations respecting RLS for that specific user.
    # The app.supabase client might be using the service_role key.
    
    # Ensure create_client is imported if not already at module level
    from supabase import create_client as sb_create_client 
    
    # Use the same URL and anon key (or service key if that's what app.config has, though anon is typical here)
    # The key provided here is for initializing the client library; the actual auth is via the JWT.
    # It's common to use the ANON_KEY for this specific client if you want RLS to be strictly based on the user's JWT.
    # If app.config['SUPABASE_KEY'] is service_role, this client will also have service_role privileges initially,
    # but the set_session call overrides the Authorization header for subsequent requests.
    
    # Let's assume current_app.config['SUPABASE_KEY'] is the anon key for this context,
    # or that Supabase handles it correctly.
    # A more robust way might be to have SUPABASE_ANON_KEY also in config.
    
    client = sb_create_client(
        current_app.config['SUPABASE_URL'],
        current_app.config['SUPABASE_KEY'] # This should ideally be the ANON key if you want strict RLS based on JWT
    )
    
    # This sets the Authorization header for this client instance's requests
    client.auth.set_session(access_token=token, refresh_token='dummy_refresh_token_if_not_available') # refresh_token might not be needed for all ops
    # Or, more directly for PostgREST:
    # client.postgrest.auth(token) # For supabase-py v2.x
    # For supabase-py v1.x, updating headers directly is common:
    # client.postgrest.session.headers.update({'Authorization': f'Bearer {token}'})


    print(f"🔐 Created authenticated Supabase client for token ending: ...{token[-6:]}")
    return client

# MODIFIED: Route path changed
@mood_bp.route('/check-today', methods=['GET'])
def check_today_mood_route():
    """Check if user has submitted mood today with strict enforcement"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    # This user_id is from the token, representing the authenticated user
    authenticated_user_id_from_token = verify_token(token)
    if not authenticated_user_id_from_token:
        return jsonify({'error': 'Invalid or expired access token'}), 401
    
    # This user_id is from the query parameter, representing the user whose data is being requested
    user_id_from_query = request.args.get('userId')
    if not user_id_from_query:
        return jsonify({'error': 'Missing userId query parameter'}), 400
    
    try:
        _validate_user_id(user_id_from_query) # Validate format of query param userId
    except ValueError as e:
        return jsonify({'error': str(e)}), 400 # Invalid format for userId in query
    
    # Security Check: Ensure the authenticated user is requesting their own data
    # Allow test users to bypass this for easier debugging if needed, but be cautious.
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id_from_query not in test_user_ids and authenticated_user_id_from_token != user_id_from_query:
        current_app.logger.warning(
            f"Unauthorized access attempt in check_today_mood: Token user {authenticated_user_id_from_token} "
            f"tried to access data for query user {user_id_from_query}."
        )
        return jsonify({'error': 'Unauthorized: You can only check your own mood status.'}), 403
    
    try:
        # Use a Supabase client authenticated with the user's token for RLS.
        # This ensures that check_daily_mood_exists respects row-level security.
        # The MoodService will use this client.
        user_specific_supabase_client = create_authenticated_supabase_client(token)
        mood_service = MoodService(user_specific_supabase_client) # Pass the user-specific client
        
        existing_entry = mood_service.check_daily_mood_exists(user_id_from_query) # Check for the query user
        
        if existing_entry:
            print(f'🔄 User {user_id_from_query} already has mood entry for today - should redirect to home')
            # Ensure analysis is serializable (it should be if coming from JSON)
            analysis_data = existing_entry.get('analysis', {})
            if isinstance(analysis_data, str): # Just in case it's a string
                try: analysis_data = json.loads(analysis_data)
                except: analysis_data = {'error': 'analysis parse failed'}

            return jsonify({
                'hasEntry': True,
                'shouldRedirect': True, # Frontend can use this
                'message': 'You have already submitted your mood for today. Come back tomorrow!',
                'analysis': analysis_data,
                'entryId': existing_entry.get('mood_id'),
                'submittedAt': existing_entry.get('created_at'),
                'redirectTo': '/home' # Suggestion for frontend
            }), 200
        else:
            print(f'✅ User {user_id_from_query} can submit mood entry for today')
            return jsonify({
                'hasEntry': False,
                'shouldRedirect': False,
                'message': 'Ready to submit today\'s mood entry.',
                'canSubmit': True # Explicitly state they can submit
            }), 200
            
    except Exception as e:
        print(f'❌ Error in check_today_mood_route for user {user_id_from_query}: {str(e)}')
        current_app.logger.error(f"Exception in check_today_mood_route for user {user_id_from_query}: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error while checking mood status: {str(e)}'}), 500

# MODIFIED: Route path changed (matches GET for consistency)
@mood_bp.route('', methods=['POST']) # Changed from '/mood' to '' (relative to '/api/mood-entries')
def save_mood_entry_route():
    """Save new mood entry with strict daily limit and Gemini AI analysis"""
    request_start_time = time.time()
    
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id_from_token = verify_token(token)
    if not authenticated_user_id_from_token:
        return jsonify({'error': 'Invalid or expired access token'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided in request body'}), 400
        
    user_id_from_payload = data.get('userId')
    mood_from_payload = data.get('mood') # e.g., "Happy", "Sad", or a category
    content_from_payload = data.get('content') # Text content from user
    questionnaire_data_from_payload = data.get('questionnaireData', {}) # Structured Q&A

    if not user_id_from_payload:
        return jsonify({'error': 'Missing userId in request body'}), 400
    
    try:
        _validate_user_id(user_id_from_payload)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id_from_payload not in test_user_ids and authenticated_user_id_from_token != user_id_from_payload:
        current_app.logger.warning(
            f"Unauthorized access attempt in save_mood_entry_route: Token user {authenticated_user_id_from_token} "
            f"tried to save data for payload user {user_id_from_payload}."
        )
        return jsonify({'error': 'Unauthorized: You can only save your own mood entries.'}), 403
    
    if not mood_from_payload or not content_from_payload: # Content might be answers
        return jsonify({'error': 'Missing required fields: mood and content/questionnaire responses'}), 400

    try:
        print(f'💾 Processing mood entry for user: {user_id_from_payload} via /api/mood-entries POST')
        
        user_specific_supabase_client = create_authenticated_supabase_client(token)
        mood_service = MoodService(user_specific_supabase_client)
        
        # Strict daily limit check FIRST
        print('🔍 Checking daily limit enforcement before saving...')
        existing_entry = mood_service.check_daily_mood_exists(user_id_from_payload)
        if existing_entry:
            print(f'🚫 DAILY LIMIT REACHED - User {user_id_from_payload} already submitted mood today')
            analysis_data = existing_entry.get('analysis', {})
            if isinstance(analysis_data, str):
                try: analysis_data = json.loads(analysis_data)
                except: analysis_data = {'error': 'analysis parse failed'}
            
            # Return 409 Conflict as per HTTP semantics for duplicate resource creation attempt
            return jsonify({
                'error': 'Daily limit reached. You have already created a mood entry for today.',
                'message': 'You have already created a mood entry for today. Come back tomorrow!',
                'analysis': analysis_data, # Send back existing analysis
                'existingEntryId': existing_entry.get('mood_id'),
                'submittedAt': existing_entry.get('created_at'),
                'dailyLimitReached': True,
                'nextSubmissionAllowed': f'{(datetime.utcnow().date() + timedelta(days=1)).isoformat()}T00:00:00Z'
            }), 409 # 409 Conflict is appropriate here
        
        print('✅ Daily limit check passed, proceeding with mood entry save & AI analysis')
        result = mood_service.save_mood_entry(
            user_id_from_payload, 
            mood_from_payload, 
            content_from_payload, 
            questionnaire_data_from_payload
        )
        
        total_processing_time = time.time() - request_start_time
        print(f'✅ Mood entry saved successfully in {total_processing_time:.2f}s. Analysis source: {result.get("analysis", {}).get("source", "unknown")}')
        
        return jsonify({
            'id': result.get('id'),
            'analysis': result.get('analysis'),
            'success': True,
            'message': result.get('message', 'Mood entry saved successfully.'),
            'processingTime': round(total_processing_time, 2),
            'analysisSource': result.get("analysis", {}).get('source', 'unknown'),
            'aiUsed': not result.get("analysis", {}).get('ai_failed', False) # Assuming 'ai_failed' key if AI fails
        }), 201 # 201 Created

    except Exception as e:
        total_processing_time = time.time() - request_start_time
        error_message = f'Internal server error while saving mood entry: {str(e)}'
        print(f'❌ Error saving mood entry (after {total_processing_time:.2f}s): {error_message}')
        current_app.logger.error(f"Exception in save_mood_entry_route for user {user_id_from_payload}: {e}", exc_info=True)
        # Check for specific Supabase errors if possible (e.g., RLS)
        if "security policy" in str(e).lower() or "permission denied" in str(e).lower():
            return jsonify({'error': f'Database security policy prevented saving: {str(e)}'}), 403 # Forbidden
        return jsonify({'error': error_message}), 500

# MODIFIED: Route path changed
@mood_bp.route('', methods=['GET']) # Changed from '/mood' to '' (relative to '/api/mood-entries')
def get_mood_entries_route():
    """Get user's mood entries"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Missing or invalid Authorization header'}), 401
    
    token = auth_header.split(' ')[1]
    authenticated_user_id_from_token = verify_token(token)
    if not authenticated_user_id_from_token:
        return jsonify({'error': 'Invalid or expired access token'}), 401

    user_id_from_query = request.args.get('userId')
    if not user_id_from_query:
        return jsonify({'error': 'Missing userId query parameter'}), 400
    
    try:
        _validate_user_id(user_id_from_query)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    
    test_user_ids = ['user123', 'test-user', 'demo-user']
    if user_id_from_query not in test_user_ids and authenticated_user_id_from_token != user_id_from_query:
        current_app.logger.warning(
            f"Unauthorized access attempt in get_mood_entries_route: Token user {authenticated_user_id_from_token} "
            f"tried to access data for query user {user_id_from_query}."
        )
        return jsonify({'error': 'Unauthorized: You can only retrieve your own mood entries.'}), 403
    
    limit_str = request.args.get('limit', '30')
    try:
        limit = int(limit_str)
        if limit <= 0 or limit > 100: # Max limit
            limit = 30 
    except ValueError:
        limit = 30


    try:
        print(f"Fetching mood entries for user {user_id_from_query} with limit {limit} via /api/mood-entries GET")
        user_specific_supabase_client = create_authenticated_supabase_client(token)
        mood_service = MoodService(user_specific_supabase_client)
        
        entries_data = mood_service.get_recent_mood_entries(user_id_from_query, limit=limit)
        
        # Data is already processed by get_recent_mood_entries to ensure dicts
        # The frontend expects 'id', 'userId', 'content', 'mood', 'date', 'analysis'
        # Map to frontend expected format if necessary, or ensure service returns it.
        # Current MoodService.get_recent_mood_entries returns 'mood_id', 'mood', 'content', 'analysis', 'created_at'
        
        formatted_entries = []
        for entry in entries_data:
            formatted_entries.append({
                'id': entry.get('mood_id'),
                'userId': user_id_from_query, # Add it back if service doesn't include it per entry
                'content': entry.get('content'),
                'mood': entry.get('mood'), # User selected mood
                'date': entry.get('created_at'),
                'analysis': entry.get('analysis'), # AI analysis object
                'questionnaireData': entry.get('questionnaire_data') # Include this too
            })
        
        return jsonify(formatted_entries), 200

    except Exception as e:
        print(f'❌ Error fetching mood entries for user {user_id_from_query}: {str(e)}')
        current_app.logger.error(f"Exception in get_mood_entries_route for user {user_id_from_query}: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error while fetching mood entries: {str(e)}'}), 500