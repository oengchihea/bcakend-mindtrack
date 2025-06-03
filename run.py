from app import create_app
from dotenv import load_dotenv
from flask_cors import CORS # CORS is imported but potentially not used if create_app handles it fully
import os

load_dotenv()
# --- DEBUG LINE ---
print(f"DEBUG run.py: SUPABASE_KEY loaded by dotenv (first 10 chars): {os.getenv('SUPABASE_KEY')[:10] if os.getenv('SUPABASE_KEY') else 'NOT FOUND'}")
# --- END DEBUG LINE ---

# The import of main_bp here isn't standard if it's already handled in create_app.
# It's not being used in this run.py file directly.
# try:
#     from app.routes.main import main_bp
#     print("Successfully imported main_bp from run.py (though typically registered in create_app)!")
# except ImportError as e:
#     print(f"Import of main_bp from run.py failed: {e}")

app = create_app()

# This CORS setup might be redundant if create_app() configures CORS sufficiently.
# If create_app() already has CORS(app, resources={r"/api/*": {"origins": "*"}}),
# this line in run.py can be removed or commented out.
# CORS(app, resources={r"/api/*": {"origins": "*"}})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)