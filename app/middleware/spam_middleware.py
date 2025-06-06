from functools import wraps
from flask import request, jsonify, g, current_app
from app.services.auto_spam_detector_service import spam_detector
def spam_protection(f):
    """Decorator to automatically check for spam and rate limits"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Only check POST and PUT requests
        if request.method not in ['POST', 'PUT']:
            return f(*args, **kwargs)
        
        try:
            # Get request data
            data = request.get_json()
            if not data:
                return f(*args, **kwargs)
            
            # Check if we have user context
            if not hasattr(g, 'current_user') or not g.current_user:
                return f(*args, **kwargs)
            
            user_id = g.current_user.id
            
            # Determine action type and content
            action_type = 'posts'
            content = ''
            
            if 'comments' in request.path:
                action_type = 'comments'
                content = data.get('text', '')
            else:
                # For posts, combine title and content
                title = data.get('title', '')
                post_content = data.get('content', '')
                content = f"{title} {post_content}".strip()
            
            # Check if content should be blocked
            should_block, block_info = spam_detector.should_block_content(
                user_id, action_type, content, current_app.supabase
            )
            
            if should_block:
                # Return appropriate error response
                status_code = 429 if 'limit' in block_info.get('reason', '') else 400
                
                return jsonify({
                    'error': 'Content blocked',
                    'blocked': True,
                    'reason': block_info.get('reason'),
                    'message': block_info.get('message'),
                    'details': block_info
                }), status_code
            
            # Store spam info for later use
            g.spam_info = block_info
            
            # All checks passed, proceed with the request
            return f(*args, **kwargs)
            
        except Exception as e:
            print(f"Error in spam protection: {e}")
            # Allow the request to proceed on error
            return f(*args, **kwargs)
    
    return decorated_function
