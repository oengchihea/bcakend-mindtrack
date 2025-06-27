from datetime import datetime, timezone
import os
import logging
from flask import Flask, jsonify, current_app
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv

# Configure logging for production
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def create_app():
    """
    Create and configure the Flask application.

    Returns:
        Flask: Configured Flask application instance.
    """
    app = Flask(__name__)
    load_dotenv()

    # Configure environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SUPABASE_URL'] = os.getenv('SUPABASE_URL')
    app.config['SUPABASE_KEY'] = (
        os.getenv('SUPABASE_ANON_KEY') or
        os.getenv('SUPABASE_KEY') or
        os.getenv('SUPABASE_ROLE_SERVICE') or
        os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    )
    app.config['SUPABASE_ANON_KEY'] = app.config['SUPABASE_KEY']
    app.config['SUPABASE_SERVICE_ROLE_KEY'] = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or app.config['SUPABASE_KEY']

    # Initialize Supabase client
    with app.app_context():
        if not all([app.config['SUPABASE_URL'], app.config['SUPABASE_KEY']]):
            logger.error("Missing Supabase URL or Key in environment variables")
            app.supabase = None
            current_app.config['SUPABASE_CLIENT'] = None
        else:
            try:
                supabase_client = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
                app.supabase = supabase_client
                current_app.config['SUPABASE_CLIENT'] = supabase_client
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                app.supabase = None
                current_app.config['SUPABASE_CLIENT'] = None

    # Configure CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    try:
        from .routes.journal import journal_bp
        app.register_blueprint(journal_bp, url_prefix='/api')

        from .routes.journal_prompt import journal_prompt_bp
        app.register_blueprint(journal_prompt_bp, url_prefix='/api')

        from .routes.mood import mood_bp
        app.register_blueprint(mood_bp, url_prefix='/api')

        from .routes.auth import auth_bp
        app.register_blueprint(auth_bp, url_prefix='/api')

        from .routes.user import user_bp
        app.register_blueprint(user_bp, url_prefix='/api')

        from .routes.posts import posts_bp
        app.register_blueprint(posts_bp, url_prefix='/api')

        from .routes.analyze_journal import analyze_bp
        app.register_blueprint(analyze_bp, url_prefix='/api')

        from .routes.events import events_bp
        app.register_blueprint(events_bp, url_prefix='/api')

        from .routes.main import main_bp
        app.register_blueprint(main_bp, url_prefix='/api')
    except ImportError as e:
        logger.error(f"Failed to register blueprint: {e}")

    @app.route('/')
    def root():
        """Root endpoint for the Flask application."""
        status = "ok" if hasattr(app, 'supabase') and app.supabase else "degraded"
        supabase_status = "connected" if status == "ok" else "not_connected"
        return jsonify({
            "message": f"Flask backend is running. Supabase client {'is initialized' if status == 'ok' else 'failed to initialize'}.",
            "status": status,
            "supabase": supabase_status
        }), 200

    @app.route('/api/health')
    def health_check():
        """Health check endpoint for the Flask application."""
        supabase_status = "connected" if hasattr(app, 'supabase') and app.supabase else "not_connected"
        blueprints_registered = list(app.blueprints.keys())
        return jsonify({
            "status": "healthy" if supabase_status == "connected" else "degraded",
            "supabase_client": supabase_status,
            "registered_blueprints": blueprints_registered or ["None"],
            "environment_check": {
                "SUPABASE_URL": "set" if app.config.get('SUPABASE_URL') else "missing",
                "SUPABASE_KEY": "set" if app.config.get('SUPABASE_KEY') else "missing",
                "SECRET_KEY": "set" if app.config.get('SECRET_KEY') else "missing"
            }
        }), 200

    @app.errorhandler(Exception)
    def handle_exception(e):
        """
        Global error handler for unhandled exceptions.

        Args:
            e (Exception): The exception that occurred.

        Returns:
            JSON response with error details.
        """
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify({
            "error": "A server error has occurred",
            "type": type(e).__name__,
            "details": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 500

    return app