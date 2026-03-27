import time
import logging
from django.utils import timezone
from django.http import JsonResponse
from django.conf import settings
from rest_framework import status
from .models import User, AuditLog

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Simple rate limiting middleware"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.rate_limit_cache = {}

    def __call__(self, request):
        # Skip for admin and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return self.get_response(request)

        # Get client IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        # Rate limiting for login attempts
        if request.path.endswith('/login/') and request.method == 'POST':
            cache_key = f"login_{ip}"
            current_time = time.time()
            
            # Clean old entries
            self.rate_limit_cache = {k: v for k, v in self.rate_limit_cache.items() 
                                    if current_time - v['timestamp'] < 3600}
            
            if cache_key in self.rate_limit_cache:
                attempts = self.rate_limit_cache[cache_key]['attempts']
                if attempts >= 5:
                    return JsonResponse(
                        {'error': 'Too many login attempts. Please try again later.'},
                        status=429
                    )
                self.rate_limit_cache[cache_key]['attempts'] += 1
                self.rate_limit_cache[cache_key]['timestamp'] = current_time
            else:
                self.rate_limit_cache[cache_key] = {'attempts': 1, 'timestamp': current_time}

        response = self.get_response(request)
        return response


class SingleSessionMiddleware:
    """Enforce single session per user"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            current_session_key = request.session.session_key
            stored_session_key = request.user.current_session_token
            
            if stored_session_key and stored_session_key != current_session_key:
                # Another session exists, logout this one
                from django.contrib.auth import logout
                logout(request)
                return JsonResponse(
                    {'error': 'Another session is active. Please login again.'},
                    status=401
                )
            
            # Update session token if needed
            if stored_session_key != current_session_key:
                request.user.current_session_token = current_session_key
                request.user.last_session_created = timezone.now()
                request.user.save(update_fields=['current_session_token', 'last_session_created'])

        return self.get_response(request)


class IPWhitelistMiddleware:
    """
    Middleware to restrict admin access to specific IP addresses.
    UPDATED: Fixed to handle OPTIONS requests for CORS preflight
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle OPTIONS requests (CORS preflight) - always allow
        if request.method == 'OPTIONS':
            response = self.get_response(request)
            # Add CORS headers to OPTIONS response
            response['Access-Control-Allow-Origin'] = 'https://kirinyaga-hostels-frontend.onrender.com'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-CSRFToken'
            return response
        
        # Get client IP
        client_ip = self.get_client_ip(request)
        
        # Admin paths to protect (including API admin endpoints)
        admin_paths = [
            '/api/admin/',
            '/admin/',
            '/api/admin-dashboard/',
            '/admin-dashboard/',
        ]
        
        # Also check for admin login endpoints - allow them to be accessed even if IP not whitelisted
        # This is critical because the user isn't authenticated yet at login time
        admin_login_paths = [
            '/api/auth/admin/login/',
            '/api/auth/login/',
        ]
        
        # Check if this is an admin login attempt
        is_admin_login = any(request.path == path for path in admin_login_paths) or \
                         any(request.path.startswith(path) for path in admin_login_paths)
        
        # Check if the request path is for admin (excluding login)
        is_admin_path = any(request.path.startswith(path) for path in admin_paths) and not is_admin_login
        
        # Only check for admin paths (not login)
        if not is_admin_path:
            return self.get_response(request)
        
        # Get whitelisted IPs from settings
        whitelisted_ips = getattr(settings, 'ADMIN_ALLOWED_IPS', [])
        
        # Clean up any empty strings
        whitelisted_ips = [ip.strip() for ip in whitelisted_ips if ip and ip.strip()]
        
        # If no whitelist configured, allow all (with logging)
        if not whitelisted_ips:
            # Still log admin access for audit
            if request.user.is_authenticated:
                logger.info(f"Admin access from IP {client_ip} (no whitelist configured)")
            return self.get_response(request)
        
        # Check if IP is whitelisted
        if client_ip not in whitelisted_ips:
            logger.warning(f"⚠️ IP BLOCKED: {client_ip} attempted to access {request.path}")
            
            # Log the denied access to audit log
            try:
                if request.user.is_authenticated:
                    AuditLog.objects.create(
                        user=request.user,
                        action='ADMIN_ACCESS_DENIED_IP',
                        ip_address=client_ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        details={
                            'path': request.path,
                            'method': request.method,
                            'reason': 'IP not whitelisted',
                            'whitelisted_ips': whitelisted_ips
                        }
                    )
                else:
                    # Log anonymous attempt
                    AuditLog.objects.create(
                        user=None,
                        action='ADMIN_ACCESS_DENIED_IP_ANONYMOUS',
                        ip_address=client_ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        details={
                            'path': request.path,
                            'method': request.method,
                            'reason': 'IP not whitelisted (unauthenticated)',
                            'whitelisted_ips': whitelisted_ips
                        }
                    )
            except Exception as e:
                logger.error(f"Failed to log IP denial: {e}")
            
            # Return 403 Forbidden with JSON response
            return JsonResponse({
                'error': 'Access Denied',
                'message': 'Your IP address is not authorized to access the admin panel.',
                'ip': client_ip,
                'contact': 'Please contact the system administrator if you believe this is an error.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # IP is whitelisted - allow access
        if request.user.is_authenticated:
            logger.info(f"✅ Admin access allowed from whitelisted IP: {client_ip}")
        
        return self.get_response(request)
    
    def get_client_ip(self, request):
        """Get the client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class AdminActivityMiddleware:
    """
    Middleware to log all admin activity.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Process the request first
        response = self.get_response(request)
        
        # Only log for authenticated admin users
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser or request.user.role == 'admin'):
            # Skip static files and certain paths
            skip_paths = ['/static/', '/media/', '/admin/jsi18n/']
            if any(request.path.startswith(path) for path in skip_paths):
                return response
            
            # Log only non-GET requests (POST, PUT, DELETE, etc.)
            if request.method != 'GET':
                try:
                    # Get client IP
                    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                    if x_forwarded_for:
                        ip = x_forwarded_for.split(',')[0]
                    else:
                        ip = request.META.get('REMOTE_ADDR')
                    
                    # Log to audit log
                    AuditLog.objects.create(
                        user=request.user,
                        action=f"ADMIN_{request.method}_{request.path.replace('/', '_')}",
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        details={
                            'path': request.path,
                            'method': request.method,
                            'data': request.POST.dict() if request.method == 'POST' else {},
                            'status_code': response.status_code
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to log admin activity: {e}")
        
        return response


class MaintenanceModeMiddleware:
    """
    Middleware to put the site in maintenance mode.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if maintenance mode is enabled
        maintenance_mode = getattr(settings, 'MAINTENANCE_MODE', False)
        
        if maintenance_mode:
            # Allow access to admin and maintenance paths
            allowed_paths = ['/admin/', '/api/admin/', '/maintenance/', '/login/']
            if not any(request.path.startswith(path) for path in allowed_paths):
                return JsonResponse({
                    'error': 'Maintenance Mode',
                    'message': 'The system is currently under maintenance. Please try again later.',
                    'estimated_time': getattr(settings, 'MAINTENANCE_ESTIMATED_TIME', '30 minutes')
                }, status=503)
        
        return self.get_response(request)