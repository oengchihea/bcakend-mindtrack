from app import create_app
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()

try:
    from app.routes.main import main_bp
    print("Successfully imported main_bp!")
except ImportError as e:
    print(f"Import failed: {e}")

app = create_app()
CORS(app, resources={r"/api/*": {"origins": "*"}})  # Allow all origins for testing

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)