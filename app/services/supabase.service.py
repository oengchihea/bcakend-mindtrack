# D:\All file\Internship\MindTrack\backend2\bcakend-mindtrack\app\services\supabase_service.py
import os
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class SupabaseService:
    def __init__(self):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        logging.info(f"Initializing SupabaseService with URL: {url[:10]}... and key length: {len(key) if key else 0}")
        if not url or not key:
            logging.error("CRITICAL ERROR: SUPABASE_URL or SUPABASE_KEY environment variables are not set")
            self.client = None
        else:
            try:
                self.client = create_client(url, key)
                logging.info("Supabase client initialized successfully")
            except Exception as e:
                logging.error(f"CRITICAL ERROR: Failed to create Supabase client: {e}", exc_info=True)
                self.client = None