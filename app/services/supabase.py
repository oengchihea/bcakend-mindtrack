import os
from supabase import create_client

class supabaseService:
    def __init__(self):
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        self.client = create_client(url, key)
        
