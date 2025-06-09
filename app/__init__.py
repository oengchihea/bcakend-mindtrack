import logging
import os
from flask import Flask, jsonify
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv

# Configure logging for Vercel
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

def create_app():
    logging.info("--- Starting Flask app creation ---")
    load_dotenv()
    app = Flask(__name__)

    # --- Environment Variable Check ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL')
    app.config['SUPABASE_KEY'] = os.environ.get('SUPABASE_KEY')

    logging.info(f"SUPABASE_URL Loaded: {'YES' if app.config['SUPABASE_URL'] else 'NO - CRITICAL'}")
    logging.info(f"SUPABASE_KEY Loaded: {'YES' if app.config['SUPABASE_KEY'] else 'NO - CRITICAL'}")
    
    if not all([app.config['SUPABASE_URL'], app.config['SUPABASE_KEY']]):
        logging.error("CRITICAL ERROR: Missing Supabase URL or Key in environment variables.")
        # For Vercel, it's better to let it fail and check logs than to raise an unhandled exception here
        # that might prevent other logs from showing. The check above will log the error.
        # Consider returning a specific error response or handling this more gracefully if needed.
        # For now, logging the error is the primary step.

    # --- Supabase Client Initialization ---
    try:
        if app.config['SUPABASE_URL'] and app.config['SUPABASE_KEY']:
            app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
            logging.info("Supabase client initialized successfully.")
        else:
            logging.error("Supabase client NOT initialized due to missing credentials.")
            app.supabase = None # Explicitly set to None
    except Exception as e:
        logging.error(f"CRITICAL ERROR: Failed to initialize Supabase client: {e}", exc_info=True)
        app.supabase = None # Explicitly set to None on error

    # --- CORS and Blueprint Registration ---
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    logging.info("CORS configured for /api/*.")

    try:
        # Register Journal Blueprint
        from .routes.journal import journal_bp
        app.register_blueprint(journal_bp)
        logging.info("Successfully registered 'journal_bp' blueprint.")

        # Register Mood Blueprint
        from .routes.mood import mood_bp # Ensure this line is present and correct
        app.register_blueprint(mood_bp)
        logging.info("Successfully registered 'mood_bp' blueprint.") # This log is crucial

    except ImportError as e:
        logging.error(f"CRITICAL ERROR: Failed to import or register blueprint: {e}", exc_info=True)
        # This error would prevent the routes from being available.

    logging.info("--- Flask app creation finished ---")
    return app

# This should be the entry point Vercel uses.
# If your vercel.json points to 'app' as a directory, Vercel might look for 'app.py' or 'wsgi.py'
# Ensure Vercel is configured to find this 'app' instance.
# Typically, if this file is __init__.py, Vercel's Python runtime will find the 'app' instance.
app = create_app()

# --- Health Check and Root Routes ---
@app.route('/')
def root():
    # Check if Supabase client was initialized
    if hasattr(app, 'supabase') and app.supabase:
        return "Flask backend is running. Supabase client appears to be initialized."
    else:
        return "Flask backend is running. Supabase client FAILED to initialize (check logs)."


@app.route('/api/health')
def health_check():
    # More detailed health check
    supabase_status = "OK"
    if not hasattr(app, 'supabase') or not app.supabase:
        supabase_status = "Error: Supabase client not initialized"
    
    # Check if blueprints are registered (basic check)
    # A more robust check would inspect app.blueprints
    blueprints_registered = []
    if 'journal' in app.blueprints:
        blueprints_registered.append("journal_bp")
    if 'mood' in app.blueprints: # Check if 'mood' (name of mood_bp) is in registered blueprints
        blueprints_registered.append("mood_bp")

    return jsonify({
        "status": "healthy",
        "supabase_client": supabase_status,
        "registered_blueprints": blueprints_registered if blueprints_registered else "None or check failed"
    }), 200
