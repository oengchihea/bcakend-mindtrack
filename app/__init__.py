import logging
import os
from flask import Flask, jsonify
from flask_cors import CORS
from supabase import create_client
from dotenv import load_dotenv
from datetime import datetime, timezone

# Configure logging for Vercel
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s [%(pathname)s:%(lineno)d]')

def create_app():
    logging.info("--- Starting Flask app creation at %s ---", datetime.now(timezone.utc).isoformat())
    load_dotenv()
    app = Flask(__name__)

    # --- Environment Variable Check ---
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_secret_key')
    app.config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL')
    app.config['SUPABASE_KEY'] = os.environ.get('SUPABASE_KEY')

    logging.info(f"SUPABASE_URL Loaded: {'YES' if app.config['SUPABASE_URL'] else 'NO - CRITICAL'}")
    logging.info(f"SUPABASE_KEY Loaded: {'YES' if app.config['SUPABASE_KEY'] else 'NO - CRITICAL'}")
    
    if not all([app.config['SUPABASE_URL'], app.config['SUPABASE_KEY']]):
        logging.error("CRITICAL ERROR: Missing Supabase URL or Key in environment variables at %s", datetime.now(timezone.utc).isoformat())
        app.supabase = None
    else:
        try:
            app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
            logging.info("Supabase client initialized successfully with service key at %s", datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logging.error(f"CRITICAL ERROR: Failed to initialize Supabase client with service key: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
            app.supabase = None

    # --- CORS and Blueprint Registration ---
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    logging.info("CORS configured for /api/* at %s", datetime.now(timezone.utc).isoformat())

    try:
        # Register Journal Blueprint
        from .routes.journal import journal_bp
        app.register_blueprint(journal_bp, url_prefix='/api')
        logging.info("Successfully registered 'journal_bp' blueprint with /api prefix at %s", datetime.now(timezone.utc).isoformat())

        # Register Analyze Journal Blueprint
        from .routes.analyze_journal import analyze_bp
        app.register_blueprint(analyze_bp, url_prefix='/api')
        logging.info("Successfully registered 'analyze_bp' blueprint with /api prefix at %s", datetime.now(timezone.utc).isoformat())

        # Register Journal Prompt Blueprint
        from .routes.journal_prompt import journal_prompt_bp
        app.register_blueprint(journal_prompt_bp, url_prefix='/api')
        logging.info("Successfully registered 'journal_prompt_bp' blueprint with /api prefix at %s", datetime.now(timezone.utc).isoformat())

        # Debug route to confirm endpoints
        @app.route('/api/health', methods=['GET'])
        def health_check():
            supabase_status = "OK" if app.supabase else "Error: Supabase client not initialized"
            blueprints = list(app.blueprints.keys())
            routes = sorted([f"{rule.method} {rule.rule}" for rule in app.url_map.iter_rules()])
            logging.info("Registered routes: %s at %s", routes, datetime.now(timezone.utc).isoformat())
            return jsonify({
                "status": "healthy",
                "supabase_client": supabase_status,
                "registered_blueprints": blueprints,
                "routes": routes
            }), 200

    except ImportError as e:
        logging.error(f"CRITICAL ERROR: Failed to import or register blueprint: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
        return None
    except Exception as e:
        logging.error(f"Unexpected error during app setup: {e} at %s", datetime.now(timezone.utc).isoformat(), exc_info=True)
        return None

    logging.info("--- Flask app creation finished at %s ---", datetime.now(timezone.utc).isoformat())
    return app

# WSGI application for Vercel
app = create_app()
if app is None:
    raise RuntimeError("Failed to create Flask application")

# Ensure the app object is the WSGI entry point
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    # For Vercel WSGI
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Explicitly export the app for WSGI
application = app