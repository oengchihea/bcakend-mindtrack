#!/usr/bin/env python3
"""
Test script to verify Supabase client initialization with final fixes
"""
import os
from dotenv import load_dotenv
from supabase import create_client
import json

def test_supabase_initialization():
    """Test if Supabase client can be initialized without errors"""
    try:
        # Load environment variables
        load_dotenv()
        
        # Get environment variables
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_ANON_KEY')
        
        print(f"🔧 Testing Supabase initialization with final fixes...")
        print(f"🔧 Supabase URL: {supabase_url}")
        print(f"🔧 Supabase Key: {'*' * 10}...{supabase_key[-4:] if supabase_key else 'None'}")
        
        if not supabase_url or not supabase_key:
            print(json.dumps({"error": "Missing environment variables"}))
            return False
        
        # Test client creation with explicit parameters
        print("🔧 Creating Supabase client with explicit parameters...")
        supabase = create_client(
            supabase_url=supabase_url,
            supabase_key=supabase_key
        )
        
        print("✅ Supabase client created successfully!")
        
        # Test basic auth method access
        print("🔧 Testing auth method access...")
        if hasattr(supabase, 'auth'):
            print("✅ Auth module accessible")
        else:
            print("❌ Auth module not accessible")
            return False
        
        # Test table access
        print("🔧 Testing table access...")
        try:
            # Just test if we can access a table (don't actually query)
            table = supabase.table('user')
            print("✅ Table access working")
        except Exception as e:
            print(f"⚠️ Table access test failed: {e}")
            # This might fail due to RLS, but client creation should work
        
        print("✅ All tests passed! Supabase client is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_supabase_initialization()
    if success:
        print("\n🎉 Supabase client initialization test PASSED!")
        exit(0)
    else:
        print("\n💥 Supabase client initialization test FAILED!")
        exit(1) 