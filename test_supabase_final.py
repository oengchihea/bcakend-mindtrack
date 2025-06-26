#!/usr/bin/env python3
"""
Comprehensive test script to verify Supabase client initialization and diagnose deployment issues
"""
import os
import sys
import json
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_environment_variables():
    """Test if all required environment variables are present"""
    logger.info("🔍 Testing environment variables...")
    
    load_dotenv()
    
    required_vars = ['SUPABASE_URL', 'SUPABASE_KEY']
    optional_vars = ['SUPABASE_ANON_KEY', 'SUPABASE_SERVICE_ROLE_KEY', 'SECRET_KEY']
    
    missing_vars = []
    present_vars = []
    
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            present_vars.append(var)
            if var == 'SUPABASE_URL':
                logger.info(f"✅ {var}: {value}")
            else:
                logger.info(f"✅ {var}: {'*' * 10}...{value[-4:] if len(value) > 4 else '****'}")
        else:
            missing_vars.append(var)
            logger.error(f"❌ {var}: NOT SET")
    
    for var in optional_vars:
        value = os.environ.get(var)
        if value:
            logger.info(f"ℹ️ {var}: {'*' * 10}...{value[-4:] if len(value) > 4 else '****'}")
        else:
            logger.warning(f"⚠️ {var}: NOT SET (optional)")
    
    if missing_vars:
        logger.error("🚨 Missing required environment variables!")
        return False, missing_vars
    
    logger.info("✅ All required environment variables are present")
    return True, present_vars

def test_supabase_import():
    """Test if Supabase can be imported"""
    logger.info("🔍 Testing Supabase import...")
    
    try:
        from supabase import create_client, Client
        logger.info("✅ Supabase module imported successfully")
        return True
    except ImportError as e:
        logger.error(f"❌ Failed to import Supabase: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error importing Supabase: {e}")
        return False

def test_supabase_client_creation():
    """Test if Supabase client can be created"""
    logger.info("🔍 Testing Supabase client creation...")
    
    try:
        from supabase import create_client
        
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_KEY') or os.environ.get('SUPABASE_ANON_KEY')
        
        if not supabase_url or not supabase_key:
            logger.error("❌ Missing URL or key for client creation")
            return False
        
        logger.info("🔧 Creating Supabase client...")
        supabase = create_client(
            supabase_url=supabase_url,
            supabase_key=supabase_key
        )
        
        logger.info("✅ Supabase client created successfully")
        
        # Test if we can access auth
        if hasattr(supabase, 'auth'):
            logger.info("✅ Auth module accessible")
        else:
            logger.warning("⚠️ Auth module not accessible")
        
        # Test if we can access table operations
        try:
            table = supabase.table('user')
            logger.info("✅ Table access working")
        except Exception as e:
            logger.warning(f"⚠️ Table access test failed: {e}")
            # This might fail due to RLS, but client creation should work
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create Supabase client: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        return False

def test_flask_app_creation():
    """Test if Flask app can be created without errors"""
    logger.info("🔍 Testing Flask app creation...")
    
    try:
        # Add the current directory to Python path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        from run import app
        logger.info("🔧 Testing Flask application from run.py...")
        logger.info("✅ Flask application created successfully")
        
        # Test if Supabase is available in app
        if hasattr(app, 'supabase') and app.supabase:
            logger.info("✅ Supabase client available in Flask app")
        else:
            logger.warning("⚠️ Supabase client NOT available in Flask app")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to create Flask app: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        
        # Print full traceback for debugging
        import traceback
        logger.error("Full traceback:")
        logger.error(traceback.format_exc())
        
        return False

def generate_diagnostic_report():
    """Generate a comprehensive diagnostic report"""
    logger.info("📋 Generating diagnostic report...")
    
    report = {
        "test_results": {},
        "environment": {},
        "system_info": {},
        "recommendations": []
    }
    
    # Environment variables test
    env_success, env_details = test_environment_variables()
    report["test_results"]["environment_variables"] = {
        "success": env_success,
        "details": env_details
    }
    
    # Supabase import test
    import_success = test_supabase_import()
    report["test_results"]["supabase_import"] = {
        "success": import_success
    }
    
    # Supabase client creation test
    client_success = test_supabase_client_creation()
    report["test_results"]["supabase_client"] = {
        "success": client_success
    }
    
    # Flask app creation test
    flask_success = test_flask_app_creation()
    report["test_results"]["flask_app"] = {
        "success": flask_success
    }
    
    # System info
    report["system_info"] = {
        "python_version": sys.version,
        "platform": sys.platform,
        "current_directory": os.getcwd(),
        "script_location": os.path.abspath(__file__)
    }
    
    # Environment info
    report["environment"] = {
        "FLASK_ENV": os.environ.get("FLASK_ENV", "not_set"),
        "VERCEL_ENV": os.environ.get("VERCEL_ENV", "not_set"),
        "PWD": os.environ.get("PWD", "not_set")
    }
    
    # Generate recommendations
    if not env_success:
        report["recommendations"].append("Set missing environment variables in Vercel dashboard")
    
    if not import_success:
        report["recommendations"].append("Check if supabase package is installed: pip install supabase")
    
    if not client_success:
        report["recommendations"].append("Verify Supabase URL and key are correct")
    
    if not flask_success:
        report["recommendations"].append("Check Flask app configuration and dependencies")
    
    if all([env_success, import_success, client_success, flask_success]):
        report["recommendations"].append("All tests passed! Your backend should work correctly.")
    
    return report

def main():
    """Run comprehensive Supabase and Flask testing"""
    logger.info("🚀 Starting comprehensive backend testing...")
    
    try:
        report = generate_diagnostic_report()
        
        logger.info("📊 Test Summary:")
        for test_name, test_result in report["test_results"].items():
            status = "✅ PASS" if test_result["success"] else "❌ FAIL"
            logger.info(f"  {test_name}: {status}")
        
        logger.info("💡 Recommendations:")
        for recommendation in report["recommendations"]:
            logger.info(f"  - {recommendation}")
        
        # Output JSON report for programmatic use
        print("\n" + "="*50)
        print("JSON DIAGNOSTIC REPORT:")
        print("="*50)
        print(json.dumps(report, indent=2))
        
        # Return appropriate exit code
        all_tests_passed = all(result["success"] for result in report["test_results"].values())
        
        if all_tests_passed:
            logger.info("🎉 All tests passed! Your backend should work correctly.")
            return 0
        else:
            logger.error("💥 Some tests failed. Check the recommendations above.")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Test script failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 