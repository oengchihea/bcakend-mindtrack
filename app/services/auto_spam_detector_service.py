import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from flask import current_app

class SpamDetectionService:
    def __init__(self):
        # Daily and hourly limits
        self.limits = {
            'posts': {
                'daily': 10,
                'hourly': 3
            },
            'comments': {
                'daily': 50,
                'hourly': 15
            }
        }
        
        # Spam patterns
        self.spam_patterns = [
            r'buy\s+now',
            r'click\s+here',
            r'limited\s+time\s+offer',
            r'act\s+now',
            r'free\s+money',
            r'make\s+money\s+fast',
            r'work\s+from\s+home',
            r'earn\s+\$\d+',
            r'discount\s+code',
            r'best\s+price',
            r'viagra|cialis',
            r'casino|lottery|winner',
            r'congratulations|you\s+won',
            r'nigerian\s+prince',
            r'inheritance',
            r'investment\s+opportunity',
            r'crypto\s+investment',
            r'bitcoin\s+profit',
        ]
        
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.spam_patterns]
        
        # Suspicious domains
        self.suspicious_domains = [
            '.tk', '.ml', '.ga', '.cf', '.gq', '.top', '.loan', '.click',
            '.download', '.stream', '.science', '.party', '.racing'
        ]
    
    def check_rate_limits(self, user_id: str, action_type: str, db) -> Tuple[bool, Dict]:
        """Check if user has exceeded rate limits"""
        try:
            current_time = datetime.utcnow()
            
            # Check daily limit
            daily_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_count = self._get_action_count(user_id, action_type, daily_start, db)
            daily_limit = self.limits[action_type]['daily']
            
            if daily_count >= daily_limit:
                return False, {
                    'blocked': True,
                    'reason': 'daily_limit_exceeded',
                    'message': f'You have reached your daily limit of {daily_limit} {action_type}. Please try again tomorrow.',
                    'count': daily_count,
                    'limit': daily_limit,
                    'type': 'daily'
                }
            
            # Check hourly limit
            hourly_start = current_time - timedelta(hours=1)
            hourly_count = self._get_action_count(user_id, action_type, hourly_start, db)
            hourly_limit = self.limits[action_type]['hourly']
            
            if hourly_count >= hourly_limit:
                return False, {
                    'blocked': True,
                    'reason': 'hourly_limit_exceeded',
                    'message': f'You are posting too frequently. Please wait before posting again.',
                    'count': hourly_count,
                    'limit': hourly_limit,
                    'type': 'hourly'
                }
            
            return True, {
                'blocked': False,
                'daily': {'count': daily_count, 'limit': daily_limit, 'remaining': daily_limit - daily_count},
                'hourly': {'count': hourly_count, 'limit': hourly_limit, 'remaining': hourly_limit - hourly_count}
            }
            
        except Exception as e:
            print(f"Error checking rate limits: {e}")
            return True, {'blocked': False, 'error': str(e)}
    
    def _get_action_count(self, user_id: str, action_type: str, since: datetime, db) -> int:
        """Get count of actions since a specific time"""
        try:
            table_name = action_type  # 'posts' or 'comments'
            result = db.table(table_name).select('*', count='exact').eq('user_id', user_id).gte('created_at', since.isoformat()).execute()
            return result.count if result.count else 0
        except Exception as e:
            print(f"Error getting action count: {e}")
            return 0
    
    def analyze_content(self, text: str) -> Tuple[bool, int, List[str]]:
        """Analyze content for spam indicators"""
        if not text or len(text.strip()) < 2:
            return True, 100, ['Content too short']
        
        spam_indicators = []
        spam_score = 0
        
        # Check text length
        if len(text) > 5000:
            spam_score += 20
            spam_indicators.append('Content too long')
        
        # Check for spam patterns
        pattern_matches = 0
        for pattern in self.compiled_patterns:
            if pattern.search(text):
                pattern_matches += 1
                spam_score += 15
        
        if pattern_matches > 0:
            spam_indicators.append(f'Contains {pattern_matches} spam patterns')
        
        # Check for excessive capitalization
        if len(text) > 20:
            uppercase_count = sum(1 for c in text if c.isupper())
            uppercase_ratio = uppercase_count / len(text)
            if uppercase_ratio > 0.5:
                spam_score += 25
                spam_indicators.append('Excessive capitalization')
        
        # Check for excessive punctuation
        punctuation_count = sum(1 for c in text if c in '!?.')
        if punctuation_count > len(text) * 0.3 and len(text) > 20:
            spam_score += 20
            spam_indicators.append('Excessive punctuation')
        
        # Check for excessive URLs
        urls = re.findall(r'https?://\S+', text)
        if len(urls) > 3:
            spam_score += 30
            spam_indicators.append(f'Too many URLs ({len(urls)})')
        
        # Check for suspicious URLs
        for url in urls:
            if any(domain in url.lower() for domain in self.suspicious_domains):
                spam_score += 25
                spam_indicators.append('Suspicious URL detected')
                break
        
        # Check for repeated characters
        repeated_chars = re.findall(r'(.)\1{4,}', text)
        if repeated_chars:
            spam_score += 15
            spam_indicators.append('Repeated characters')
        
        is_spam = spam_score >= 50
        return is_spam, min(spam_score, 100), spam_indicators
    
    def check_user_behavior(self, user_id: str, db) -> Dict:
        """Check user behavior patterns"""
        try:
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            
            # Get recent posts and comments
            posts_result = db.table('posts').select('*').eq('user_id', user_id).gte('created_at', week_ago).execute()
            comments_result = db.table('comments').select('*').eq('user_id', user_id).gte('created_at', week_ago).execute()
            
            posts_count = len(posts_result.data) if posts_result.data else 0
            comments_count = len(comments_result.data) if comments_result.data else 0
            
            behavior_score = 0
            warnings = []
            
            # Check for excessive activity
            if posts_count > 50:
                behavior_score += 30
                warnings.append('Excessive posting activity')
            
            if comments_count > 200:
                behavior_score += 20
                warnings.append('Excessive commenting activity')
            
            # Check for spam content in recent posts
            spam_posts = 0
            if posts_result.data:
                for post in posts_result.data:
                    content = f"{post.get('title', '')} {post.get('content', '')}".strip()
                    is_spam, _, _ = self.analyze_content(content)
                    if is_spam:
                        spam_posts += 1
            
            if spam_posts > 0:
                behavior_score += spam_posts * 10
                warnings.append(f'{spam_posts} spam posts detected')
            
            return {
                'behavior_score': min(behavior_score, 100),
                'is_suspicious': behavior_score >= 50,
                'warnings': warnings,
                'posts_count': posts_count,
                'comments_count': comments_count
            }
            
        except Exception as e:
            print(f"Error checking user behavior: {e}")
            return {'behavior_score': 0, 'is_suspicious': False, 'warnings': []}
    
    def should_block_content(self, user_id: str, action_type: str, content: str, db) -> Tuple[bool, Dict]:
        """Main method to determine if content should be blocked"""
        
        # 1. Check rate limits
        rate_ok, rate_info = self.check_rate_limits(user_id, action_type, db)
        if not rate_ok:
            return True, rate_info
        
        # 2. Check content for spam
        is_spam, spam_score, spam_indicators = self.analyze_content(content)
        if is_spam:
            return True, {
                'blocked': True,
                'reason': 'spam_content_detected',
                'message': 'Your content appears to be spam and cannot be posted.',
                'spam_score': spam_score,
                'indicators': spam_indicators
            }
        
        # 3. Check user behavior
        behavior_info = self.check_user_behavior(user_id, db)
        if behavior_info['is_suspicious']:
            return True, {
                'blocked': True,
                'reason': 'suspicious_behavior',
                'message': 'Your account has been temporarily restricted due to suspicious activity.',
                'behavior_score': behavior_info['behavior_score'],
                'warnings': behavior_info['warnings']
            }
        
        # All checks passed
        return False, {
            'blocked': False,
            'rate_info': rate_info,
            'spam_score': spam_score,
            'behavior_info': behavior_info
        }
    
    def get_user_limits(self, user_id: str, db) -> Dict:
        """Get user's current limits and usage"""
        try:
            # Check limits for both posts and comments
            posts_rate_ok, posts_rate_info = self.check_rate_limits(user_id, 'posts', db)
            comments_rate_ok, comments_rate_info = self.check_rate_limits(user_id, 'comments', db)
            
            # Get behavior info
            behavior_info = self.check_user_behavior(user_id, db)
            
            return {
                'user_id': user_id,
                'limits': {
                    'posts': posts_rate_info,
                    'comments': comments_rate_info
                },
                'behavior': behavior_info,
                'can_post': posts_rate_ok and not behavior_info['is_suspicious'],
                'can_comment': comments_rate_ok and not behavior_info['is_suspicious']
            }
        except Exception as e:
            print(f"Error getting user limits: {e}")
            return {
                'user_id': user_id,
                'error': str(e),
                'can_post': True,
                'can_comment': True
            }

# Global instance
spam_detector = SpamDetectionService()
