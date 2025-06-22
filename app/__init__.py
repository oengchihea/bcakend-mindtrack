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
    app.config['SUPABASE_SERVICE_ROLE_KEY'] = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

    logging.info(f"SUPABASE_URL Loaded: {'YES' if app.config['SUPABASE_URL'] else 'NO - CRITICAL'}")
    logging.info(f"SUPABASE_KEY Loaded: {'YES' if app.config['SUPABASE_KEY'] else 'NO - CRITICAL'}")
    
    if not all([app.config['SUPABASE_URL'], app.config['SUPABASE_KEY']]):
        logging.error("CRITICAL ERROR: Missing Supabase URL or Key in environment variables.")
        app.supabase = None
    else:
        try:
            app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
            logging.info("Supabase client initialized successfully with service key.")
        except Exception as e:
            logging.error(f"CRITICAL ERROR: Failed to initialize Supabase client with service key: {e}", exc_info=True)
            app.supabase = None

    # --- CORS and Blueprint Registration ---
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    logging.info("CORS configured for /api/*.")

    try:
        # Register Journal Blueprint with Supabase client
        from .routes.journal import journal_bp
        app.register_blueprint(journal_bp, url_prefix='/api')
        logging.info("Successfully registered 'journal_bp' blueprint with /api prefix.")

        # Register Mood Blueprint
        from .routes.mood import mood_bp
        app.register_blueprint(mood_bp, url_prefix='/api')
        logging.info("Successfully registered 'mood_bp' blueprint with /api prefix.")

        # Register Auth Blueprint
        from .routes.auth import auth_bp
        app.register_blueprint(auth_bp, url_prefix='/api')
        logging.info("Successfully registered 'auth_bp' blueprint with /api prefix.")

        # Register User Blueprint
        from .routes.user import user_bp
        app.register_blueprint(user_bp, url_prefix='/api')
        logging.info("Successfully registered 'user_bp' blueprint with /api prefix.")

        # Register Posts Blueprint
        from .routes.posts import posts_bp
        app.register_blueprint(posts_bp, url_prefix='/api')
        logging.info("Successfully registered 'posts_bp' blueprint with /api prefix.")

        # Register Analyze Journal Blueprint
        from .routes.analyze_journal import analyze_bp
        app.register_blueprint(analyze_bp, url_prefix='/api')
        logging.info("Successfully registered 'analyze_bp' blueprint with /api prefix.")

        # Debug route to confirm /api/journalScore is accessible
        @app.route('/api/journalScore', methods=['GET'])
        def debug_journal_score():
            return jsonify({"message": "Journal score endpoint is accessible"}), 200

    except ImportError as e:
        logging.error(f"CRITICAL ERROR: Failed to import or register blueprint: {e}", exc_info=True)

    logging.info("--- Flask app creation finished ---")
    return app

# This should be the entry point Vercel uses.
app = create_app()

# --- Health Check and Root Routes ---
@app.route('/')
def root():
    if hasattr(app, 'supabase') and app.supabase:
        return "Flask backend is running. Supabase client appears to be initialized."
    else:
        return "Flask backend is running. Supabase client FAILED to initialize (check logs)."

@app.route('/api/health')
def health_check():
    supabase_status = "OK"
    if not hasattr(app, 'supabase') or not app.supabase:
        supabase_status = "Error: Supabase client not initialized"
    
    blueprints_registered = []
    if 'journal' in app.blueprints:
        blueprints_registered.append("journal_bp")
    if 'mood' in app.blueprints:
        blueprints_registered.append("mood_bp")
    if 'auth' in app.blueprints:
        blueprints_registered.append("auth_bp")
    if 'user' in app.blueprints:
        blueprints_registered.append("user_bp")
    if 'posts' in app.blueprints:
        blueprints_registered.append("posts_bp")
    if 'analyze' in app.blueprints:
        blueprints_registered.append("analyze_bp")

    return jsonify({
        "status": "healthy",
        "supabase_client": supabase_status,
        "registered_blueprints": blueprints_registered if blueprints_registered else "None or check failed"
    }), 200