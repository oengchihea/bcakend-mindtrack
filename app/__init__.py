import logging
import os
from flask import Flask, jsonify, current_app
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

    # Initialize Supabase client within application context
    with app.app_context():
        if not all([app.config['SUPABASE_URL'], app.config['SUPABASE_KEY']]):
            logging.error("CRITICAL ERROR: Missing Supabase URL or Key in environment variables.")
            app.supabase = None
            current_app.config['SUPABASE_CLIENT'] = None
        else:
            try:
                supabase_client = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
                app.supabase = supabase_client
                current_app.config['SUPABASE_CLIENT'] = supabase_client
                logging.info("Supabase client initialized successfully with service key and stored in config.")
            except Exception as e:
                logging.error(f"CRITICAL ERROR: Failed to initialize Supabase client with service key: {e}", exc_info=True)
                app.supabase = None
                current_app.config['SUPABASE_CLIENT'] = None

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

        # Register Journal Prompt Blueprint
        from .routes.journal_prompt import journal_prompt_bp
        app.register_blueprint(journal_prompt_bp, url_prefix='/api')
        logging.info("Successfully registered 'journal_prompt_bp' blueprint with /api prefix.")

        from .routes.events import events_bp
        app.register_blueprint(events_bp)

        # Debug route to confirm /api/journalScore is accessible
        @app.route('/api/journalScore', methods=['GET'])
        def debug_journal_score():
            return jsonify({"message": "Journal score endpoint is accessible"}), 200

    except ImportError as e:
        logging.error(f"CRITICAL ERROR: Failed to import or register blueprint: {e}", exc_info=True)

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
        
        blueprints_registered = list(app.blueprints.keys())

        return jsonify({
            "status": "healthy",
            "supabase_client": supabase_status,
            "registered_blueprints": blueprints_registered if blueprints_registered else "None"
        }), 200

    logging.info("--- Flask app creation finished ---")
    return app

# The app object is now created in `run.py` to have a single entrypoint.
# The health checks are moved inside create_app.