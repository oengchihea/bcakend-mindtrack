import os
import json
import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, current_app, g
from supabase import create_client, Client
from postgrest import APIError
from .auth import auth_required
import httpx
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY_V2") or os.getenv("GEMINI_API_KEY_V1") or os.getenv("GEMINI_API_KEY")

# Try to import google.generativeai, but make it optional
try:
    import google.generativeai as genai
    from google.api_core import exceptions
    GEMINI_IMPORT_AVAILABLE = True
except ImportError:
    GEMINI_IMPORT_AVAILABLE = False
    genai = None
    exceptions = None
    logging.warning("google-generativeai not installed, using fallback analysis only")

# Try to configure Gemini AI, but make it optional
try:
    if GEMINI_API_KEY and GEMINI_IMPORT_AVAILABLE:
        genai.configure(api_key=GEMINI_API_KEY)
        GEMINI_AVAILABLE = True
    else:
        GEMINI_AVAILABLE = False
        logging.warning("GEMINI_API_KEY not available or google-generativeai not installed, using fallback analysis")
except Exception as e:
    logging.error(f"Failed to configure Gemini AI: {e}")
    GEMINI_AVAILABLE = False

analyze_bp = Blueprint('analyze_bp', __name__)
MODEL_NAME = "gemini-1.5-flash-latest"

def generate_fallback_analysis(content, questionnaire_data, user_id):
    """Generate fallback analysis when Gemini AI is not available"""
    try:
        # Simple keyword-based sentiment analysis
        content_lower = (content or "").lower()
        positive_words = ["happy", "good", "great", "excellent", "amazing", "wonderful", "grateful", "thankful", "joy", "love", "excited", "proud"]
        negative_words = ["sad", "bad", "terrible", "awful", "angry", "frustrated", "worried", "anxious", "stressed", "upset", "disappointed"]
        
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        # Incorporate questionnaire data for sentiment
        feeling_score = 5
        if questionnaire_data and 'feeling_scale' in questionnaire_data:
            try:
                feeling_score = int(questionnaire_data['feeling_scale'])
            except (ValueError, TypeError):
                pass
        
        if positive_count > negative_count or feeling_score >= 7:
            sentiment = "positive"
            score = min(8, 5 + positive_count + (feeling_score - 5))
        elif negative_count > positive_count or feeling_score <= 4:
            sentiment = "negative"
            score = max(2, 5 - negative_count - (5 - feeling_score))
        else:
            sentiment = "neutral"
            score = feeling_score
            
        # Extract themes based on content
        themes = []
        if any(word in content_lower for word in ["work", "job", "office", "meeting"]):
            themes.append("work")
        if any(word in content_lower for word in ["stress", "anxious", "worried", "pressure"]):
            themes.append("stress")
        if any(word in content_lower for word in ["grateful", "thankful", "appreciate", "blessing"]):
            themes.append("gratitude")
        if any(word in content_lower for word in ["family", "friend", "relationship", "love"]):
            themes.append("relationships")
        if any(word in content_lower for word in ["tired", "exhausted", "sleep", "energy"]):
            themes.append("energy")
            
        if not themes:
            themes = ["reflection"]
            
        # Generate appropriate insights and suggestions
        if sentiment == "positive":
            insights = "Your journal entry reflects a positive mindset and emotional well-being."
            suggestions = [
                "Continue practicing gratitude to maintain your positive outlook.",
                "Share your positive energy with others around you.",
                "Reflect on what specifically contributed to these good feelings."
            ]
            emoji = "😊"
        elif sentiment == "negative":
            insights = "Your journal entry indicates some challenges or difficult emotions."
            suggestions = [
                "Consider talking to someone you trust about these feelings.",
                "Practice self-care activities that usually help you feel better.",
                "Remember that difficult emotions are temporary and will pass."
            ]
            emoji = "😔"
        else:
            insights = "Your journal entry shows a balanced emotional state."
            suggestions = [
                "Take time to reflect on what brings you joy and fulfillment.",
                "Consider setting small goals to add more positive experiences to your day.",
                "Practice mindfulness to stay present and aware of your emotions."
            ]
            emoji = "😐"
            
        return {
            "sentiment": sentiment,
            "score": score,
            "themes": themes,
            "insights": insights,
            "suggestions": suggestions,
            "emoji": emoji,
            "fallback": True,
            "message": "Analysis generated using fallback method due to AI service unavailability"
        }
        
    except Exception as e:
        logging.error(f"Error in fallback analysis: {e}")
        return {
            "sentiment": "neutral",
            "score": 5,
            "themes": ["unknown"],
            "insights": "Fallback analysis failed, default values applied.",
            "suggestions": ["Try journaling again later.", "Reflect on your day.", "Practice self-care."],
            "emoji": "😐",
            "fallback": True,
            "error": f"Fallback analysis error: {str(e)}"
        }

def analyze_with_gemini(content, questionnaire_data, user_id, max_retries=3):
    # Check if Gemini is available
    if not GEMINI_AVAILABLE:
        current_app.logger.warning(f"Gemini AI not available for user {user_id}, using fallback analysis")
        return generate_fallback_analysis(content, questionnaire_data, user_id)
    
    attempt = 0
    while attempt < max_retries:
        try:
            current_app.logger.info(f"Analyzing journal with Gemini for user {user_id}: {content[:50]}... at {datetime.now(timezone.utc).isoformat()}, attempt {attempt + 1}/{max_retries}")
            
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

            prompt = f"""
You are an expert emotional well-being analyst. Carefully analyze this journal entry and provide an accurate assessment:

JOURNAL CONTENT: "{content or 'No content provided'}"
QUESTIONNAIRE DATA: {json.dumps(questionnaire_data or {})}

ANALYSIS INSTRUCTIONS:
1. SENTIMENT: Determine if the overall emotional tone is "positive", "negative", or "neutral"
2. SCORE: Rate emotional well-being from 0-10 where:
   - 0-2: Severe distress (depression, grief, trauma, suicidal thoughts)
   - 3-4: Significant emotional difficulties (very sad, anxious, angry, overwhelmed)
   - 5-6: Mild emotional challenges or neutral state (slight sadness, minor stress, okay)
   - 7-8: Good emotional state (happy, content, grateful, motivated)
   - 9-10: Excellent emotional well-being (joy, euphoria, deep peace, amazing day)

3. THEMES: Identify specific emotional themes (e.g., "grief", "anxiety", "gratitude", "loneliness", "excitement", "stress", "love", "anger")

4. INSIGHTS: Provide empathetic understanding of their emotional state

5. SUGGESTIONS: Give 3 specific, actionable suggestions based on their emotional state

IMPORTANT SCORING GUIDELINES:
- If they mention sadness, loss, grief, depression: Score 2-4
- If they mention anxiety, worry, stress: Score 3-5  
- If they mention anger, frustration: Score 3-5
- If they mention neutral/okay feelings: Score 5-6
- If they mention happiness, gratitude, excitement: Score 7-9
- If they mention extreme joy, amazing day, love: Score 9-10

Return ONLY this JSON format:
{{
  "sentiment": "negative|neutral|positive",
  "score": integer_0_to_10,
  "themes": ["theme1", "theme2"],
  "insights": "Your understanding of their emotional state",
  "suggestions": [
    "Specific suggestion 1",
    "Specific suggestion 2", 
    "Specific suggestion 3"
  ],
  "emoji": "relevant_emoji"
}}
Ensure the response is valid JSON with no additional text or errors outside the JSON structure."""

            response = model.generate_content(prompt)
            json_string = response.text.strip()

            # Clean and parse JSON, handling potential malformed responses
            json_string = json_string.replace("```json\n", "").replace("```", "").strip()
            if not json_string.startswith("{"):
                json_string = "{" + json_string + "}"
            
            # Attempt to parse, removing trailing errors if present
            try:
                result = json.loads(json_string)
            except json.JSONDecodeError as e:
                current_app.logger.warning(f"Initial JSON parse failed: {e}, attempting to clean response")
                # Try to extract valid JSON by removing trailing error text
                json_start = json_string.find("{")
                json_end = json_string.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    cleaned_json = json_string[json_start:json_end]
                    try:
                        result = json.loads(cleaned_json)
                    except json.JSONDecodeError as e2:
                        current_app.logger.error(f"Failed to parse cleaned JSON response: {e2} at {datetime.now(timezone.utc).isoformat()}")
                        return {
                            "error": f"Failed to parse Gemini response: {str(e2)}",
                            "sentiment": "neutral",
                            "score": 5,
                            "themes": ["unknown"],
                            "insights": "Analysis failed, default values applied.",
                            "suggestions": ["Try journaling again later.", "Reflect on your day.", "Practice self-care."],
                            "emoji": "😐"
                        }
                else:
                    current_app.logger.error(f"Failed to parse Gemini JSON response: {e} at {datetime.now(timezone.utc).isoformat()}")
                    return {
                        "error": f"Failed to parse Gemini response: {str(e)}",
                        "sentiment": "neutral",
                        "score": 5,
                        "themes": ["unknown"],
                        "insights": "Analysis failed, default values applied.",
                        "suggestions": ["Try journaling again later.", "Reflect on your day.", "Practice self-care."],
                        "emoji": "😐"
                    }
            
            # Validate response
            if (
                isinstance(result.get("sentiment"), str) and
                isinstance(result.get("score"), int) and 0 <= result["score"] <= 10 and
                isinstance(result.get("themes"), list) and len(result["themes"]) > 0 and
                isinstance(result.get("insights"), str) and
                isinstance(result.get("suggestions"), list) and len(result["suggestions"]) == 3 and
                isinstance(result.get("emoji"), str)
            ):
                current_app.logger.info(f"Gemini analysis successful: {json.dumps(result)[:100]}... at {datetime.now(timezone.utc).isoformat()}")
                return result
            else:
                current_app.logger.error(f"Invalid Gemini response format: {json_string} at {datetime.now(timezone.utc).isoformat()}")
                return {
                    "error": "Invalid response format from Gemini",
                    "sentiment": "neutral",
                    "score": 5,
                    "themes": ["unknown"],
                    "insights": "Analysis failed, default values applied.",
                    "suggestions": ["Try journaling again later.", "Reflect on your day.", "Practice self-care."],
                    "emoji": "😐"
                }
        except Exception as api_error:
            # Handle various Gemini API errors more broadly
            error_str = str(api_error).lower()
            if "quota" in error_str or "resourceexhausted" in error_str:
                current_app.logger.warning(f"Quota exceeded error: {api_error} at {datetime.now(timezone.utc).isoformat()}, attempt {attempt + 1}/{max_retries}")
                if attempt == max_retries - 1:
                    current_app.logger.warning(f"Gemini quota exceeded, using fallback analysis for user {user_id}")
                    return generate_fallback_analysis(content, questionnaire_data, user_id)
                retry_delay = getattr(api_error, 'retry_delay', None)
                wait_time = retry_delay.seconds if retry_delay and hasattr(retry_delay, 'seconds') else 2 ** attempt
                current_app.logger.info(f"Retrying after {wait_time} seconds due to quota limit at {datetime.now(timezone.utc).isoformat()}")
                time.sleep(wait_time)
                attempt += 1
                continue
            elif "invalid" in error_str and ("key" in error_str or "argument" in error_str):
                current_app.logger.error(f"API key error: {api_error} at {datetime.now(timezone.utc).isoformat()}")
                return {
                    "error": f"Failed to analyze journal with Gemini: {api_error}. The API key is invalid or expired. Renew it at https://aistudio.google.com/app/apikey.",
                    "sentiment": "neutral",
                    "score": 5,
                    "themes": ["unknown"],
                    "insights": "Analysis failed due to an invalid API key.",
                    "suggestions": ["Renew your API key.", "Update GEMINI_API_KEY in .env.", "Retry after updating."],
                    "emoji": "😐"
                }
            else:
                current_app.logger.error(f"Error in analyze_with_gemini: {api_error} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
                return {
                    "error": f"Failed to analyze journal with Gemini: {str(api_error)}",
                    "sentiment": "neutral",
                    "score": 5,
                    "themes": ["unknown"],
                    "insights": "Analysis failed, default values applied.",
                    "suggestions": ["Try journaling again later.", "Reflect on your day.", "Practice self-care."],
                    "emoji": "😐"
                }
    return generate_fallback_analysis(content, questionnaire_data, user_id)

def analyze_weekly_insights(insights, user_id):
    try:
        current_app.logger.info(f"Analyzing weekly insights for user {user_id} from stored daily data at {datetime.now(timezone.utc).isoformat()}")
        
        # Use stored daily analysis results
        if not insights or not all(isinstance(entry, dict) and "score" in entry for entry in insights):
            raise ValueError("Invalid or empty insights data")

        # Calculate average score and dominant sentiment
        scores = [entry["score"] for entry in insights]
        sentiments = [entry["sentiment"] for entry in insights]
        avg_score = sum(scores) / len(scores) if scores else 5
        
        # Aggregate daily scores by date for graph
        daily_scores = {}
        for entry in insights:
            date = entry.get("date")
            if date:
                if date not in daily_scores:
                    daily_scores[date] = []
                daily_scores[date].append(entry["score"])
        
        # Compute average score per date
        daily_avg_scores = {
            date: sum(scores) / len(scores) if scores else 5
            for date, scores in daily_scores.items()
        }
        
        # Determine dominant sentiment
        sentiment_counts = {
            "positive": sentiments.count("positive"),
            "negative": sentiments.count("negative"),
            "neutral": sentiments.count("neutral")
        }
        dominant_sentiment = max(sentiment_counts.items(), key=lambda x: x[1])[0]
        
        # Aggregate themes
        all_themes = []
        for entry in insights:
            all_themes.extend(entry.get("themes", []))
        unique_themes = list(set(all_themes)) if all_themes else ["unknown"]
        
        # Generate weekly insight
        insight = f"Your week showed a {dominant_sentiment} overall mood with an average score of {avg_score:.1f}."
        if "stress" in unique_themes:
            insight += " Stress was a recurring theme."
        if "gratitude" in unique_themes:
            insight += " Expressions of gratitude were noted."

        # Generate weekly suggestions
        suggestions = []
        if dominant_sentiment == "negative":
            suggestions.extend([
                "Establish a consistent self-care routine to manage stress.",
                "Track positive moments daily to shift your focus.",
                "Explore stress-reduction techniques like deep breathing."
            ])
        elif dominant_sentiment == "positive":
            suggestions.extend([
                "Maintain your positive routines and share your insights.",
                "Set new personal goals to keep your momentum.",
                "Continue journaling to sustain this positive trend."
            ])
        else:
            suggestions.extend([
                "Experiment with new activities to boost engagement.",
                "Reflect on what brings you joy and incorporate it more.",
                "Set aside time for self-reflection to understand your mood."
            ])
        
        return {
            "average_score": avg_score,
            "dominant_sentiment": dominant_sentiment,
            "themes": unique_themes,
            "insight": insight,
            "suggestions": suggestions,
            "daily_avg_scores": daily_avg_scores
        }
    except Exception as e:
        current_app.logger.error(f"Error in analyze_weekly_insights: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return {
            "error": f"Failed to analyze weekly insights: {str(e)}",
            "average_score": 5,
            "dominant_sentiment": "neutral",
            "themes": [],
            "insight": "Weekly analysis failed, default values applied.",
            "suggestions": [],
            "daily_avg_scores": {}
        }

def analyze_monthly_insights(insights, user_id):
    try:
        current_app.logger.info(f"Analyzing monthly insights for user {user_id} from stored daily data at {datetime.now(timezone.utc).isoformat()}")
        
        # Use stored daily analysis results
        if not insights or not all(isinstance(entry, dict) and "score" in entry for entry in insights):
            raise ValueError("Invalid or empty insights data")

        # Calculate average score and dominant sentiment
        scores = [entry["score"] for entry in insights]
        sentiments = [entry["sentiment"] for entry in insights]
        avg_score = sum(scores) / len(scores) if scores else 5
        
        # Aggregate daily scores by date for graph
        daily_scores = {}
        for entry in insights:
            date = entry.get("date")
            if date:
                if date not in daily_scores:
                    daily_scores[date] = []
                daily_scores[date].append(entry["score"])
        
        # Compute average score per date
        daily_avg_scores = {
            date: sum(scores) / len(scores) if scores else 5
            for date, scores in daily_scores.items()
        }
        
        # Determine dominant sentiment
        sentiment_counts = {
            "positive": sentiments.count("positive"),
            "negative": sentiments.count("negative"),
            "neutral": sentiments.count("neutral")
        }
        dominant_sentiment = max(sentiment_counts.items(), key=lambda x: x[1])[0]
        
        # Aggregate themes
        all_themes = []
        for entry in insights:
            all_themes.extend(entry.get("themes", []))
        unique_themes = list(set(all_themes)) if all_themes else ["unknown"]
        
        # Generate monthly insight
        insight = f"Your month showed a {dominant_sentiment} overall mood with an average score of {avg_score:.1f}."
        if "stress" in unique_themes:
            insight += " Stress was a recurring theme."
        if "gratitude" in unique_themes:
            insight += " Expressions of gratitude were noted."

        # Generate monthly suggestions
        suggestions = []
        if dominant_sentiment == "negative":
            suggestions.extend([
                "Establish a long-term self-care plan to manage stress.",
                "Reflect on patterns to shift your focus positively.",
                "Consider professional support for ongoing stress."
            ])
        elif dominant_sentiment == "positive":
            suggestions.extend([
                "Sustain your positive habits over the month.",
                "Set monthly goals to build on your momentum.",
                "Share your positivity to inspire others."
            ])
        else:
            suggestions.extend([
                "Explore new monthly activities to boost engagement.",
                "Reflect on monthly joys to enhance your mood.",
                "Schedule regular self-reflection sessions."
            ])
        
        return {
            "average_score": avg_score,
            "dominant_sentiment": dominant_sentiment,
            "themes": unique_themes,
            "insight": insight,
            "suggestions": suggestions,
            "daily_avg_scores": daily_avg_scores
        }
    except Exception as e:
        current_app.logger.error(f"Error in analyze_monthly_insights: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return {
            "error": f"Failed to analyze monthly insights: {str(e)}",
            "average_score": 5,
            "dominant_sentiment": "neutral",
            "themes": [],
            "insight": "Monthly analysis failed, default values applied.",
            "suggestions": [],
            "daily_avg_scores": {}
        }

@analyze_bp.route('/analyze-journal', methods=['POST'])
@auth_required
def analyze_journal():
    """
    Analyze journal content in real-time without saving to database.
    This is used by the frontend during journal submission.
    """
    current_app.logger.info(f"Route /api/analyze-journal hit with method POST at {datetime.now(timezone.utc).isoformat()}")
    
    user_id = g.user.id
    data = request.get_json()
    
    if not data:
        current_app.logger.warning(f"No data provided in request at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({
            "error": "Request body is required",
            "fallback": True,
            "sentiment": "neutral",
            "score": 5,
            "themes": ["unknown"],
            "insights": "No content provided for analysis.",
            "suggestions": [
                "Try writing about your current feelings",
                "Share what's on your mind",
                "Reflect on your day"
            ],
            "emoji": "😐"
        }), 400
    
    content = data.get('content', '')
    questionnaire_data = data.get('questionnaireData', {})
    
    if not content:
        current_app.logger.warning(f"No content provided for analysis at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({
            "error": "Content is required for analysis",
            "fallback": True,
            "sentiment": "neutral",
            "score": 5,
            "themes": ["unknown"],
            "insights": "No journal content provided.",
            "suggestions": [
                "Start by writing about your day",
                "Share what you're feeling right now",
                "Describe a moment that stood out"
            ],
            "emoji": "😐"
        }), 400
    
    try:
        current_app.logger.info(f"Analyzing journal content for user {user_id} at {datetime.now(timezone.utc).isoformat()}")
        
        # First try with Gemini
        result = analyze_with_gemini(content, questionnaire_data, user_id, max_retries=2)
        
        # Check for quota exceeded error
        if "error" in result and ("quota" in result["error"].lower() or "429" in result["error"]):
            current_app.logger.warning(f"Gemini quota exceeded, using fallback analysis for user {user_id}")
            
            # Generate fallback analysis
            fallback_result = generate_fallback_analysis(content, questionnaire_data, user_id)
            
            # Add quota warning to the response
            fallback_result.update({
                "quota_exceeded": True,
                "quota_message": "AI analysis temporarily unavailable due to quota limits. Using simplified analysis.",
                "retry_after": "Please try again in a few minutes."
            })
            
            return jsonify(fallback_result), 200
        
        # Check for other errors
        elif "error" in result:
            current_app.logger.error(f"Analysis failed with error: {result['error']} at {datetime.now(timezone.utc).isoformat()}")
            
            # Generate fallback analysis
            fallback_result = generate_fallback_analysis(content, questionnaire_data, user_id)
            fallback_result.update({
                "original_error": result["error"],
                "fallback_message": "Using simplified analysis due to temporary AI service disruption."
            })
            
            return jsonify(fallback_result), 200
        
        current_app.logger.info(f"Successfully analyzed journal content for user {user_id} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify(result), 200
    
    except Exception as e:
        current_app.logger.error(f"Error analyzing journal content: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        
        # Generate fallback analysis
        fallback_result = generate_fallback_analysis(content, questionnaire_data, user_id)
        fallback_result.update({
            "error": f"An unexpected error occurred: {str(e)}",
            "fallback_message": "Using simplified analysis due to technical difficulties."
        })
        
        return jsonify(fallback_result), 200

@analyze_bp.route('/analyze-journal-by-date', methods=['POST'])
@auth_required
def analyze_journal_by_date():
    current_app.logger.info(f"Route /api/analyze-journal-by-date hit with method POST at {datetime.now(timezone.utc).isoformat()}")
    logging.info(f"Current app supabase: {hasattr(current_app, 'supabase')} {current_app.supabase}")
    logging.info(f"Current app config SUPABASE_CLIENT: {current_app.config.get('SUPABASE_CLIENT')}")
    
    supabase = current_app.config.get('SUPABASE_CLIENT') or current_app.supabase
    if not supabase:
        current_app.logger.error(f"Supabase client not initialized at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Internal server error: Supabase client not available"}), 500
    
    user_id = g.user.id
    data = request.get_json()
    
    if not data or 'date' not in data:
        current_app.logger.warning(f"Missing 'date' field in request at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Missing required field: date"}), 400
    
    try:
        journal_date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    except ValueError:
        current_app.logger.warning(f"Invalid date format: {data['date']} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    
    try:
        max_retries = 3
        # Fetch journal entries for the date
        journal_response = None
        for attempt in range(max_retries):
            try:
                journal_response = supabase.table('journalEntry').select('*').eq('user_id', user_id).gte('created_at', f"{journal_date} 00:00:00+07").lte('created_at', f"{journal_date} 23:59:59+07").execute()
                break
            except httpx.ReadError as e:
                current_app.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed due to ReadError for journalEntry: {e} at {datetime.now(timezone.utc).isoformat()}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        else:
            raise Exception("Max retries reached for Supabase journalEntry query")
        
        if not journal_response.data:
            current_app.logger.info(f"No journal entry found for user {user_id} on {journal_date} at {datetime.now(timezone.utc).isoformat()}")
            
            # Provide default AI analysis encouraging journaling
            content = "No journal entry provided for this date."
            questionnaire_data = {}
            result = analyze_with_gemini(content, questionnaire_data, user_id, max_retries=3)
            if "error" in result:
                current_app.logger.error(f"Default analysis failed with error: {result['error']} at {datetime.now(timezone.utc).isoformat()}")
                return jsonify(result), 500
            
            result.update({
                "message": f"No journal entry found for {journal_date}. Please write a journal entry to receive personalized insights.",
                "redirect": "/journal/write",
                "average_score": result["score"]
            })
            return jsonify({"results": [result]}), 200
        
        # Always re-analyze all journal entries for the date
        results = []
        for journal_entry in journal_response.data:
            content = journal_entry.get('entry_text')
            questionnaire_data = journal_entry.get('questionnaire', {})
            
            current_app.logger.info(f"Analyzing journal entry for user {user_id} on {journal_date} with journal_id {journal_entry['journal_id']} at {datetime.now(timezone.utc).isoformat()}")
            result = analyze_with_gemini(content, questionnaire_data, user_id, max_retries=3)
            result["date"] = journal_date.isoformat()
            if "error" in result:
                current_app.logger.error(f"Analysis failed with error: {result['error']} at {datetime.now(timezone.utc).isoformat()}")
                return jsonify(result), 500
            
            # Update or insert analysis in dailyanalysis table
            try:
                # Delete existing analysis for this user and date to avoid duplicates
                supabase.table('dailyanalysis').delete().eq('user_id', user_id).eq('date', journal_date).execute()
                supabase.table('dailyanalysis').insert({
                    'user_id': user_id,
                    'date': journal_date.isoformat(),
                    'analysis': result
                }).execute()
            except APIError as e:
                if '42P01' not in str(e):
                    current_app.logger.error(f"Failed to save to dailyanalysis: {e} at {datetime.now(timezone.utc).isoformat()}")
            
            # Update journalEntry
            entry_id = journal_entry.get('journal_id')
            if not entry_id:
                current_app.logger.error(f"No journal_id found in journal entry: {journal_entry} at {datetime.now(timezone.utc).isoformat()}")
                return jsonify({"error": "Internal server error: No journal_id for update"}), 500
            supabase.table('journalEntry').update({
                'analysis': result,
                'score': result['score']
            }).eq('journal_id', entry_id).execute()
            
            results.append(result)
        
        # Calculate average score for the day
        scores = [result['score'] for result in results if 'score' in result]
        avg_score = sum(scores) / len(scores) if scores else 5
        
        current_app.logger.info(f"Successfully analyzed {len(results)} journal entries for user {user_id} on {journal_date} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({
            "results": results,
            "average_score": avg_score
        }), 200
    
    except APIError as e:
        current_app.logger.error(f"Supabase API error: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except httpx.ReadError as e:
        current_app.logger.error(f"Network error: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Network error: Unable to connect to Supabase: {str(e)}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error analyzing journal by date: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Failed to analyze journal entry: {str(e)}"}), 500

@analyze_bp.route('/analyze-weekly-insights', methods=['POST'])
@auth_required
def analyze_weekly_insights_endpoint():
    current_app.logger.info(f"Route /api/analyze-weekly-insights hit with method POST at {datetime.now(timezone.utc).isoformat()}")
    logging.info(f"Current app supabase: {hasattr(current_app, 'supabase')} {current_app.supabase}")
    logging.info(f"Current app config SUPABASE_CLIENT: {current_app.config.get('SUPABASE_CLIENT')}")
    
    supabase = current_app.config.get('SUPABASE_CLIENT') or current_app.supabase
    if not supabase:
        current_app.logger.error(f"Supabase client not initialized at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Internal server error: Supabase client not available"}), 500
    
    user_id = g.user.id
    data = request.get_json()
    
    if not data or 'start_date' not in data:
        current_app.logger.warning(f"Missing 'start_date' field in request at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Missing required field: start_date"}), 400
    
    try:
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = start_date + timedelta(days=6)
    except ValueError:
        current_app.logger.warning(f"Invalid date format: {data['start_date']} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    
    try:
        # Fetch daily analyses for the week from dailyanalysis table
        response = supabase.table('dailyanalysis').select('analysis, date').eq('user_id', user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
        if not response.data:
            current_app.logger.info(f"No analysis entries found for user {user_id} in week starting {start_date} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({
                "error": "No journal entries found for the specified week",
                "message": "Please write journal entries to receive weekly insights.",
                "redirect": "/journal/write"
            }), 404
        
        insights = [
            {**entry['analysis'], "date": entry['date']}
            for entry in response.data if entry.get('analysis')
        ]
        if not insights:
            current_app.logger.warning(f"No valid analysis data found for user {user_id} in week starting {start_date} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({
                "error": "No valid analysis data available for the week",
                "message": "Please write journal entries to receive weekly insights.",
                "redirect": "/journal/write"
            }), 400
        
        current_app.logger.info(f"Analyzing {len(insights)} daily analyses for user {user_id} for week starting {start_date} at {datetime.now(timezone.utc).isoformat()}")
        weekly_analysis = analyze_weekly_insights(insights, user_id)
        
        if "error" in weekly_analysis:
            current_app.logger.error(f"Weekly analysis failed with error: {weekly_analysis['error']} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify(weekly_analysis), 500
        
        current_app.logger.info(f"Successfully analyzed weekly insights for user {user_id} for week starting {start_date} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify(weekly_analysis), 200
    
    except APIError as e:
        current_app.logger.error(f"Supabase API error: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except httpx.ReadError as e:
        current_app.logger.error(f"Network error: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Network error: Unable to connect to Supabase: {str(e)}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error analyzing weekly insights: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Failed to analyze weekly insights: {str(e)}"}), 500

@analyze_bp.route('/analyze-monthly-insights', methods=['POST'])
@auth_required
def analyze_monthly_insights_endpoint():
    current_app.logger.info(f"Route /api/analyze-monthly-insights hit with method POST at {datetime.now(timezone.utc).isoformat()}")
    logging.info(f"Current app supabase: {hasattr(current_app, 'supabase')} {current_app.supabase}")
    logging.info(f"Current app config SUPABASE_CLIENT: {current_app.config.get('SUPABASE_CLIENT')}")
    
    supabase = current_app.config.get('SUPABASE_CLIENT') or current_app.supabase
    if not supabase:
        current_app.logger.error(f"Supabase client not initialized at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Internal server error: Supabase client not available"}), 500
    
    user_id = g.user.id
    data = request.get_json()
    
    if not data or 'month' not in data:
        current_app.logger.warning(f"Missing 'month' field in request at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Missing required field: month"}), 400
    
    try:
        # Parse month as YYYY-MM format and calculate start and end dates
        month_str = data['month']
        start_date = datetime.strptime(month_str + "-01", '%Y-%m-%d').date()
        end_date = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)  # Last day of month
    except ValueError:
        current_app.logger.warning(f"Invalid month format: {data['month']} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"error": "Invalid month format. Use YYYY-MM."}), 400
    
    try:
        # Fetch daily analyses for the month from dailyanalysis table
        response = supabase.table('dailyanalysis').select('analysis, date').eq('user_id', user_id).gte('date', start_date.isoformat()).lte('date', end_date.isoformat()).execute()
        if not response.data:
            current_app.logger.info(f"No analysis entries found for user {user_id} in month {month_str} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({
                "error": "No journal entries found for the specified month",
                "message": "Please write journal entries to receive monthly insights.",
                "redirect": "/journal/write"
            }), 404
        
        insights = [
            {**entry['analysis'], "date": entry['date']}
            for entry in response.data if entry.get('analysis')
        ]
        if not insights:
            current_app.logger.warning(f"No valid analysis data found for user {user_id} in month {month_str} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({
                "error": "No valid analysis data available for the month",
                "message": "Please write journal entries to receive monthly insights.",
                "redirect": "/journal/write"
            }), 400
        
        current_app.logger.info(f"Analyzing {len(insights)} daily analyses for user {user_id} for month {month_str} at {datetime.now(timezone.utc).isoformat()}")
        monthly_analysis = analyze_monthly_insights(insights, user_id)
        
        if "error" in monthly_analysis:
            current_app.logger.error(f"Monthly analysis failed with error: {monthly_analysis['error']} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify(monthly_analysis), 500
        
        current_app.logger.info(f"Successfully analyzed monthly insights for user {user_id} for month {month_str} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify(monthly_analysis), 200
    
    except APIError as e:
        current_app.logger.error(f"Supabase API error: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except httpx.ReadError as e:
        current_app.logger.error(f"Network error: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Network error: Unable to connect to Supabase: {str(e)}"}), 500
    except Exception as e:
        current_app.logger.error(f"Error analyzing monthly insights: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return jsonify({"error": f"Failed to analyze monthly insights: {str(e)}"}), 500