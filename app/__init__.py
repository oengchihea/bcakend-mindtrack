from flask import Flask
from flask_cors import CORS
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables from .env file (primarily for local development)
# On Vercel, these should be set in the project's Environment Variables settings.
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.logger.info("Flask app creation started.")

    # Configure app from environment variables
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        SUPABASE_URL=os.environ.get('SUPABASE_URL'),
        SUPABASE_KEY=os.environ.get('SUPABASE_KEY'),
        SUPABASE_SERVICE_ROLE_KEY=os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    )

    # Log the loaded (or not loaded) environment variables
    # This is CRUCIAL for debugging on Vercel
    app.logger.info(f"SECRET_KEY: {'Set' if app.config.get('SECRET_KEY') else 'NOT SET'}")
    app.logger.info(f"SUPABASE_URL: {app.config.get('SUPABASE_URL')}")
    app.logger.info(f"SUPABASE_KEY: {'Set' if app.config.get('SUPABASE_KEY') else 'NOT SET'}")
    app.logger.info(f"SUPABASE_SERVICE_ROLE_KEY: {'Set' if app.config.get('SUPABASE_SERVICE_ROLE_KEY') else 'NOT SET'}")

    if not app.config['SUPABASE_URL'] or not app.config['SUPABASE_KEY']:
        app.logger.error("CRITICAL: SUPABASE_URL and SUPABASE_KEY must be set in environment variables.")
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    else:
        app.logger.info("Supabase URL and Key appear to be set.")

    # Initialize Supabase client
    try:
        app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
        app.logger.info("Supabase client initialized successfully.")
    except Exception as e:
        app.logger.error(f"Failed to initialize Supabase client: {e}", exc_info=True)
        raise

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    app.logger.info("CORS enabled.")

    # Register blueprints
    app.logger.info("Registering blueprints...")
    try:
        from .routes.journal import journal_bp
        app.register_blueprint(journal_bp)
        app.logger.info("Registered journal_bp.")

        # If you have other blueprints, ensure they are registered here.
        # Any ImportError will stop the app from initializing correctly on Vercel.

    except ImportError as e:
        app.logger.error(f"Failed to import or register a blueprint: {e}", exc_info=True)
        raise

    if not app.config.get('SUPABASE_SERVICE_ROLE_KEY'):
        app.logger.warning("SUPABASE_SERVICE_ROLE_KEY not set. Some Supabase operations might fail.")

    app.logger.info("Flask app creation finished.")
    return app

# This 'app' instance is what Vercel's WSGI server will use.
app = create_app()

# A simple root route to test if the Flask app itself is running
@app.route('/')
def handle_root():
    return "Flask backend is running. Access API routes at /api/..."

@app.route('/api/health')
def health_check():
    return jsonify({"status": "healthy", "message": "Flask API is up"}), 200
