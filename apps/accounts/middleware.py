import time
import logging
import json
from django.utils import timezone
from django.http import JsonResponse
from django.conf import settings
from rest_framework import status
from .models import User, AuditLog

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Get client IP address with fallback"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    
    # Return default if no IP found
    if not ip:
        ip = '0.0.0.0'
    return ip


class AuditLogMiddleware:
    """
    Automatically log ALL user actions across the system.
    This middleware captures every request made by authenticated users.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
    def __call__(self, request):
        # Skip logging for static/media files and certain paths
        skip_paths = ['/static/', '/media/', '/admin/jsi18n/', '/favicon.ico']
        if any(request.path.startswith(path) for path in skip_paths):
            return self.get_response(request)
        
        # Get client IP
        ip_address = get_client_ip(request)
        
        # Determine action based on URL and method
        action, category, resource_type, resource_id = self.determine_action(request)
        
        # Get request body for POST/PUT/PATCH
        request_body = None
        if request.method in ['POST', 'PUT', 'PATCH'] and request.body:
            try:
                # Try to parse as JSON
                request_body = json.loads(request.body) if request.body else None
                # Don't log passwords
                if request_body and isinstance(request_body, dict):
                    if 'password' in request_body:
                        request_body['password'] = '********'
                    if 'new_password' in request_body:
                        request_body['new_password'] = '********'
                    if 'password_confirm' in request_body:
                        request_body['password_confirm'] = '********'
            except:
                request_body = str(request.body)[:500]
        
        # Process the request
        response = self.get_response(request)
        
        # Log if user is authenticated OR it's an auth action
        should_log = (
            (request.user and request.user.is_authenticated) or
            category == 'auth' or
            request.method in ['POST', 'PUT', 'DELETE']  # Log all write operations
        )
        
        if should_log:
            try:
                # Don't log every single GET request to avoid clutter
                if request.method == 'GET' and category not in ['auth', 'admin']:
                    # Only log important GET requests (like viewing hostels)
                    if not any(x in request.path for x in ['/api/hostels/', '/api/hostel/']):
                        return response
                
                # Create audit log entry
                AuditLog.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    action=action,
                    action_category=category,
                    ip_address=ip_address,
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                    request_method=request.method,
                    response_status=response.status_code,
                    session_id=request.session.session_key,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details={
                        'path': request.path,
                        'query_params': dict(request.GET.items()),
                        'method': request.method,
                        'request_body': request_body,
                        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:200],
                        'response_status': response.status_code,
                    }
                )
            except Exception as e:
                logger.error(f"Failed to create audit log: {e}")
        
        return response
    
    def determine_action(self, request):
        """Determine action name, category, resource type based on URL path"""
        path = request.path
        method = request.method
        
        # Default values
        action = f"{method} {path}"
        category = 'system'
        resource_type = None
        resource_id = None
        
        # Extract resource ID from path if present (UUID pattern)
        path_parts = path.strip('/').split('/')
        for i, part in enumerate(path_parts):
            # UUID pattern detection (simple check for length and dashes)
            if len(part) > 20 and '-' in part and len(part) < 40:
                resource_id = part
                if i > 0:
                    resource_type = path_parts[i-1].capitalize()
                break
        
        # Authentication actions
        if '/api/auth/' in path or '/login' in path or '/signup' in path:
            category = 'auth'
            if 'student/login' in path or 'owner/login' in path or 'admin/login' in path or '/login' in path:
                if method == 'POST':
                    action = 'LOGIN'
                else:
                    action = 'LOGIN_ATTEMPT'
            elif 'logout' in path:
                action = 'LOGOUT'
            elif 'student/signup' in path or 'student/register' in path:
                action = 'STUDENT_SIGNUP'
            elif 'owner/signup' in path or 'owner/register' in path:
                action = 'OWNER_SIGNUP'
            elif 'verify-email' in path:
                action = 'VERIFY_EMAIL'
            elif 'resend-verification' in path:
                action = 'RESEND_VERIFICATION'
            elif 'reset-password' in path or 'password-reset' in path:
                if 'request' in path or method == 'POST':
                    action = 'PASSWORD_RESET_REQUEST'
                else:
                    action = 'PASSWORD_RESET_CONFIRM'
            elif '2fa' in path or 'two-factor' in path:
                if 'enable' in path:
                    action = '2FA_ENABLE'
                elif 'disable' in path:
                    action = '2FA_DISABLE'
                elif 'verify' in path:
                    action = '2FA_VERIFY'
                else:
                    action = '2FA_OTP_SENT'
        
        # Hostel actions
        elif '/api/hostels/' in path:
            category = 'hostel'
            resource_type = 'Hostel'
            
            if method == 'GET':
                if len(path_parts) > 3 and path_parts[3] and len(path_parts[3]) > 20:
                    action = 'VIEW_HOSTEL_DETAIL'
                else:
                    action = 'VIEW_HOSTELS_LIST'
            elif method == 'POST':
                action = 'CREATE_HOSTEL'
            elif method == 'PUT' or method == 'PATCH':
                action = 'UPDATE_HOSTEL'
            elif method == 'DELETE':
                action = 'DELETE_HOSTEL'
        
        # Owner hostel management
        elif '/api/owner/hostels/' in path:
            category = 'hostel'
            resource_type = 'Hostel'
            if method == 'GET':
                action = 'VIEW_OWNER_HOSTELS'
            elif method == 'POST':
                action = 'CREATE_HOSTEL'
            elif method == 'PUT' or method == 'PATCH':
                action = 'UPDATE_HOSTEL'
            elif method == 'DELETE':
                action = 'DELETE_HOSTEL'
        
        # Saved hostels
        elif '/api/saved-hostels/' in path:
            category = 'hostel'
            resource_type = 'SavedHostel'
            if method == 'POST':
                action = 'SAVE_HOSTEL'
            elif method == 'DELETE':
                action = 'UNSAVE_HOSTEL'
            elif method == 'GET':
                action = 'VIEW_SAVED_HOSTELS'
        
        # Booking actions
        elif '/api/bookings/' in path:
            category = 'booking'
            resource_type = 'Booking'
            if method == 'POST':
                action = 'CREATE_BOOKING'
            elif method == 'PUT' or method == 'PATCH':
                action = 'UPDATE_BOOKING'
            elif method == 'DELETE':
                action = 'CANCEL_BOOKING'
            elif method == 'GET':
                action = 'VIEW_BOOKINGS'
        
        # Review actions
        elif '/api/reviews/' in path:
            category = 'review'
            resource_type = 'Review'
            if method == 'POST':
                action = 'CREATE_REVIEW'
            elif method == 'PUT' or method == 'PATCH':
                action = 'UPDATE_REVIEW'
            elif method == 'DELETE':
                action = 'DELETE_REVIEW'
            elif method == 'GET':
                action = 'VIEW_REVIEWS'
        
        # Profile actions
        elif '/api/profile/' in path or '/api/user/' in path:
            category = 'profile'
            resource_type = 'User'
            if method == 'PUT' or method == 'PATCH':
                action = 'UPDATE_PROFILE'
            elif method == 'GET':
                action = 'VIEW_PROFILE'
        
        # Admin actions
        elif '/api/admin/' in path or path.startswith('/admin/'):
            category = 'admin'
            if 'approve' in path.lower():
                if 'owner' in path.lower():
                    action = 'ADMIN_APPROVE_OWNER'
                elif 'hostel' in path.lower():
                    action = 'ADMIN_APPROVE_HOSTEL'
                else:
                    action = 'ADMIN_APPROVE'
            elif 'reject' in path.lower():
                action = 'ADMIN_REJECT'
            elif 'delete' in path.lower():
                action = 'ADMIN_DELETE'
            elif 'block' in path.lower() or 'unblock' in path.lower() or 'toggle-status' in path.lower():
                action = 'ADMIN_TOGGLE_USER_STATUS'
            elif 'settings' in path.lower():
                action = 'ADMIN_UPDATE_SETTINGS'
            elif 'dashboard' in path.lower():
                action = 'ADMIN_VIEW_DASHBOARD'
            elif 'stats' in path.lower():
                action = 'ADMIN_VIEW_STATS'
            else:
                action = f"ADMIN_{method}_{path_parts[-1] if path_parts else 'ACTION'}"
        
        # Payment actions
        elif '/api/payments/' in path or '/api/mpesa/' in path:
            category = 'payment'
            resource_type = 'Payment'
            if method == 'POST':
                action = 'INITIATE_PAYMENT'
            elif method == 'GET':
                action = 'VIEW_PAYMENT'
        
        # Support/feedback
        elif '/api/support/' in path:
            category = 'system'
            action = 'SUPPORT_REQUEST'
        
        return action, category, resource_type, resource_id


class RateLimitMiddleware:
    """
    Rate limiting middleware that tracks attempts per USER (email) and per PORTAL.
    Now uses DATABASE User model instead of in-memory cache.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for admin and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return self.get_response(request)

        # Only rate limit login endpoints
        if '/login/' in request.path and request.method == 'POST':
            return self.handle_login_rate_limit(request)
        
        return self.get_response(request)
    
    def handle_login_rate_limit(self, request):
        """Handle rate limiting for login attempts - now uses database User model"""
        ip = get_client_ip(request)
        
        # Determine portal type from URL
        if 'admin/login' in request.path:
            portal = 'admin'
            max_attempts = getattr(settings, 'ADMIN_MAX_ATTEMPTS', 3)
        elif 'owner/login' in request.path:
            portal = 'owner'
            max_attempts = getattr(settings, 'MAX_LOGIN_ATTEMPTS', 5)
        elif 'student/login' in request.path:
            portal = 'student'
            max_attempts = getattr(settings, 'MAX_LOGIN_ATTEMPTS', 5)
        else:
            portal = 'auth'
            max_attempts = 5
        
        # Try to get email from request body
        email = None
        try:
            if request.body:
                body = json.loads(request.body.decode('utf-8'))
                email = body.get('email', '').lower().strip()
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            pass
        
        # If we have an email, check the User model's failed_login_attempts
        if email:
            try:
                from .models import User
                user = User.objects.get(email=email)
                
                # Check if user is already locked in database
                if user.locked_until and user.locked_until > timezone.now():
                    remaining = user.locked_until - timezone.now()
                    logger.warning(f"User {email} is locked until {user.locked_until}")
                    return JsonResponse({
                        'error': f'Account locked. Try again in {remaining.seconds // 60} minutes.',
                        'locked': True,
                        'remaining_seconds': remaining.seconds
                    }, status=429)
                
                # Check if user has exceeded max attempts
                if user.failed_login_attempts >= max_attempts:
                    # Lock the account in database
                    lockout_hours = getattr(settings, 'LOCKOUT_HOURS', 1)
                    user.locked_until = timezone.now() + timezone.timedelta(hours=lockout_hours)
                    user.save()
                    
                    logger.warning(f"Rate limit exceeded for {email} on {portal} portal - LOCKED FOR {lockout_hours} HOUR(S)")
                    
                    AuditLog.objects.create(
                        user=user,
                        action='RATE_LIMIT_EXCEEDED',
                        action_category='auth',
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        details={
                            'portal': portal,
                            'email': email,
                            'attempts': user.failed_login_attempts,
                            'max_attempts': max_attempts,
                            'locked_for_hours': lockout_hours
                        }
                    )
                    
                    return JsonResponse({
                        'error': f'Too many login attempts. Account locked for {lockout_hours} hour(s).',
                        'locked': True,
                        'portal': portal,
                        'max_attempts': max_attempts,
                        'lockout_hours': lockout_hours
                    }, status=429)
                    
            except User.DoesNotExist:
                pass  # User not found, let the view handle it
        
        # Allow the request to proceed
        return self.get_response(request)

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
                
                # Log session conflict
                try:
                    AuditLog.objects.create(
                        user=request.user,
                        action='SESSION_CONFLICT',
                        ip_address=get_client_ip(request),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        details={
                            'current_session': current_session_key,
                            'stored_session': stored_session_key,
                            'action_taken': 'logout'
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to log session conflict: {e}")
                
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
        client_ip = get_client_ip(request)
        
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
                    ip = get_client_ip(request)
                    
                    # Log to audit log
                    AuditLog.objects.create(
                        user=request.user,
                        action=f"ADMIN_{request.method}_{request.path.replace('/', '_')}",
                        action_category='admin',
                        ip_address=ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        request_method=request.method,
                        response_status=response.status_code,
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
    Puts the entire site into maintenance mode when an admin flips the switch.
    Regular users see a friendly maintenance page while admins can still access
    everything to make changes or turn it back off.
    
    The maintenance status is stored in the database so it survives server restarts,
    and we check it on every request to make sure it's always accurate.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip the check entirely if we're already on the maintenance page itself
        # (prevents redirect loops)
        if request.path.startswith('/maintenance') or request.path.startswith('/api/maintenance'):
            return self.get_response(request)
        
        # Handle OPTIONS requests (CORS preflight) - always allow these through
        if request.method == 'OPTIONS':
            response = self.get_response(request)
            response['Access-Control-Allow-Origin'] = 'https://kirinyaga-hostels-frontend.onrender.com'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-CSRFToken'
            return response
        
        # Grab the system settings from the database to see if maintenance is on
        try:
            from apps.accounts.models import SystemSettings
            settings_obj = SystemSettings.get_settings()
            maintenance_mode = settings_obj.maintenance_mode
            maintenance_message = getattr(settings_obj, 'maintenance_message', '')
            estimated_time = getattr(settings_obj, 'maintenance_estimated_time', '')
        except Exception as e:
            # If we can't reach the database for some reason, fall back to False
            # Better to let the site work than block everyone unnecessarily
            logger.error(f"Failed to check maintenance mode from database: {e}")
            maintenance_mode = getattr(settings, 'MAINTENANCE_MODE', False)
            maintenance_message = ''
            estimated_time = ''
        
        # If maintenance is off, everyone can proceed normally
        if not maintenance_mode:
            return self.get_response(request)
        
        # Maintenance mode is ON - now we need to decide who gets through
        
        # Rule 1: Admin users can always access everything
        # They need to be able to turn maintenance off or make fixes
        if request.user.is_authenticated:
            if request.user.role == 'admin' or request.user.is_superuser or request.user.is_staff:
                return self.get_response(request)
        
        # Rule 2: Certain paths are always allowed even during maintenance
        allowed_paths = [
            '/admin/',
            '/api/admin/',
            '/api/auth/admin/',
            '/api/auth/login/',
            '/api/auth/logout/',
            '/static/',
            '/media/',
        ]
        
        for allowed in allowed_paths:
            if request.path.startswith(allowed):
                return self.get_response(request)
        
        # Rule 3: Everyone else gets blocked and sees the maintenance message
        
        # Check if this is an API request (expects JSON) or a browser request (expects HTML)
        is_api_request = request.path.startswith('/api/') or \
                         request.headers.get('Accept') == 'application/json' or \
                         request.headers.get('Content-Type') == 'application/json'
        
        if is_api_request:
            # API clients get a clean JSON response
            return JsonResponse({
                'error': 'Maintenance Mode',
                'message': maintenance_message or 'Kirinyaga Hostels is currently undergoing scheduled maintenance. We\'ll be back shortly!',
                'estimated_time': estimated_time or 'a few minutes',
                'maintenance': True
            }, status=503)
        else:
            # Browser users get redirected to the friendly maintenance page
            from django.shortcuts import redirect
            return redirect('/maintenance.html')