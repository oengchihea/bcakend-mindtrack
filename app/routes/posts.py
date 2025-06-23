from flask import Blueprint, request, jsonify, current_app, g
from datetime import datetime
import uuid
from app.routes.auth import auth_required
from app.middleware.spam_middleware import spam_protection
from app.services.auto_spam_detector_service import spam_detector
posts_bp = Blueprint('posts', __name__)

# Debug route to test if posts blueprint is working
@posts_bp.route('/posts/debug', methods=['GET'])
def posts_debug():
    """Debug endpoint to test if posts blueprint is accessible"""
    return jsonify({
        'message': 'Posts blueprint is working',
        'available_routes': [
            '/api/posts/',
            '/api/posts',
            '/api/posts/debug',
            '/api/posts/health'
        ]
    }), 200

# Simple posts route without auth for testing
@posts_bp.route('/posts/test', methods=['GET'])
def posts_test():
    """Simple test endpoint for posts without authentication"""
    return jsonify({
        'message': 'Posts endpoint is accessible',
        'posts': [],
        'count': 0
    }), 200

# ============================================================================
# USER LIMITS ENDPOINT
# ============================================================================

@posts_bp.route('/posts/user-limits', methods=['GET'])
@auth_required
def get_user_limits():
    """Get current user's posting limits and usage"""
    try:
        user_id = g.user.id
        limits_info = spam_detector.get_user_limits(user_id, current_app.supabase)
        return jsonify(limits_info), 200
        
    except Exception as e:
        print(f"Error getting user limits: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# POSTS ENDPOINTS WITH AUTO SPAM PROTECTION
# ============================================================================

@posts_bp.route('/posts/create', methods=['POST'])
@auth_required
@spam_protection  # Automatically blocks spam
def create_post():
    """Create a new post"""
    try:
        data = request.get_json()
        
        # Extract user_id from authenticated user (UUID format)
        user_id = g.user.id
        
        # Validate required fields
        required_fields = ['title', 'content']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        # Get spam info from middleware
        spam_info = getattr(g, 'spam_info', {})
        spam_score = spam_info.get('spam_score', 0)
        
        # Get user information from user table (using user_id column)
        user_info = None
        try:
            user_result = current_app.supabase.table('user').select('name, profile_image_url').eq('user_id', user_id).execute()
            if user_result.data:
                user_info = user_result.data[0]
                print(f"✅ Found user info: {user_info}")
            else:
                print(f"⚠️ No user found with user_id: {user_id}")
        except Exception as e:
            print(f"Warning: Could not fetch user info from user table: {e}")
        
        # Prepare post data
        post_data = {
            'post_id': str(uuid.uuid4()),
            'user_id': user_id,  # Keep as UUID - don't convert to string
            'title': data['title'],
            'content': data['content'],
            'category': data.get('category'),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'spam_score': spam_score,  # Store spam score
            'is_flagged': spam_score >= 50,  # Flag if high spam score
        }
        
        print(f"Creating post with user_id: {user_id} (spam_score: {spam_score})")
        
        # Insert into Supabase with RLS context
        result = current_app.supabase.table('posts').insert(post_data).execute()
        
        if result.data:
            # Add user information to the response
            created_post = result.data[0]
            if user_info:
                created_post['user_name'] = user_info.get('name', 'Anonymous')
                created_post['user_avatar_url'] = user_info.get('profile_image_url', '')
            else:
                created_post['user_name'] = 'Anonymous'
                created_post['user_avatar_url'] = ''
            
            return jsonify({
                'message': 'Post created successfully',
                'post': created_post
            }), 201
        else:
            return jsonify({'error': 'Failed to create post'}), 500
            
    except Exception as e:
        print(f"Error creating post: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/', methods=['GET'])
@posts_bp.route('/posts', methods=['GET'])
@auth_required
def get_all_posts():
    """Get all posts (public feed) with user information"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Get all posts (excluding flagged ones for public feed)
        posts_result = current_app.supabase.table('posts').select(
            'post_id, user_id, title, content, category, created_at, updated_at, spam_score'
        ).eq('is_flagged', False).order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        
        posts_with_user_info = []
        
        for post in posts_result.data:
            # Get user info for each post from user table (using user_id column)
            try:
                user_result = current_app.supabase.table('user').select(
                    'name, profile_image_url'
                ).eq('user_id', post['user_id']).execute()
                
                if user_result.data:
                    user_info = user_result.data[0]
                    post['user_name'] = user_info.get('name', 'Anonymous')
                    post['user_avatar_url'] = user_info.get('profile_image_url', '')
                else:
                    post['user_name'] = 'Anonymous'
                    post['user_avatar_url'] = ''
                    
            except Exception as e:
                print(f"Warning: Could not fetch user info for user {post['user_id']}: {e}")
                post['user_name'] = 'Anonymous'
                post['user_avatar_url'] = ''
            
            posts_with_user_info.append(post)
        
        return jsonify({
            'posts': posts_with_user_info,
            'count': len(posts_with_user_info)
        }), 200
        
    except Exception as e:
        print(f"Error getting posts: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/<post_id>', methods=['GET'])
@auth_required
def get_post(post_id):
    """Get a specific post by ID with user information"""
    try:
        result = current_app.supabase.table('posts').select('*').eq('post_id', post_id).execute()
        
        if result.data:
            post = result.data[0]
            
            # Get user information from user table (using user_id column)
            try:
                user_result = current_app.supabase.table('user').select(
                    'name, profile_image_url'
                ).eq('user_id', post['user_id']).execute()
                
                if user_result.data:
                    user_info = user_result.data[0]
                    post['user_name'] = user_info.get('name', 'Anonymous')
                    post['user_avatar_url'] = user_info.get('profile_image_url', '')
                else:
                    post['user_name'] = 'Anonymous'
                    post['user_avatar_url'] = ''
                    
            except Exception as e:
                print(f"Warning: Could not fetch user info: {e}")
                post['user_name'] = 'Anonymous'
                post['user_avatar_url'] = ''
            
            return jsonify({
                'post': post
            }), 200
        else:
            return jsonify({'error': 'Post not found'}), 404
            
    except Exception as e:
        print(f"Error getting post: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/<post_id>', methods=['PUT'])
@auth_required
@spam_protection  # Add spam protection
def update_post(post_id):
    """Update an existing post (only by the owner)"""
    try:
        data = request.get_json()
        user_id = g.user.id
        
        # Check if post exists and belongs to the user
        existing_post = current_app.supabase.table('posts').select('*').eq('post_id', post_id).eq('user_id', user_id).execute()
        
        if not existing_post.data:
            return jsonify({'error': 'Post not found or you do not have permission to edit it'}), 404
        
        # Get spam info from middleware
        spam_info = getattr(g, 'spam_info', {})
        spam_score = spam_info.get('spam_score', 0)
        
        # Prepare update data
        update_data = {
            'updated_at': datetime.utcnow().isoformat(),
            'spam_score': spam_score,
            'is_flagged': spam_score >= 50
        }
        
        # Only update provided fields
        allowed_fields = ['title', 'content', 'category']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field]
        
        # Update in Supabase
        result = current_app.supabase.table('posts').update(update_data).eq('post_id', post_id).eq('user_id', user_id).execute()
        
        if result.data:
            return jsonify({
                'message': 'Post updated successfully',
                'post': result.data[0]
            }), 200
        else:
            return jsonify({'error': 'Failed to update post'}), 500
            
    except Exception as e:
        print(f"Error updating post: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/<post_id>', methods=['DELETE'])
@auth_required
def delete_post(post_id):
    """Delete a post (only by the owner)"""
    try:
        user_id = g.user.id
        
        # Check if post exists and belongs to the user
        existing_post = current_app.supabase.table('posts').select('*').eq('post_id', post_id).eq('user_id', user_id).execute()
        
        if not existing_post.data:
            return jsonify({'error': 'Post not found or you do not have permission to delete it'}), 404
        
        # Delete comments first (cascade delete)
        try:
            current_app.supabase.table('comments').delete().eq('post_id', post_id).execute()
        except Exception as e:
            print(f"Warning: Could not delete comments: {e}")
        
        # Delete the post
        result = current_app.supabase.table('posts').delete().eq('post_id', post_id).eq('user_id', user_id).execute()
        
        return jsonify({
            'message': 'Post deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting post: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/my-posts', methods=['GET'])
@auth_required
def get_my_posts():
    """Get all posts by the authenticated user"""
    try:
        user_id = g.user.id
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        result = current_app.supabase.table('posts').select('*').eq('user_id', user_id).order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        
        # Add user info to each post
        for post in result.data:
            try:
                user_result = current_app.supabase.table('user').select(
                    'name, profile_image_url'
                ).eq('user_id', user_id).execute()
                
                if user_result.data:
                    user_info = user_result.data[0]
                    post['user_name'] = user_info.get('name', 'Anonymous')
                    post['user_avatar_url'] = user_info.get('profile_image_url', '')
                else:
                    post['user_name'] = 'Anonymous'
                    post['user_avatar_url'] = ''
                    
            except Exception as e:
                print(f"Warning: Could not fetch user info: {e}")
                post['user_name'] = 'Anonymous'
                post['user_avatar_url'] = ''
        
        return jsonify({
            'posts': result.data,
            'count': len(result.data)
        }), 200
        
    except Exception as e:
        print(f"Error getting user posts: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# COMMENTS ENDPOINTS WITH AUTO SPAM PROTECTION
# ============================================================================

@posts_bp.route('/posts/<post_id>/comments', methods=['GET'])
@auth_required
def get_comments(post_id):
    """Get all comments for a post"""
    try:
        # Check if post exists
        post_result = current_app.supabase.table('posts').select('post_id').eq('post_id', post_id).execute()
        if not post_result.data:
            return jsonify({'error': 'Post not found'}), 404
        
        # Get comments for the post (excluding flagged ones)
        result = current_app.supabase.table('comments').select('*').eq('post_id', post_id).eq('is_flagged', False).order('created_at', desc=True).execute()
        
        # Add user info to each comment
        comments_with_user_info = []
        for comment in result.data:
            try:
                user_result = current_app.supabase.table('user').select(
                    'name, profile_image_url'
                ).eq('user_id', comment['user_id']).execute()
                
                if user_result.data:
                    user_info = user_result.data[0]
                    comment['user_name'] = user_info.get('name', 'Anonymous')
                    comment['user_avatar_url'] = user_info.get('profile_image_url', '')
                else:
                    comment['user_name'] = 'Anonymous'
                    comment['user_avatar_url'] = ''
                    
            except Exception as e:
                print(f"Warning: Could not fetch user info for comment: {e}")
                comment['user_name'] = 'Anonymous'
                comment['user_avatar_url'] = ''
            
            comments_with_user_info.append(comment)
        
        return jsonify({
            'comments': comments_with_user_info,
            'count': len(comments_with_user_info)
        }), 200
        
    except Exception as e:
        print(f"Error getting comments: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/<post_id>/comments', methods=['POST'])
@auth_required
@spam_protection  # Add spam protection
def create_comment(post_id):
    """Create a new comment on a post"""
    try:
        data = request.get_json()
        user_id = g.user.id
        
        # Check if post exists
        post_result = current_app.supabase.table('posts').select('post_id').eq('post_id', post_id).execute()
        if not post_result.data:
            return jsonify({'error': 'Post not found'}), 404
        
        # Validate required fields
        if not data.get('text'):
            return jsonify({'error': 'Comment text is required'}), 400
        
        # Get spam info from middleware
        spam_info = getattr(g, 'spam_info', {})
        spam_score = spam_info.get('spam_score', 0)
        
        # Get user info for the response
        user_info = None
        try:
            user_result = current_app.supabase.table('user').select('name, profile_image_url').eq('user_id', user_id).execute()
            if user_result.data:
                user_info = user_result.data[0]
        except Exception as e:
            print(f"Warning: Could not fetch user info: {e}")
        
        # Prepare comment data
        comment_data = {
            'id': str(uuid.uuid4()),
            'post_id': post_id,
            'user_id': user_id,  # Keep as UUID
            'text': data['text'],
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'spam_score': spam_score,  # Store spam score
            'is_flagged': spam_score >= 50,  # Flag if high spam score
        }
        
        print(f"Creating comment with user_id: {user_id} (spam_score: {spam_score})")
        
        # Insert into Supabase
        result = current_app.supabase.table('comments').insert(comment_data).execute()
        
        if result.data:
            created_comment = result.data[0]
            
            # Add user info to response
            if user_info:
                created_comment['user_name'] = user_info.get('name', 'Anonymous')
                created_comment['user_avatar_url'] = user_info.get('profile_image_url', '')
            else:
                created_comment['user_name'] = 'Anonymous'
                created_comment['user_avatar_url'] = ''
            
            return jsonify({
                'message': 'Comment created successfully',
                'comment': created_comment
            }), 201
        else:
            return jsonify({'error': 'Failed to create comment'}), 500
            
    except Exception as e:
        print(f"Error creating comment: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/<post_id>/comments/<comment_id>', methods=['PUT'])
@auth_required
@spam_protection  # Add spam protection
def update_comment(post_id, comment_id):
    """Update a comment (only by the owner)"""
    try:
        data = request.get_json()
        user_id = g.user.id
        
        # Check if comment exists and belongs to the user
        existing_comment = current_app.supabase.table('comments').select('*').eq('id', comment_id).eq('user_id', user_id).eq('post_id', post_id).execute()
        
        if not existing_comment.data:
            return jsonify({'error': 'Comment not found or you do not have permission to edit it'}), 404
        
        # Validate required fields
        if not data.get('text'):
            return jsonify({'error': 'Comment text is required'}), 400
        
        # Get spam info from middleware
        spam_info = getattr(g, 'spam_info', {})
        spam_score = spam_info.get('spam_score', 0)
        
        # Prepare update data
        update_data = {
            'text': data['text'],
            'updated_at': datetime.utcnow().isoformat(),
            'spam_score': spam_score,
            'is_flagged': spam_score >= 50
        }
        
        # Update in Supabase
        result = current_app.supabase.table('comments').update(update_data).eq('id', comment_id).eq('user_id', user_id).execute()
        
        if result.data:
            return jsonify({
                'message': 'Comment updated successfully',
                'comment': result.data[0]
            }), 200
        else:
            return jsonify({'error': 'Failed to update comment'}), 500
            
    except Exception as e:
        print(f"Error updating comment: {e}")
        return jsonify({'error': str(e)}), 500

@posts_bp.route('/posts/<post_id>/comments/<comment_id>', methods=['DELETE'])
@auth_required
def delete_comment(post_id, comment_id):
    """Delete a comment (only by the owner)"""
    try:
        user_id = g.user.id
        
        # Check if comment exists and belongs to the user
        existing_comment = current_app.supabase.table('comments').select('*').eq('id', comment_id).eq('user_id', user_id).eq('post_id', post_id).execute()
        
        if not existing_comment.data:
            return jsonify({'error': 'Comment not found or you do not have permission to delete it'}), 404
        
        # Delete from Supabase
        result = current_app.supabase.table('comments').delete().eq('id', comment_id).eq('user_id', user_id).execute()
        
        return jsonify({
            'message': 'Comment deleted successfully'
        }), 200
        
    except Exception as e:
        print(f"Error deleting comment: {e}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@posts_bp.route('/posts/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'message': 'Posts API is running',
        'timestamp': datetime.utcnow().isoformat()
    }), 200

@posts_bp.route('/posts/stats', methods=['GET'])
@auth_required
def get_stats():
    """Get statistics for the authenticated user"""
    try:
        user_id = g.user.id
        
        # Get post count
        posts_result = current_app.supabase.table('posts').select('post_id', count='exact').eq('user_id', user_id).execute()
        posts_count = posts_result.count if posts_result.count else 0
        
        # Get comment count
        try:
            comments_result = current_app.supabase.table('comments').select('id', count='exact').eq('user_id', user_id).execute()
            comments_count = comments_result.count if comments_result.count else 0
        except Exception as e:
            print(f"Warning: Could not get comment count: {e}")
            comments_count = 0
        
        return jsonify({
            'user_id': user_id,
            'posts_count': posts_count,
            'comments_count': comments_count,
            'total_activity': posts_count + comments_count
        }), 200
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'error': str(e)}), 500
