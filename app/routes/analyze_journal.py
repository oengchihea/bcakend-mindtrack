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
        
        if positive_count > negative_count:
            sentiment = "positive"
            score = min(8, 5 + positive_count)
        elif negative_count > positive_count:
            sentiment = "negative" 
            score = max(2, 5 - negative_count)
        else:
            sentiment = "neutral"
            score = 5
            
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
            "message": "Analysis generated using fallback method (Gemini AI unavailable)"
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
Analyze the following journal entry for sentiment and emotional well-being:
- Content: {content or 'No content provided'}
- Questionnaire Data: {json.dumps(questionnaire_data or {})}
- User ID: {user_id}

Return a JSON object with:
- sentiment: (e.g., "positive", "neutral", "negative")
- score: (integer between 0 and 10, reflecting emotional well-being)
- themes: (array of strings, e.g., ["stress", "gratitude"], must be non-empty)
- insights: (brief string summarizing the journal's emotional content)
- suggestions: (array of three strings with tailored suggestions to improve or maintain well-being)
- emoji: (string with a relevant emoji)

Example:
{{
  "sentiment": "positive",
  "score": 8,
  "themes": ["stress", "gratitude"],
  "insights": "Your journal reflects a positive mood with strong themes of gratitude.",
  "suggestions": [
    "Continue noting things you're grateful for to maintain positivity.",
    "Share your positive mood with others through kind acts.",
    "Reflect on what made today joyful to replicate it."
  ],
  "emoji": "😊"
}}

Ensure 'score' is an integer between 0 and 10, 'themes' is non-empty, and 'suggestions' contains exactly three items.
"""

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
            except json.JSONDecodeError as e:
                current_app.logger.error(f"Failed to parse Gemini JSON response: {json_string}, error: {e} at {datetime.now(timezone.utc).isoformat()}")
                return {
                    "error": f"Failed to parse Gemini response: {str(e)}",
                    "sentiment": "neutral",
                    "score": 5,
                    "themes": ["unknown"],
                    "insights": "Analysis failed, default values applied.",
                    "suggestions": ["Try journaling again later.", "Reflect on your day.", "Practice self-care."],
                    "emoji": "😐"
                }
        except Exception as api_error:
            # Handle various Gemini API errors more broadly since exceptions module might not be available
            error_str = str(api_error).lower()
            if "quota" in error_str or "resourceexhausted" in error_str:
                current_app.logger.warning(f"Quota exceeded error: {api_error} at {datetime.now(timezone.utc).isoformat()}, attempt {attempt + 1}/{max_retries}")
                if attempt == max_retries - 1:
                    return {
                        "error": f"Failed to analyze journal with Gemini: {api_error}. You have exceeded the free tier quota (50 requests/day). Wait until 07:00 +07 on June 24, 2025, for reset or upgrade your plan. See https://ai.google.dev/gemini-api/docs/rate-limits for details.",
                        "sentiment": "neutral",
                        "score": 5,
                        "themes": ["unknown"],
                        "insights": "Analysis failed due to quota limit.",
                        "suggestions": ["Wait for quota reset.", "Consider a paid plan.", "Check usage at https://ai.google.dev/gemini-api/docs/rate-limits."],
                        "emoji": "😐"
                    }
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
                # Handle as general exception and break out of retry loop
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
    return {
        "error": "Max retries reached for Gemini analysis",
        "sentiment": "neutral",
        "score": 5,
        "themes": ["unknown"],
        "insights": "Analysis failed after max retries, please try again later.",
        "suggestions": ["Try again later.", "Check your internet connection.", "Contact support if needed."],
        "emoji": "😐"
    }

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
            "suggestions": suggestions
        }
    except Exception as e:
        current_app.logger.error(f"Error in analyze_weekly_insights: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return {
            "error": f"Failed to analyze weekly insights: {str(e)}",
            "average_score": 5,
            "dominant_sentiment": "neutral",
            "themes": [],
            "insight": "Weekly analysis failed, default values applied.",
            "suggestions": []
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
            "suggestions": suggestions
        }
    except Exception as e:
        current_app.logger.error(f"Error in analyze_monthly_insights: {e} at {datetime.now(timezone.utc).isoformat()}", exc_info=True)
        return {
            "error": f"Failed to analyze monthly insights: {str(e)}",
            "average_score": 5,
            "dominant_sentiment": "neutral",
            "themes": [],
            "insight": "Monthly analysis failed, default values applied.",
            "suggestions": []
        }

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
        for attempt in range(max_retries):
            try:
                response = supabase.table('journalEntry').select('*').eq('user_id', user_id).gte('created_at', f"{journal_date} 00:00:00+07").lte('created_at', f"{journal_date} 23:59:59+07").execute()
                break
            except httpx.ReadError as e:
                current_app.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed due to ReadError: {e} at {datetime.now(timezone.utc).isoformat()}")
                if attempt == max_retries - 1:
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
        else:
            raise Exception("Max retries reached for Supabase query")
        
        if not response.data:
            current_app.logger.info(f"No journal entry found for user {user_id} on {journal_date} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "No journal entry found for the specified date"}), 404
        
        # Process and re-analyze all entries for the date
        results = []
        for journal_entry in response.data:
            logging.info(f"Journal entry data: {journal_entry}")  # Log the full entry to inspect structure
            content = journal_entry.get('entry_text')
            questionnaire_data = journal_entry.get('questionnaire', {})
            
            current_app.logger.info(f"Re-analyzing journal entry for user {user_id} on {journal_date} with journal_id {journal_entry['journal_id']} at {datetime.now(timezone.utc).isoformat()}")
            result = analyze_with_gemini(content, questionnaire_data, user_id, max_retries=3)
            if "error" in result:
                current_app.logger.error(f"Analysis failed with error: {result['error']} at {datetime.now(timezone.utc).isoformat()}")
                return jsonify(result), 500

            # Save or update analysis and score
            entry_id = journal_entry.get('journal_id')
            if not entry_id:
                current_app.logger.error(f"No journal_id found in journal entry: {journal_entry} at {datetime.now(timezone.utc).isoformat()}")
                return jsonify({"error": "Internal server error: No journal_id for update"}), 500
            supabase.table('journalEntry').update({
                'analysis': result,
                'score': result['score']
            }).eq('journal_id', entry_id).execute()
            results.append(result)

        if not results:
            current_app.logger.error(f"No valid analysis results for user {user_id} on {journal_date} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "No valid analysis results"}), 500
        
        # Return all results in a single response
        current_app.logger.info(f"Successfully re-analyzed {len(results)} journal entries for user {user_id} on {journal_date} at {datetime.now(timezone.utc).isoformat()}")
        return jsonify({"results": results}), 200
    
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
        # Fetch daily analyses for the week
        response = supabase.table('journalEntry').select('analysis').eq('user_id', user_id).gte('created_at', f"{start_date} 00:00:00+07").lte('created_at', f"{end_date} 23:59:59+07").execute()
        if not response.data:
            current_app.logger.info(f"No journal entries found for user {user_id} in week starting {start_date} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "No journal entries found for the specified week"}), 404
        
        insights = [entry['analysis'] for entry in response.data if entry.get('analysis')]
        if not insights:
            current_app.logger.warning(f"No valid analysis data found for user {user_id} in week starting {start_date} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "No valid analysis data available for the week"}), 400
        
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
        # Fetch daily analyses for the month
        response = supabase.table('journalEntry').select('analysis').eq('user_id', user_id).gte('created_at', f"{start_date} 00:00:00+07").lte('created_at', f"{end_date} 23:59:59+07").execute()
        if not response.data:
            current_app.logger.info(f"No journal entries found for user {user_id} in month {month_str} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "No journal entries found for the specified month"}), 404
        
        insights = [entry['analysis'] for entry in response.data if entry.get('analysis')]
        if not insights:
            current_app.logger.warning(f"No valid analysis data found for user {user_id} in month {month_str} at {datetime.now(timezone.utc).isoformat()}")
            return jsonify({"error": "No valid analysis data available for the month"}), 400
        
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