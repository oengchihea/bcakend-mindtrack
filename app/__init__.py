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
        raise ValueError("Supabase credentials are not set.")

    # --- Supabase Client Initialization ---
    try:
        app.supabase = create_client(app.config['SUPABASE_URL'], app.config['SUPABASE_KEY'])
        logging.info("Supabase client initialized successfully.")
    except Exception as e:
        logging.error(f"CRITICAL ERROR: Failed to initialize Supabase client: {e}", exc_info=True)
        raise

    # --- CORS and Blueprint Registration ---
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    logging.info("CORS configured for /api/*.")

    try:
        from .routes.journal import journal_bp
        app.register_blueprint(journal_bp)
        logging.info("Successfully registered 'journal_bp' blueprint.")
    except ImportError as e:
        logging.error(f"CRITICAL ERROR: Failed to import or register blueprint: {e}", exc_info=True)
        raise

    logging.info("--- Flask app creation finished successfully ---")
    return app

app = create_app()

# --- Health Check and Root Routes ---
@app.route('/')
def root():
    return "Flask backend is running."

@app.route('/api/health')
def health_check():
    return jsonify({"status": "healthy"}), 200
