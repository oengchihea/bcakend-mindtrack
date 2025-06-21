from app import create_app
from dotenv import load_dotenv
import os

load_dotenv()

# --- DEBUG LINES ---
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
print(f"DEBUG run.py: SUPABASE_URL loaded: {'YES' if supabase_url else 'NO - CRITICAL'}")
print(f"DEBUG run.py: SUPABASE_KEY loaded: {'YES' if supabase_key else 'NO - CRITICAL'} (first 10 chars: {supabase_key[:10] if supabase_key else 'NOT FOUND'})")
# --- END DEBUG LINES ---

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)