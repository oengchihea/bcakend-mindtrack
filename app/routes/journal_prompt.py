import os
import requests
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timezone

journal_prompt_bp = Blueprint('journal_prompt_bp', __name__)

# The URL for the dedicated AI service (Next.js backend)
AI_SERVICE_URL = "https://ai-mindtrack.vercel.app/api/journal-prompt/generate"

@journal_prompt_bp.route('/journal-prompt/generate', methods=['POST'])
def generate_journal_prompts():
    """
    This function acts as a proxy to the dedicated AI service.
    It forwards the request from the app to the Next.js AI backend
    to get dynamically generated journal prompts.
    """
    current_app.logger.info(f"Proxying request to AI service for journal prompts at {datetime.now(timezone.utc).isoformat()}")

    # Get the original request data from the Flutter app
    incoming_data = request.get_json()
    if not incoming_data:
        current_app.logger.warning("No JSON data received for journal prompt generation.")
        return jsonify({"error": "No data provided"}), 400

    # Get the user's auth token to pass along to the AI service if needed
    auth_header = request.headers.get('Authorization')

    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'MindTrack-Flask-Proxy/1.0'
    }
    if auth_header:
        headers['Authorization'] = auth_header

    try:
        # Forward the request to the AI service
        current_app.logger.info(f"Forwarding request to: {AI_SERVICE_URL} with data: {incoming_data}")
        ai_response = requests.post(
            AI_SERVICE_URL,
            json=incoming_data,
            headers=headers,
            timeout=40  # 40-second timeout for the AI service
        )

        # This will raise an exception for 4xx or 5xx status codes
        ai_response.raise_for_status()

        # Get the JSON response from the AI service
        ai_data = ai_response.json()
        current_app.logger.info("Successfully received response from AI service.")

        # Return the AI service's response directly to the Flutter app
        return jsonify(ai_data), ai_response.status_code

    except requests.exceptions.Timeout:
        current_app.logger.error("Request to AI service timed out.")
        return jsonify({"error": "The request to the AI service timed out."}), 504
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error connecting to AI service: {e}")
        error_body = e.response.json() if e.response and e.response.text else {"error": str(e)}
        status_code = e.response.status_code if e.response else 502
        return jsonify({"error": "Failed to connect to the AI service.", "details": error_body}), status_code
    except Exception as e:
        current_app.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500