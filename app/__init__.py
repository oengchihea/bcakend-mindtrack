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

    # --- Environment Variable Check - FIXED ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL')
    
    # FIXED: Support multiple environment variable names
    app.config['SUPABASE_KEY'] = (
        os.environ.get('SUPABASE_ANON_KEY') or 
        os.environ.get('SUPABASE_KEY') or
        os.environ.get('SUPABASE_ROLE_SERVICE')
    )
    app.config['SUPABASE_ANON_KEY'] = app.config['SUPABASE_KEY']  # For compatibility
    app.config['SUPABASE_SERVICE_ROLE_KEY'] = os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or app.config['SUPABASE_KEY']

    logging.info(f"SUPABASE_URL Loaded: {'YES' if app.config['SUPABASE_URL'] else 'NO - CRITICAL'}")
    logging.info(f"SUPABASE_KEY Loaded: {'YES' if app.config['SUPABASE_KEY'] else 'NO - CRITICAL'}")

    # Initialize Supabase client within application context - GRACEFUL HANDLING
    with app.app_context():
        if not all([app.config['SUPABASE_URL'], app.config['SUPABASE_KEY']]):
            logging.error("CRITICAL ERROR: Missing Supabase URL or Key in environment variables.")
            logging.error("Required environment variables:")
            logging.error("- SUPABASE_URL (your Supabase project URL)")
            logging.error("- SUPABASE_ANON_KEY (your Supabase anon key)")
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
                logging.error("This usually means:")
                logging.error("- Invalid SUPABASE_URL or SUPABASE_ANON_KEY")
                logging.error("- Network connectivity issues")
                logging.error("- Supabase project is not accessible")
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

        # Register Events Blueprint
        from .routes.events import events_bp
        app.register_blueprint(events_bp)  # This already has /api prefix
        logging.info("Successfully registered 'events_bp' blueprint.")

    except ImportError as e:
        logging.error(f"CRITICAL ERROR: Failed to import or register blueprint: {e}", exc_info=True)

    # --- Health Check and Root Routes ---
    @app.route('/')
    def root():
        if hasattr(app, 'supabase') and app.supabase:
            return jsonify({
                "message": "Flask backend is running. Supabase client appears to be initialized.",
                "status": "ok",
                "supabase": "connected"
            }), 200
        else:
            return jsonify({
                "message": "Flask backend is running. Supabase client FAILED to initialize (check logs).",
                "status": "degraded",
                "supabase": "not_connected",
                "action_required": "Check environment variables: SUPABASE_URL and SUPABASE_ANON_KEY"
            }), 200

    @app.route('/api/health')
    def health_check():
        supabase_status = "OK"
        if not hasattr(app, 'supabase') or not app.supabase:
            supabase_status = "Error: Supabase client not initialized"
        
        blueprints_registered = list(app.blueprints.keys())

        return jsonify({
            "status": "healthy",
            "supabase_client": supabase_status,
            "registered_blueprints": blueprints_registered if blueprints_registered else "None",
            "environment_check": {
                "SUPABASE_URL": "Set" if app.config.get('SUPABASE_URL') else "Missing",
                "SUPABASE_KEY": "Set" if app.config.get('SUPABASE_KEY') else "Missing",
                "SECRET_KEY": "Set" if app.config.get('SECRET_KEY') else "Missing"
            },
            "debug_info": {
                "supabase_initialized": hasattr(app, 'supabase') and app.supabase is not None,
                "flask_env": os.environ.get('FLASK_ENV', 'development'),
                "vercel_env": os.environ.get('VERCEL_ENV', 'not_vercel')
            }
        }), 200

    # --- Enhanced Global Error Handler ---
    @app.errorhandler(Exception)
    def handle_exception(e):
        import traceback
        current_app.logger.error(f"Unhandled exception: {e}")
        current_app.logger.error(traceback.format_exc())
        
        # More specific error information for debugging
        error_type = type(e).__name__
        error_details = {
            "error": "A server error has occurred",
            "type": error_type,
            "details": str(e),
            "timestamp": logging.Formatter().formatTime(logging.LogRecord('', 0, '', 0, '', (), None)),
        }
        
        # Add specific guidance for common errors
        if "supabase" in str(e).lower():
            error_details["guidance"] = "This appears to be a Supabase-related error. Check environment variables and Supabase configuration."
        elif "import" in str(e).lower():
            error_details["guidance"] = "This appears to be an import error. Check if all required dependencies are installed."
        
        return jsonify(error_details), 500

    logging.info("--- Flask app creation finished ---")
    return app