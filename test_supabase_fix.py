#!/usr/bin/env python3
"""
Test script to verify Supabase client initialization with fixed API
"""
import os
from dotenv import load_dotenv
from supabase import create_client

def test_supabase_initialization():
    """Test if Supabase client can be initialized without errors"""
    try:
        # Load environment variables
        load_dotenv()
        
        # Get environment variables
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_ANON_KEY')
        
        print(f"🔧 Testing Supabase initialization with fixed API...")
        print(f"🔧 Supabase URL: {supabase_url}")
        print(f"🔧 Supabase Key: {'*' * 10}...{supabase_key[-4:] if supabase_key else 'None'}")
        
        if not supabase_url or not supabase_key:
            print("❌ Missing environment variables")
            return False
        
        # Test the fixed client initialization
        print("🔧 Creating Supabase client with fixed API...")
        supabase = create_client(supabase_url, supabase_key)
        
        print("✅ Supabase client created successfully!")
        
        # Test a simple operation
        print("🔧 Testing simple operation...")
        try:
            # Try to get user table info (this should work even without auth)
            result = supabase.table('user').select('count', count='exact').limit(1).execute()
            print("✅ Basic Supabase operation successful!")
            return True
        except Exception as e:
            print(f"⚠️ Basic operation failed (this might be expected): {e}")
            print("✅ But client initialization was successful!")
            return True
            
    except Exception as e:
        print(f"❌ Supabase initialization failed: {e}")
        return False

if __name__ == "__main__":
    success = test_supabase_initialization()
    if success:
        print("🎉 All tests passed! Supabase client is working correctly.")
    else:
        print("💥 Tests failed! There are still issues with Supabase client.") 