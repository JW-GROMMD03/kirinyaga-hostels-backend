from rest_framework import status, generics
from django.core.paginator import Paginator
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import secrets
import json
import logging
import random
from .models import User, AuditLog, PasswordResetToken, TwoFactorOTP
from .serializers import (
    StudentSignupSerializer, OwnerSignupSerializer,
    StudentLoginSerializer, ResendVerificationSerializer, OwnerLoginSerializer, AdminLoginSerializer,
    VerifyEmailSerializer, PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    TwoFactorOTPRequestSerializer, TwoFactorOTPVerifySerializer,
    TwoFactorEnableSerializer, TwoFactorDisableSerializer,
    UserSerializer, SupportSerializer
)

logger = logging.getLogger(__name__)


def rate_limit_key_by_email_or_ip(group, request):
    """
    Custom rate limit key: uses email if available, otherwise IP.
    This ensures rate limits are per user, not per IP.
    """
    # Try to get email from request body
    email = None
    try:
        if request.body:
            body = json.loads(request.body.decode('utf-8'))
            email = body.get('email', '').lower().strip()
    except:
        pass
    
    # Get portal from URL
    if 'admin/login' in request.path:
        portal = 'admin'
    elif 'owner/login' in request.path:
        portal = 'owner'
    elif 'student/login' in request.path:
        portal = 'student'
    else:
        portal = 'auth'
    
    if email:
        return f"{portal}_{email}"
    return f"{portal}_{get_client_ip(request)}"

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# -------------------- Student Signup --------------------
class StudentSignupView(APIView):
    permission_classes = [AllowAny]
    
    @method_decorator(ratelimit(key='ip', rate='3/h', method='POST', block=True))
    def post(self, request):
        serializer = StudentSignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            AuditLog.objects.create(
                user=user,
                action='STUDENT_SIGNUP',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )
            return Response({
                'message': 'Registration successful. Please check your email for verification.',
                'email': user.email
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# -------------------- Owner Signup --------------------
class OwnerSignupView(APIView):
    permission_classes = [AllowAny]
    
    @method_decorator(ratelimit(key='ip', rate='3/h', method='POST', block=True))
    def post(self, request):
        serializer = OwnerSignupSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            AuditLog.objects.create(
                user=user,
                action='OWNER_SIGNUP',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email, 'hostel_name': request.data.get('hostel_name')}
            )
            return Response({
                'message': 'Registration successful. Please check your email for verification. Your account will be reviewed by admin.',
                'email': user.email
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# -------------------- Student Login --------------------
class StudentLoginView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key=rate_limit_key_by_email_or_ip, rate='5/m', method='POST', block=True))
    def post(self, request):
        serializer = StudentLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # CRITICAL SECURITY FIX: Only allow students to log in
            if user.role != 'student':
                AuditLog.objects.create(
                    user=user,
                    action='LOGIN_FAILED_WRONG_PORTAL',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'email': user.email, 'attempted_role': 'student', 'actual_role': user.role}
                )
                return Response({'error': 'This account is not a student account. Please use the correct login portal.'}, 
                                status=status.HTTP_403_FORBIDDEN)
            
            user.last_login = timezone.now()
            user.last_login_ip = get_client_ip(request)
            user.save()

            refresh = RefreshToken.for_user(user)
            refresh['role'] = user.role
            refresh['email'] = user.email

            response = Response()
            response.set_cookie(
                key='refresh_token',
                value=str(refresh),
                httponly=True,
                secure=not request.META.get('HTTP_HOST', '').startswith('localhost'),
                samesite='Lax',
                max_age=30 * 24 * 3600 if request.data.get('remember') else None
            )

            AuditLog.objects.create(
                user=user,
                action='LOGIN_SUCCESS',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            response.data = {
                'access': str(refresh.access_token),
                'role': user.role,
                'requires_2fa_setup': not user.is_2fa_enabled,
                'email': user.email,
                'full_name': user.full_name
            }
            return response

        AuditLog.objects.create(
            user=None,
            action='LOGIN_FAILED',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'email': request.data.get('email')}
        )
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

# -------------------- Owner Login --------------------
class OwnerLoginView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True))
    def post(self, request):
        serializer = OwnerLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # CRITICAL SECURITY FIX: Only allow owners to log in
            if user.role != 'owner':
                AuditLog.objects.create(
                    user=user,
                    action='LOGIN_FAILED_WRONG_PORTAL',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'email': user.email, 'attempted_role': 'owner', 'actual_role': user.role}
                )
                return Response({'error': 'This account is not an owner account. Please use the correct login portal.'}, 
                                status=status.HTTP_403_FORBIDDEN)
            
            # Also check if owner is approved
            if hasattr(user, 'owner_profile') and not user.owner_profile.is_approved:
                return Response({'error': 'Your account is pending admin approval. Please wait for verification.'}, 
                                status=status.HTTP_403_FORBIDDEN)
            
            user.last_login = timezone.now()
            user.last_login_ip = get_client_ip(request)
            user.save()

            refresh = RefreshToken.for_user(user)
            refresh['role'] = user.role
            refresh['email'] = user.email

            response = Response()
            response.set_cookie(
                key='refresh_token',
                value=str(refresh),
                httponly=True,
                secure=not request.META.get('HTTP_HOST', '').startswith('localhost'),
                samesite='Lax',
                max_age=30 * 24 * 3600 if request.data.get('remember') else None
            )

            AuditLog.objects.create(
                user=user,
                action='LOGIN_SUCCESS',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            response.data = {
                'access': str(refresh.access_token),
                'role': user.role,
                'requires_2fa_setup': not user.is_2fa_enabled,
                'email': user.email,
                'full_name': user.full_name
            }
            return response

        AuditLog.objects.create(
            user=None,
            action='LOGIN_FAILED',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'email': request.data.get('email')}
        )
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

# -------------------- Admin Login --------------------
class AdminLoginView(APIView):
    permission_classes = [AllowAny]

    def dispatch(self, request, *args, **kwargs):
        """Add CORS headers to response"""
        response = super().dispatch(request, *args, **kwargs)
        response['Access-Control-Allow-Origin'] = 'https://kirinyaga-hostels-frontend.onrender.com'
        response['Access-Control-Allow-Credentials'] = 'true'
        response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response

    def options(self, request, *args, **kwargs):
        """Handle preflight OPTIONS requests"""
        return Response(status=status.HTTP_200_OK)
    
    @method_decorator(ratelimit(key='ip', rate='5/m', method='POST', block=True))
    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # CRITICAL SECURITY FIX: Only allow admins to log in
            if user.role != 'admin' and not user.is_superuser:
                AuditLog.objects.create(
                    user=user,
                    action='LOGIN_FAILED_WRONG_PORTAL',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'email': user.email, 'attempted_role': 'admin', 'actual_role': user.role}
                )
                return Response({'error': 'This account is not an admin account. Please use the correct login portal.'}, 
                                status=status.HTTP_403_FORBIDDEN)
            
            user.last_login = timezone.now()
            user.last_login_ip = get_client_ip(request)
            user.save()

            refresh = RefreshToken.for_user(user)
            refresh['role'] = user.role
            refresh['email'] = user.email

            response = Response()
            response.set_cookie(
                key='refresh_token',
                value=str(refresh),
                httponly=True,
                secure=not request.META.get('HTTP_HOST', '').startswith('localhost'),
                samesite='Lax',
                max_age=30 * 24 * 3600 if request.data.get('remember') else None
            )

            AuditLog.objects.create(
                user=user,
                action='LOGIN_SUCCESS',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            response.data = {
                'access': str(refresh.access_token),
                'role': user.role,
                'requires_2fa_setup': not user.is_2fa_enabled,
                'email': user.email,
                'full_name': user.full_name
            }
            return response

        AuditLog.objects.create(
            user=None,
            action='LOGIN_FAILED',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'email': request.data.get('email')}
        )
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

# -------------------- Email Verification --------------------
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            user.email_verified = True
            user.email_verification_token = ''
            user.save()
            return Response({'message': 'Email verified successfully. You can now log in.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResendVerificationView(APIView):
    permission_classes = [AllowAny]
    
    @method_decorator(ratelimit(key='ip', rate='3/h', method='POST', block=True))
    def post(self, request):
        email = request.data.get('email')
        try:
            user = User.objects.get(email=email)
            if not user.email_verified:
                user.send_verification_email()
                return Response({'message': 'Verification email sent. Please check your inbox.'})
            else:
                return Response({'message': 'Email already verified.'}, status=status.HTTP_400_BAD_REQUEST)
        except User.DoesNotExist:
            return Response({'message': 'If this email exists, a verification link has been sent.'})

# -------------------- Logout --------------------
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        response = Response({'message': 'Logged out successfully'})
        response.delete_cookie('refresh_token')
        return response

# -------------------- Password Reset --------------------
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key='ip', rate='3/h', method='POST', block=True))
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                token = secrets.token_urlsafe(32)
                expires_at = timezone.now() + timezone.timedelta(hours=1)
                PasswordResetToken.objects.create(
                    user=user,
                    token=token,
                    expires_at=expires_at
                )
                user.send_password_reset_email(token)
            except User.DoesNotExist:
                pass
            
            return Response({
                'message': 'If an account with that email exists, a password reset link has been sent.'
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ratelimit(key='ip', rate='5/h', method='POST', block=True))
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            reset_token = serializer.validated_data['reset_token']
            new_password = serializer.validated_data['new_password']
            
            user.set_password(new_password)
            user.save()
            
            reset_token.used = True
            reset_token.save()
            
            AuditLog.objects.create(
                user=user,
                action='PASSWORD_RESET',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )
            
            return Response({'message': 'Password has been reset successfully. You can now log in with your new password.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# -------------------- 2FA OTP (for login) --------------------
class TwoFactorOTPSendView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='3/h', method='POST', block=True))
    def post(self, request):
        serializer = TwoFactorOTPRequestSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user

            otp_code = f"{random.randint(100000, 999999)}"
            expires_at = timezone.now() + timezone.timedelta(minutes=10)

            TwoFactorOTP.objects.filter(user=user, used=False).update(used=True)
            TwoFactorOTP.objects.create(
                user=user,
                otp=otp_code,
                expires_at=expires_at
            )

            user.send_2fa_otp_email(otp_code)

            AuditLog.objects.create(
                user=user,
                action='2FA_OTP_SENT',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            return Response({'message': 'OTP sent to your email.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TwoFactorOTPVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='5/h', method='POST', block=True))
    def post(self, request):
        serializer = TwoFactorOTPVerifySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            otp_obj = serializer.validated_data['otp_obj']

            otp_obj.used = True
            otp_obj.save()

            return Response({'message': 'OTP verified successfully.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# -------------------- 2FA Management --------------------
class TwoFactorStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'is_2fa_enabled': request.user.is_2fa_enabled
        })

class TwoFactorEnableRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='3/h', method='POST', block=True))
    def post(self, request):
        serializer = TwoFactorEnableSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if user.is_2fa_enabled:
                return Response({'message': '2FA is already enabled.'}, status=status.HTTP_400_BAD_REQUEST)

            otp_code = f"{random.randint(100000, 999999)}"
            expires_at = timezone.now() + timezone.timedelta(minutes=10)

            TwoFactorOTP.objects.filter(user=user, used=False).update(used=True)
            TwoFactorOTP.objects.create(
                user=user,
                otp=otp_code,
                expires_at=expires_at
            )

            user.send_2fa_otp_email(otp_code)

            AuditLog.objects.create(
                user=user,
                action='2FA_ENABLE_REQUEST',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            return Response({'message': 'OTP sent to your email.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TwoFactorEnableConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='5/h', method='POST', block=True))
    def post(self, request):
        serializer = TwoFactorOTPVerifySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            otp_obj = serializer.validated_data['otp_obj']

            otp_obj.used = True
            otp_obj.save()

            user.is_2fa_enabled = True
            user.save()

            AuditLog.objects.create(
                user=user,
                action='2FA_ENABLED',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            return Response({'message': 'Two-factor authentication enabled successfully.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TwoFactorDisableView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='3/h', method='POST', block=True))
    def post(self, request):
        user = request.user
        if not user.is_2fa_enabled:
            return Response({'message': '2FA is not enabled.'}, status=status.HTTP_400_BAD_REQUEST)

        otp_code = f"{random.randint(100000, 999999)}"
        expires_at = timezone.now() + timezone.timedelta(minutes=10)

        TwoFactorOTP.objects.filter(user=user, used=False).update(used=True)
        TwoFactorOTP.objects.create(
            user=user,
            otp=otp_code,
            expires_at=expires_at
        )

        user.send_2fa_otp_email(otp_code)

        AuditLog.objects.create(
            user=user,
            action='2FA_DISABLE_REQUEST',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'email': user.email}
        )

        return Response({'message': 'OTP sent to your email. Use it to confirm disabling 2FA.'})

class TwoFactorDisableConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @method_decorator(ratelimit(key='user', rate='5/h', method='POST', block=True))
    def post(self, request):
        serializer = TwoFactorOTPVerifySerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user = request.user
            otp_obj = serializer.validated_data['otp_obj']

            otp_obj.used = True
            otp_obj.save()

            user.is_2fa_enabled = False
            user.save()

            AuditLog.objects.create(
                user=user,
                action='2FA_DISABLED',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'email': user.email}
            )

            return Response({'message': 'Two-factor authentication disabled successfully.'})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class OwnerActivityLogView(APIView):
    """Get activity logs for the current owner"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))
        
        # Get audit logs for this user
        logs = AuditLog.objects.filter(user=request.user).order_by('-timestamp')
        
        paginator = Paginator(logs, page_size)
        current_page = paginator.get_page(page)
        
        data = [{
            'id': log.id,
            'action': log.action,
            'timestamp': log.timestamp,
            'details': log.details
        } for log in current_page]
        
        return Response({
            'results': data,
            'total': paginator.count,
            'page': page,
            'page_size': page_size
        })

# -------------------- User Profile --------------------
class UserProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

# -------------------- Support / Feedback --------------------
class SupportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SupportSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            user = request.user

            subject = f"Support Request: {data['type']} - {data['subject']}"
            message = f"""
From: {user.full_name} ({user.email})
Type: {data['type']}
Subject: {data['subject']}
Message:
{data['message']}
            """

            admin_emails = list(User.objects.filter(is_superuser=True).values_list('email', flat=True))

            if not admin_emails:
                admin_emails = [settings.ADMIN_EMAIL] if hasattr(settings, 'ADMIN_EMAIL') else []

            if admin_emails:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    admin_emails,
                    fail_silently=False,
                )
                return Response({'status': 'sent'}, status=status.HTTP_200_OK)
            else:
                return Response({'error': 'No admin email configured'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class AdminProfileView(APIView):
    """Get admin profile information"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Only allow admin users
        if request.user.role != 'admin' and not request.user.is_superuser:
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        
        return Response({
            'id': str(request.user.id),
            'full_name': request.user.full_name,
            'email': request.user.email,
            'role': request.user.role,
            'is_superuser': request.user.is_superuser,
            'is_staff': request.user.is_staff,
        }, status=status.HTTP_200_OK)


class OwnerProfileUpdateView(APIView):
    """Update owner profile information"""
    permission_classes = [IsAuthenticated]

    def put(self, request):
        user = request.user
        
        # Only allow owners to update their own profile
        if user.role != 'owner':
            return Response({'error': 'Only owners can use this endpoint'}, status=403)
        
        data = request.data
        
        # Update name and email
        if 'full_name' in data:
            user.full_name = data['full_name']
        if 'email' in data:
            if User.objects.exclude(id=user.id).filter(email=data['email']).exists():
                return Response({'error': 'Email already in use'}, status=400)
            user.email = data['email']
        
        # Update password if provided
        if 'new_password' in data and data['new_password']:
            if not user.check_password(data.get('current_password', '')):
                return Response({'error': 'Current password is incorrect'}, status=400)
            user.set_password(data['new_password'])
        
        user.save()
        
        # Log the action
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE_OWNER_PROFILE',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'updated_fields': list(data.keys())}
        )
        
        return Response({
            'id': str(user.id),
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role
        })