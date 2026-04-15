import cloudinary
import cloudinary.uploader
import cloudinary.api
import logging
from datetime import timedelta, datetime
from django.utils import timezone
from django.db.models import Q, Count, Sum, Avg, F
from django.core.paginator import Paginator
from django.db import connection
from django.conf import settings
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.sessions.models import Session
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import api_view, permission_classes

from .models import User, StudentProfile, HostelOwnerProfile, AuditLog, AdminNotification, SystemSettings
from .serializers import (
    UserSerializer, AdminStudentSerializer, AdminOwnerSerializer,
    AdminHostelSerializer, AdminSubscriptionPlanSerializer,
    AdminOwnerSubscriptionSerializer, 
    AdminConversationSerializer, AdminMessageSerializer,
    AdminNotificationSerializer, SystemSettingsSerializer
)
from apps.hostels.models import Hostel, HostelImage, Amenity, SavedHostel
from apps.hostels.serializers import HostelSerializer, HostelDetailSerializer, AmenitySerializer
from apps.subscriptions.models import SubscriptionPlan, OwnerSubscription
from apps.subscriptions.serializers import (
    SubscriptionPlanSerializer, 
    OwnerSubscriptionSerializer
)
from apps.chat.models import Conversation, Message
from apps.chat.serializers import ConversationSerializer, MessageSerializer
from apps.notifications.models import Notification, NewsletterSubscriber
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.utils import send_sms
from apps.notifications.models import Announcement 

logger = logging.getLogger(__name__)

# Optional apps - check if they exist
try:
    from apps.bookings.models import Booking
    from apps.bookings.serializers import BookingSerializer
    BOOKINGS_APP_EXISTS = True
except ImportError:
    BOOKINGS_APP_EXISTS = False
    # Create dummy classes if needed
    class Booking:
        objects = None
    class BookingSerializer:
        pass

try:
    from apps.reviews.models import Review
    from apps.reviews.serializers import ReviewSerializer
    REVIEWS_APP_EXISTS = True
except ImportError:
    REVIEWS_APP_EXISTS = False
    class Review:
        objects = None
    class ReviewSerializer:
        pass

class AdminProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        avatar_url = None
        if hasattr(request.user, 'avatar') and request.user.avatar:
            avatar_url = request.user.avatar
        return Response({
            'id': str(request.user.id),
            'full_name': request.user.full_name,
            'email': request.user.email,
            'role': request.user.role,
            'is_superuser': request.user.is_superuser,
            'is_staff': request.user.is_staff,
            'avatar_url': avatar_url
        })

# Helper function to get client IP
def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# Custom permission for admin only
class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        # First check if user is authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        # Then check if user is admin or superuser
        return request.user.role == 'admin' or request.user.is_superuser

# ==================== DASHBOARD STATS ====================
class DashboardStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Date ranges
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        # User stats
        total_students = User.objects.filter(role='student').count()
        total_owners = User.objects.filter(role='owner').count()
        total_users = total_students + total_owners
        new_users_today = User.objects.filter(date_joined__gte=today_start).count()
        new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
        
        # Blocked users
        blocked_students = User.objects.filter(role='student', is_active=False).count()
        blocked_owners = User.objects.filter(role='owner', is_active=False).count()
        
        # User verification stats
        verified_users = User.objects.filter(email_verified=True).count()
        twofa_enabled = User.objects.filter(is_2fa_enabled=True).count()
        
        # Hostel stats
        total_hostels = Hostel.objects.count()
        pending_hostels = Hostel.objects.filter(is_approved=False).count()
        approved_hostels = Hostel.objects.filter(is_approved=True).count()
        featured_hostels = Hostel.objects.filter(is_featured=True).count()
        
        # Hostel stats by room type
        hostels_by_type = Hostel.objects.values('room_type').annotate(count=Count('id'))
        
        # Review stats
        total_reviews = Review.objects.count() if REVIEWS_APP_EXISTS and hasattr(Review, 'objects') else 0
        pending_reviews = Review.objects.filter(is_approved=False).count() if REVIEWS_APP_EXISTS and hasattr(Review, 'objects') else 0
        avg_rating = Review.objects.filter(is_approved=True).aggregate(Avg('rating'))['rating__avg'] or 0
        
        # Booking stats
        total_bookings = Booking.objects.count() if BOOKINGS_APP_EXISTS and hasattr(Booking, 'objects') else 0
        recent_bookings = Booking.objects.filter(created_at__gte=week_ago).count() if BOOKINGS_APP_EXISTS and hasattr(Booking, 'objects') else 0
        
        # Chat stats
        total_conversations = Conversation.objects.count()
        unread_messages = Message.objects.filter(is_read=False).exclude(sender=request.user).count()
        
        # Notification stats
        unread_notifications = Notification.objects.filter(is_read=False).count()
        
        # Fraud stats
        high_risk_users = 0
        try:
            high_risk_users += User.objects.filter(failed_login_attempts__gte=5).count()
            high_risk_users += User.objects.filter(
                role='owner',
                owner_profile__fraud_score__gte=70
            ).count()
        except Exception as e:
            high_risk_users = User.objects.filter(failed_login_attempts__gte=5).count()
            
        locked_accounts = User.objects.filter(locked_until__gte=now).count()
        

        # ========== FIXED: Recent Activity - LOAD LIVE DATA ==========
        recent_activity = AuditLog.objects.select_related('user').order_by('-timestamp')[:50]
        
        activity_data = []
        for log in recent_activity:
            # Use the new human-readable methods
            action_display = log.get_human_readable_action()
            
            # Get icon based on action category
            icon = '📌'
            if log.action_category == 'auth':
                if 'LOGIN_SUCCESS' in log.action:
                    icon = '✅'
                elif 'LOGIN_FAILED' in log.action:
                    icon = '❌'
                elif 'LOGOUT' in log.action:
                    icon = '🚪'
                else:
                    icon = '🔐'
            elif log.action_category == 'hostel':
                if 'CREATE' in log.action:
                    icon = '🏠'
                elif 'UPDATE' in log.action:
                    icon = '✏️'
                elif 'DELETE' in log.action:
                    icon = '🗑️'
                elif 'VIEW' in log.action:
                    icon = '👁️'
                elif 'APPROVE' in log.action:
                    icon = '✓'
                elif 'REJECT' in log.action:
                    icon = '✗'
                else:
                    icon = '🏠'
            elif log.action_category == 'booking':
                if 'CREATE' in log.action:
                    icon = '📅'
                elif 'CANCEL' in log.action:
                    icon = '🚫'
                else:
                    icon = '📅'
            elif log.action_category == 'review':
                icon = '⭐'
            elif log.action_category == 'profile':
                icon = '👤'
            elif log.action_category == 'payment':
                if 'SUCCESS' in log.action:
                    icon = '💰'
                elif 'FAILED' in log.action:
                    icon = '❌'
                else:
                    icon = '💳'
            elif log.action_category == 'admin':
                if 'IMPERSONATE' in log.action:
                    icon = '🕵️'
                elif 'DELETE' in log.action:
                    icon = '🗑️'
                elif 'TOGGLE' in log.action:
                    icon = '🔒'
                elif 'VERIFY' in log.action:
                    icon = '✓'
                else:
                    icon = '⚙️'
            elif log.action_category == 'view':
                icon = '👁️'
            
            # Build a clean summary
            summary = log.get_activity_summary()
            
            activity_data.append({
                'id': log.id,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'user': log.user.email if log.user else 'Anonymous',
                'user_name': log.user.full_name if log.user else 'System',
                'user_role': log.user.role if log.user else 'system',
                'action': action_display,
                'action_summary': summary,
                'action_code': log.action,
                'category': log.action_category or 'system',
                'icon': icon,
                'details': log.details,
                'ip_address': log.ip_address,
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
            })

        # Activity summary by category (last 7 days)
        activity_summary = {
            'auth': AuditLog.objects.filter(action_category='auth', timestamp__gte=week_ago).count(),
            'hostel': AuditLog.objects.filter(action_category='hostel', timestamp__gte=week_ago).count(),
            'booking': AuditLog.objects.filter(action_category='booking', timestamp__gte=week_ago).count(),
            'review': AuditLog.objects.filter(action_category='review', timestamp__gte=week_ago).count(),
            'admin': AuditLog.objects.filter(action_category='admin', timestamp__gte=week_ago).count(),
            'profile': AuditLog.objects.filter(action_category='profile', timestamp__gte=week_ago).count(),
            'view': AuditLog.objects.filter(action_category='view', timestamp__gte=week_ago).count(),
        }

        # User growth data for charts
        months = []
        student_growth = []
        owner_growth = []
        
        for i in range(5, -1, -1):
            month_date = now - timedelta(days=30 * i)
            month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            
            students_in_month = User.objects.filter(
                role='student',
                date_joined__lte=month_end
            ).count()
            
            owners_in_month = User.objects.filter(
                role='owner',
                date_joined__lte=month_end
            ).count()
            
            months.append(month_start.strftime('%b'))
            student_growth.append(students_in_month)
            owner_growth.append(owners_in_month)

        return Response({
            'users': {
                'total_users': total_users,
                'total_students': total_students,
                'total_owners': total_owners,
                'blocked_students': blocked_students,
                'blocked_owners': blocked_owners,
                'new_today': new_users_today,
                'new_week': new_users_week,
                'verified': verified_users,
                'twofa_enabled': twofa_enabled,
            },
            'hostels': {
                'total': total_hostels,
                'pending': pending_hostels,
                'approved': approved_hostels,
                'featured': featured_hostels,
                'by_type': list(hostels_by_type),
            },
            'reviews': {
                'total': total_reviews,
                'pending': pending_reviews,
                'avg_rating': float(avg_rating),
            },
            'bookings': {
                'total': total_bookings,
                'recent': recent_bookings,
            },
            'chat': {
                'total_conversations': total_conversations,
                'unread_messages': unread_messages,
            },
            'notifications': {
                'unread': unread_notifications,
            },
            'fraud': {
                'high_risk': high_risk_users,
                'locked': locked_accounts,
            },
            'recent_activity': activity_data,
            'activity_summary': activity_summary,
            'user_growth': {
                'labels': months,
                'students': student_growth,
                'owners': owner_growth,
            }
        })

# ==================== USER MANAGEMENT ====================
class StudentListView(generics.ListAPIView):
    """List all students with their profiles"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminStudentSerializer

    def get_queryset(self):
        queryset = User.objects.filter(role='student').select_related('student_profile').order_by('-date_joined')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_filter == 'locked':
            queryset = queryset.filter(is_active=False)
        elif status_filter == 'verified':
            queryset = queryset.filter(email_verified=True)
        elif status_filter == 'unverified':
            queryset = queryset.filter(email_verified=False)
            
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(student_profile__registration_number__icontains=search) |
                Q(student_profile__phone_number__icontains=search)
            )
            
        return queryset

class StudentDetailView(generics.RetrieveAPIView):
    """Get detailed student information"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminStudentSerializer
    queryset = User.objects.filter(role='student').select_related('student_profile')

class OwnerListView(generics.ListAPIView):
    """List all owners with their profiles"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminOwnerSerializer

    def get_queryset(self):
        queryset = User.objects.filter(role='owner').select_related('owner_profile').prefetch_related('owner_profile__room_types').order_by('-date_joined')
        
        # Filter by approval status
        approval = self.request.query_params.get('approval')
        if approval == 'approved':
            queryset = queryset.filter(owner_profile__is_approved=True)
        elif approval == 'pending':
            queryset = queryset.filter(owner_profile__is_approved=False)
            
        # Filter by verification
        verified = self.request.query_params.get('verified')
        if verified == 'true':
            queryset = queryset.filter(owner_profile__verified_badge=True)
        elif verified == 'false':
            queryset = queryset.filter(owner_profile__verified_badge=False)
            
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search) |
                Q(owner_profile__hostel_name__icontains=search) |
                Q(owner_profile__primary_phone__icontains=search)
            )
            
        return queryset

class OwnerDetailView(generics.RetrieveAPIView):
    """Get detailed owner information"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminOwnerSerializer
    queryset = User.objects.filter(role='owner').select_related('owner_profile')

class ToggleUserStatusView(APIView):
    """Lock or unlock a user account"""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.is_active = not user.is_active
            
            # Determine the action message
            if not user.is_active:
                action_message = f'User {user.email} has been BLOCKED by admin.'
                block_reason = request.data.get('reason', 'Suspicious activities detected')
                user.locked_until = timezone.now() + timedelta(days=365)  # Long lock for blocked users
            else:
                action_message = f'User {user.email} has been UNBLOCKED by admin.'
                user.locked_until = None
                user.failed_login_attempts = 0
            
            user.save()
            
            # Send notification to the user
            if hasattr(Notification, 'objects'):
                Notification.objects.create(
                    user=user,
                    type='account_status',
                    title='Account Status Update',
                    message=action_message,
                    link='/login.html'
                )
            
            AuditLog.objects.create(
                user=request.user,
                action='TOGGLE_USER_STATUS',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={
                    'user_id': str(user_id), 
                    'email': user.email, 
                    'new_status': user.is_active,
                    'blocked': not user.is_active
                }
            )
            
            return Response({
                'status': 'success', 
                'is_active': user.is_active,
                'message': f'User has been {"blocked" if not user.is_active else "unblocked"} successfully'
            })
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
class DeleteUserView(APIView):
    """Delete a user account"""
    permission_classes = [IsAdminUser]

    def delete(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            email = user.email
            role = user.role
            user.delete()
            
            AuditLog.objects.create(
                user=request.user,
                action='DELETE_USER',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'user_id': str(user_id), 'email': email, 'role': role}
            )
            
            return Response({'status': 'success'})
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

class ApproveOwnerView(APIView):
    """Approve a hostel owner"""
    permission_classes = [IsAdminUser]

    def post(self, request, owner_id):
        try:
            user = User.objects.get(id=owner_id, role='owner')
            profile = user.owner_profile
            profile.is_approved = True
            profile.approved_at = timezone.now()
            profile.approved_by = request.user
            profile.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='APPROVE_OWNER',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'owner_id': str(owner_id), 'email': user.email, 'hostel_name': profile.hostel_name}
            )
            
            if hasattr(Notification, 'objects'):
                Notification.objects.create(
                    user=user,
                    type='owner_approved',
                    title='Account Approved',
                    message=f'Your hostel owner account has been approved by admin. You can now log in and manage your hostels.',
                    link='/owner/dashboard.html'
                )
            
            return Response({'status': 'success'})
        except User.DoesNotExist:
            return Response({'error': 'Owner not found'}, status=404)

class RejectOwnerView(APIView):
    """Reject a hostel owner"""
    permission_classes = [IsAdminUser]

    def post(self, request, owner_id):
        try:
            user = User.objects.get(id=owner_id, role='owner')
            reason = request.data.get('reason', 'Your application was rejected.')
            
            AuditLog.objects.create(
                user=request.user,
                action='REJECT_OWNER',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'owner_id': str(owner_id), 'email': user.email, 'reason': reason}
            )
            
            user.delete()
            
            return Response({'status': 'success'})
        except User.DoesNotExist:
            return Response({'error': 'Owner not found'}, status=404)

class ToggleVerifiedBadgeView(APIView):
    """Toggle verified badge for owner"""
    permission_classes = [IsAdminUser]

    def post(self, request, owner_id):
        try:
            user = User.objects.get(id=owner_id, role='owner')
            profile = user.owner_profile
            profile.verified_badge = not profile.verified_badge
            profile.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='TOGGLE_VERIFIED_BADGE',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'owner_id': str(owner_id), 'email': user.email, 'new_status': profile.verified_badge}
            )
            
            return Response({'status': 'success', 'verified_badge': profile.verified_badge})
        except User.DoesNotExist:
            return Response({'error': 'Owner not found'}, status=404)

class UpdateFraudScoreView(APIView):
    """Update fraud score for a user"""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            new_score = request.data.get('fraud_score')
            if new_score is None:
                return Response({'error': 'fraud_score required'}, status=400)
                
            if user.role == 'owner' and hasattr(user, 'owner_profile'):
                profile = user.owner_profile
                old_score = profile.fraud_score
                profile.fraud_score = new_score
                profile.save()
                
                AuditLog.objects.create(
                    user=request.user,
                    action='UPDATE_FRAUD_SCORE',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'user_id': str(user_id), 'email': user.email, 'old_score': old_score, 'new_score': new_score}
                )
                
                return Response({'status': 'success', 'fraud_score': new_score})
            else:
                return Response({'error': 'Can only set fraud score for owners'}, status=400)
                
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

class UnlockUserView(APIView):
    """Manually unlock a locked user account"""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='UNLOCK_USER',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'user_id': str(user_id), 'email': user.email}
            )
            
            return Response({'status': 'success'})
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

class HighRiskUsersView(generics.ListAPIView):
    """Get users with high fraud score or multiple failed attempts"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminOwnerSerializer

    def get_queryset(self):
        # Get users with high failed attempts
        high_risk_by_attempts = User.objects.filter(failed_login_attempts__gte=5)
        
        # Get owners with high fraud score - this field EXISTS
        high_risk_owners = User.objects.filter(
            role='owner',
            owner_profile__fraud_score__gte=70
        )
        
        # Get locked users
        locked_users = User.objects.filter(locked_until__isnull=False)
        
        # Combine all querysets
        from itertools import chain
        combined = list(chain(high_risk_by_attempts, high_risk_owners, locked_users))
        
        # Remove duplicates by id
        seen = set()
        unique_users = []
        for user in combined:
            if user.id not in seen:
                seen.add(user.id)
                unique_users.append(user)
        
        return unique_users

# ==================== HOSTEL MANAGEMENT ====================
class AdminHostelListView(generics.ListAPIView):
    """List all hostels for admin"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminHostelSerializer

    def get_queryset(self):
        queryset = Hostel.objects.select_related('owner').prefetch_related('images', 'amenities', 'reviews').order_by('-created_at')
        
        # Filter by approval
        approval = self.request.query_params.get('approval')
        if approval == 'approved':
            queryset = queryset.filter(is_approved=True)
        elif approval == 'pending':
            queryset = queryset.filter(is_approved=False)
            
        # Filter by featured
        featured = self.request.query_params.get('featured')
        if featured == 'true':
            queryset = queryset.filter(is_featured=True)
        elif featured == 'false':
            queryset = queryset.filter(is_featured=False)
            
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(owner__email__icontains=search) |
                Q(address__icontains=search)
            )
            
        return queryset

class AdminHostelDetailView(generics.RetrieveAPIView):
    """Get detailed hostel information"""
    permission_classes = [IsAdminUser]
    serializer_class = HostelDetailSerializer
    queryset = Hostel.objects.all()

class AdminApproveHostelView(APIView):
    """Approve or reject a hostel"""
    permission_classes = [IsAdminUser]

    def post(self, request, hostel_id):
        try:
            hostel = Hostel.objects.get(id=hostel_id)
            approve = request.data.get('approve', True)
            hostel.is_approved = approve
            hostel.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='APPROVE_HOSTEL' if approve else 'REJECT_HOSTEL',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'hostel_id': str(hostel_id), 'name': hostel.name, 'approved': approve}
            )
            
            if hasattr(Notification, 'objects'):
                Notification.objects.create(
                    user=hostel.owner,
                    type='hostel_approved' if approve else 'hostel_rejected',
                    title=f'Hostel {"Approved" if approve else "Rejected"}',
                    message=f'Your hostel "{hostel.name}" has been {"approved" if approve else "rejected"} by admin.',
                    link='/owner/hostels.html'
                )
            
            return Response({'status': 'success', 'is_approved': hostel.is_approved})
        except Hostel.DoesNotExist:
            return Response({'error': 'Hostel not found'}, status=404)

class AdminToggleFeaturedView(APIView):
    """Toggle featured status for a hostel"""
    permission_classes = [IsAdminUser]

    def post(self, request, hostel_id):
        try:
            hostel = Hostel.objects.get(id=hostel_id)
            hostel.is_featured = not hostel.is_featured
            hostel.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='TOGGLE_FEATURED',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'hostel_id': str(hostel_id), 'name': hostel.name, 'featured': hostel.is_featured}
            )
            
            return Response({'status': 'success', 'is_featured': hostel.is_featured})
        except Hostel.DoesNotExist:
            return Response({'error': 'Hostel not found'}, status=404)

class AdminDeleteHostelView(APIView):
    """Delete a hostel"""
    permission_classes = [IsAdminUser]

    def delete(self, request, hostel_id):
        try:
            hostel = Hostel.objects.get(id=hostel_id)
            name = hostel.name
            hostel.delete()
            
            AuditLog.objects.create(
                user=request.user,
                action='DELETE_HOSTEL',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'hostel_id': str(hostel_id), 'name': name}
            )
            
            return Response({'status': 'success'})
        except Hostel.DoesNotExist:
            return Response({'error': 'Hostel not found'}, status=404)

class FeaturedHostelsView(generics.ListAPIView):
    """Get all featured hostels"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminHostelSerializer

    def get_queryset(self):
        return Hostel.objects.filter(is_featured=True).order_by('-created_at')

# ==================== REVIEW MANAGEMENT ====================
if REVIEWS_APP_EXISTS:
    class PendingReviewsView(generics.ListAPIView):
        """Get all pending reviews"""
        permission_classes = [IsAdminUser]
        serializer_class = ReviewSerializer

        def get_queryset(self):
            return Review.objects.filter(is_approved=False).order_by('-created_at')

    class ApprovedReviewsView(generics.ListAPIView):
        """Get all approved reviews"""
        permission_classes = [IsAdminUser]
        serializer_class = ReviewSerializer

        def get_queryset(self):
            return Review.objects.filter(is_approved=True).order_by('-created_at')

    class ApproveReviewView(APIView):
        """Approve a review"""
        permission_classes = [IsAdminUser]

        def post(self, request, review_id):
            try:
                review = Review.objects.get(id=review_id)
                review.is_approved = True
                review.save()
                
                AuditLog.objects.create(
                    user=request.user,
                    action='APPROVE_REVIEW',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'review_id': str(review_id)}
                )
                
                return Response({'status': 'success'})
            except Review.DoesNotExist:
                return Response({'error': 'Review not found'}, status=404)

    class RejectReviewView(APIView):
        """Reject and delete a review"""
        permission_classes = [IsAdminUser]

        def delete(self, request, review_id):
            try:
                review = Review.objects.get(id=review_id)
                review.delete()
                
                AuditLog.objects.create(
                    user=request.user,
                    action='REJECT_REVIEW',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'review_id': str(review_id)}
                )
                
                return Response({'status': 'success'})
            except Review.DoesNotExist:
                return Response({'error': 'Review not found'}, status=404)

# ==================== SUBSCRIPTION MANAGEMENT ====================
# These classes are kept but will not be used in the dashboard
class SubscriptionPlanListView(generics.ListCreateAPIView):
    """List and create subscription plans"""
    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all().order_by('price_kes')

class SubscriptionPlanDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update or delete a subscription plan"""
    permission_classes = [IsAdminUser]
    serializer_class = SubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()

class OwnerSubscriptionListView(generics.ListAPIView):
    """List all owner subscriptions with robust error handling"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminOwnerSubscriptionSerializer

    def get_queryset(self):
        try:
            queryset = OwnerSubscription.objects.select_related('owner', 'plan').order_by('-created_at')
            status_filter = self.request.query_params.get('status')
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'expired':
                queryset = queryset.filter(is_active=False)
            return queryset
        except Exception as e:
            logger.error(f"Error in OwnerSubscriptionListView.get_queryset: {e}", exc_info=True)
            return OwnerSubscription.objects.none()

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in OwnerSubscriptionListView.list: {e}", exc_info=True)
            return Response({'error': str(e), 'detail': 'Internal Server Error'}, status=500)

class AdminExtendSubscriptionView(APIView):
    """Extend an owner's subscription"""
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        try:
            subscription = OwnerSubscription.objects.get(id=id)
            days = request.data.get('days', 30)
            
            if subscription.end_date and subscription.end_date > timezone.now():
                subscription.end_date += timedelta(days=days)
            else:
                subscription.start_date = timezone.now()
                subscription.end_date = timezone.now() + timedelta(days=days)
                
            subscription.is_active = True
            subscription.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='EXTEND_SUBSCRIPTION',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'subscription_id': str(id), 'owner': subscription.owner.email, 'days': days}
            )
            
            return Response({'status': 'success', 'end_date': subscription.end_date})
        except OwnerSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=404)
        except Exception as e:
            logger.error(f"Error in AdminExtendSubscriptionView: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)

class AdminCancelSubscriptionView(APIView):
    """Cancel an owner's subscription"""
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        try:
            subscription = OwnerSubscription.objects.get(id=id)
            subscription.is_active = False
            subscription.end_date = timezone.now()
            subscription.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='CANCEL_SUBSCRIPTION',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'subscription_id': str(id), 'owner': subscription.owner.email}
            )
            
            return Response({'status': 'success'})
        except OwnerSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=404)
        except Exception as e:
            logger.error(f"Error in AdminCancelSubscriptionView: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)

# ==================== SUBSCRIPTION PLAN CRUD ====================
class SubscriptionPlanListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminSubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all().order_by('price_kes')

class SubscriptionPlanRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminSubscriptionPlanSerializer
    queryset = SubscriptionPlan.objects.all()
    lookup_field = 'id'

    def delete(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

# ==================== OWNER SUBSCRIPTION CRUD ====================
class OwnerSubscriptionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminOwnerSubscriptionSerializer
    queryset = OwnerSubscription.objects.all()
    lookup_field = 'id'

class OwnerSubscriptionUpdateView(generics.UpdateAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminOwnerSubscriptionSerializer
    queryset = OwnerSubscription.objects.all()
    lookup_field = 'id'

    def perform_update(self, serializer):
        serializer.save()
        AuditLog.objects.create(
            user=self.request.user,
            action='UPDATE_OWNER_SUBSCRIPTION',
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            details={'subscription_id': str(self.kwargs['id']), 'changes': serializer.validated_data}
        )

class OwnerSubscriptionDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = OwnerSubscription.objects.all()
    lookup_field = 'id'

    def perform_destroy(self, instance):
        AuditLog.objects.create(
            user=self.request.user,
            action='DELETE_OWNER_SUBSCRIPTION',
            ip_address=get_client_ip(self.request),
            user_agent=self.request.META.get('HTTP_USER_AGENT', ''),
            details={'subscription_id': str(instance.id), 'owner': instance.owner.email}
        )
        instance.delete()

class OwnerSubscriptionCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        data = request.data
        try:
            owner, created = User.objects.get_or_create(
                email=data['email'],
                defaults={
                    'full_name': data['owner_name'],
                    'role': 'owner',
                    'is_active': True
                }
            )
            if created:
                HostelOwnerProfile.objects.get_or_create(
                    user=owner,
                    defaults={
                        'hostel_name': data['hostel_name'],
                        'primary_phone': data['owner_phone']
                    }
                )
            plan_id = data.get('plan_id')
            if plan_id:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            else:
                plan = SubscriptionPlan.objects.first()
            subscription = OwnerSubscription.objects.create(
                owner=owner,
                plan=plan,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=int(data['duration_days'])),
                is_active=True
            )
            AuditLog.objects.create(
                user=request.user,
                action='CREATE_OWNER_SUBSCRIPTION',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'subscription_id': str(subscription.id), 'owner': owner.email}
            )
            serializer = AdminOwnerSubscriptionSerializer(subscription)
            return Response(serializer.data, status=201)
        except Exception as e:
            logger.error(f"Error in OwnerSubscriptionCreateView: {e}", exc_info=True)
            return Response({'error': str(e)}, status=400)

# ==================== ENHANCED CHAT MANAGEMENT ====================
class AdminConversationListView(generics.ListAPIView):
    """List all chat conversations for admin"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminConversationSerializer

    def get_queryset(self):
        return Conversation.objects.all().order_by('-updated_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class AdminConversationMessagesView(generics.ListAPIView):
    """Get messages for a specific conversation"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminMessageSerializer

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        # Mark messages as read when admin views
        Message.objects.filter(conversation_id=conversation_id, is_read=False).exclude(sender=self.request.user).update(is_read=True)
        return Message.objects.filter(conversation_id=conversation_id).order_by('timestamp')

class AdminSendMessageView(APIView):
    """Send a message in a conversation"""
    permission_classes = [IsAdminUser]

    def post(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
            content = request.data.get('content')
            if not content:
                return Response({'error': 'Message content required'}, status=400)
            message = Message.objects.create(
                conversation=conversation,
                sender=request.user,
                content=content,
                is_read=False
            )
            conversation.updated_at = timezone.now()
            conversation.save()
            serializer = AdminMessageSerializer(message)
            return Response(serializer.data, status=201)
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=404)
        except Exception as e:
            logger.error(f"Error in AdminSendMessageView: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)

class AdminTypingIndicatorView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, conversation_id):
        return Response({'status': 'typing'})

# ==================== ENHANCED NOTIFICATION MANAGEMENT ====================
class NotificationListView(generics.ListAPIView):
    """List all notifications"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminNotificationSerializer
    queryset = Notification.objects.all().order_by('-created_at')

class MarkNotificationReadView(APIView):
    """Mark a notification as read"""
    permission_classes = [IsAdminUser]

    def post(self, request, notification_id):
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.is_read = True
            notification.save()
            return Response({'status': 'success'})
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=404)

class SendBulkNotificationView(APIView):
    """
    Send bulk notifications to users - HTML EMAIL VERSION
    """
    permission_classes = [permissions.IsAuthenticated]

    def send_html_email(self, to_email, subject, message, link=''):
        """Send HTML email using EmailMultiAlternatives"""
        try:
            print(f"\n📧 Sending HTML email to: {to_email}")
            print(f"   Subject: {subject}")
            
            # Create HTML email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{subject}</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        background-color: #f5f5f5;
                        margin: 0;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #006747 0%, #00855a 100%);
                        color: white;
                        padding: 30px 20px;
                        text-align: center;
                    }}
                    .header h1 {{
                        margin: 0;
                        font-size: 28px;
                    }}
                    .content {{
                        padding: 30px;
                    }}
                    .message-box {{
                        background: #f9f9f9;
                        border-left: 4px solid #FFD700;
                        padding: 15px 20px;
                        margin: 20px 0;
                        border-radius: 8px;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 12px 30px;
                        background: #006747;
                        color: white;
                        text-decoration: none;
                        border-radius: 50px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        padding: 20px;
                        background: #f8f9fa;
                        font-size: 12px;
                        color: #666;
                        border-top: 1px solid #eee;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🏠 Kirinyaga University Hostels</h1>
                        <p>Official Notification</p>
                    </div>
                    <div class="content">
                        <h2 style="color: #006747;">{subject}</h2>
                        <div class="message-box">
                            <p style="margin: 0;">{message}</p>
                        </div>
                        {f'<a href="{link}" class="button">📌 View Details</a>' if link else ''}
                        <p style="font-size: 12px; color: #666; margin-top: 20px;">
                            <i>This is an automated notification from Kirinyaga University Hostels system.</i>
                        </p>
                    </div>
                    <div class="footer">
                        <p>© 2025 Kirinyaga University Hostels. All rights reserved.</p>
                        <p>Kirinyaga University, P.O. Box 143-10300, Kerugoya, Kenya</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text version
            text_content = f"""
            Kirinyaga University Hostels
            ============================
            
            {subject}
            
            {message}
            
            {f'View details: {link}' if link else ''}
            
            ---
            This is an automated notification. Please do not reply.
            """
            
            # Create email with HTML and plain text
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
                reply_to=[settings.DEFAULT_FROM_EMAIL]
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            
            print(f"✅ HTML email sent to {to_email}")
            return True, "Email sent"
            
        except Exception as e:
            print(f"❌ Failed to send email to {to_email}: {str(e)}")
            return False, str(e)

    def post(self, request):
        data = request.data
        title = data.get('title', 'Notification from Kirinyaga Hostels')
        message = data.get('message', '')
        user_type = data.get('user_type', 'all')
        link = data.get('link', '')
        email = data.get('email')
        user_ids = data.get('user_ids', [])
        
        print("\n" + "="*60)
        print("📢 SEND NOTIFICATION (HTML EMAIL VERSION)")
        print("="*60)
        print(f"Title: {title}")
        print(f"User Type: {user_type}")
        print(f"Message: {message[:50]}...")
        print("="*60)
        
        if not message:
            return Response({'error': 'Message is required'}, status=400)
        
        # Get recipients
        users = []
        if user_type == 'all':
            users = User.objects.filter(is_active=True)
        elif user_type == 'students':
            users = User.objects.filter(is_active=True, role='student')
        elif user_type == 'owners':
            users = User.objects.filter(is_active=True, role='owner')
        elif user_type == 'specific' and user_ids:
            users = User.objects.filter(id__in=user_ids, is_active=True)
        elif user_type == 'single' and email:
            users = User.objects.filter(email=email, is_active=True)
        
        if not users.exists():
            return Response({'error': 'No recipients found'}, status=404)
        
        print(f"Recipients: {users.count()}")
        
        sent = 0
        failed = 0
        
        for user in users:
            try:
                # Create in-app notification
                from apps.notifications.models import Notification
                Notification.objects.create(
                    user=user,
                    title=title,
                    message=message,
                    link=link,
                    is_read=False
                )
                
                # Send HTML email
                success, result = self.send_html_email(user.email, title, message, link)
                if success:
                    sent += 1
                    print(f"✓ Sent to {user.email}")
                else:
                    failed += 1
                    print(f"✗ Failed to {user.email}: {result}")
                
                # Log the action
                AuditLog.objects.create(
                    user=request.user,
                    action='SEND_BULK_NOTIFICATION',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'title': title, 'user_type': user_type, 'recipients': users.count()}
                )
                
            except Exception as e:
                failed += 1
                print(f"✗ Error for {user.email}: {str(e)}")
        
        print(f"\nResults: {sent} sent, {failed} failed")
        
        return Response({
            'status': 'success',
            'sent': sent,
            'failed': failed,
            'total': users.count()
        }, status=200)

# ==================== AUDIT LOGS ====================
class AuditLogListView(APIView):
    """List all audit logs with enhanced filtering and pagination"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Get filter parameters
        action = request.query_params.get('action')
        category = request.query_params.get('category')
        user_email = request.query_params.get('user')
        search = request.query_params.get('search')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        resource_type = request.query_params.get('resource_type')
        
        queryset = AuditLog.objects.select_related('user').order_by('-timestamp')
        
        # Apply filters
        if action:
            queryset = queryset.filter(action__icontains=action)
        if category:
            queryset = queryset.filter(action_category=category)
        if user_email:
            queryset = queryset.filter(user__email__icontains=user_email)
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search) |
                Q(user__full_name__icontains=search) |
                Q(action__icontains=search) |
                Q(ip_address__icontains=search) |
                Q(details__icontains=search)
            )
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 50))
        start = (page - 1) * page_size
        end = start + page_size
        
        total = queryset.count()
        logs = queryset[start:end]
        
        # Get unique actions and categories for filter dropdowns
        unique_actions = list(AuditLog.objects.values_list('action', flat=True).distinct()[:100])
        unique_categories = list(AuditLog.objects.values_list('action_category', flat=True).distinct())
        unique_resource_types = list(AuditLog.objects.exclude(resource_type__isnull=True).values_list('resource_type', flat=True).distinct())
        
        data = []
        for log in logs:
            # Use the human-readable methods
            data.append({
                'id': log.id,
                'timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'user': log.user.email if log.user else 'System',
                'user_name': log.user.full_name if log.user else 'System',
                'user_role': log.user.role if log.user else 'system',
                'action': log.get_human_readable_action(),
                'action_code': log.action,
                'action_summary': log.get_activity_summary(),
                'category': log.action_category or 'system',
                'details': log.details,
                'ip_address': log.ip_address,
                'user_agent': log.user_agent[:100] if log.user_agent else '',
                'resource_type': log.resource_type,
                'resource_id': log.resource_id,
                'request_method': log.request_method,
                'response_status': log.response_status,
            })
        
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'has_next': page < ((total + page_size - 1) // page_size),
            'has_previous': page > 1,
            'filters': {
                'available_actions': unique_actions,
                'available_categories': unique_categories,
                'available_resource_types': unique_resource_types,
            },
            'results': data
        })

# ==================== FRAUD ALERTS ====================
class FraudAlertsView(APIView):
    """Get fraud alerts data"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Get users with high failed attempts
        high_risk_by_attempts = User.objects.filter(
            failed_login_attempts__gte=5
        ).select_related('owner_profile', 'student_profile')
        
        # Get owners with high fraud score
        high_risk_owners = User.objects.filter(
            role='owner',
            owner_profile__fraud_score__gte=70
        ).select_related('owner_profile')
        
        locked_accounts = User.objects.filter(
            locked_until__isnull=False,
            locked_until__gt=timezone.now()
        ).select_related('owner_profile', 'student_profile')
        
        recent_failed_attempts = AuditLog.objects.filter(
            action='LOGIN_FAILED',
            timestamp__gte=timezone.now() - timedelta(days=7)
        ).values('ip_address').annotate(count=Count('id')).order_by('-count')[:20]
        
        from itertools import chain
        combined = list(chain(high_risk_by_attempts, high_risk_owners))
        seen = set()
        high_risk_users = []
        for user in combined:
            if user.id not in seen:
                seen.add(user.id)
                high_risk_users.append(user)
        
        high_risk_data = []
        for user in high_risk_users:
            if user.role == 'owner' and hasattr(user, 'owner_profile'):
                fraud_score = user.owner_profile.fraud_score
            else:
                fraud_score = 0
            high_risk_data.append({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'full_name': user.full_name,
                'fraud_score': fraud_score,
                'failed_login_attempts': user.failed_login_attempts,
                'locked_until': user.locked_until,
                'is_active': user.is_active
            })
        
        locked_data = []
        for user in locked_accounts:
            locked_data.append({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'full_name': user.full_name,
                'locked_until': user.locked_until
            })
        
        return Response({
            'high_risk_users': high_risk_data,
            'locked_accounts': locked_data,
            'recent_failed_attempts': list(recent_failed_attempts)
        })

# ==================== SYSTEM SETTINGS ====================
class SystemSettingsView(APIView):
    """Get and update system settings"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        settings_obj = SystemSettings.get_settings()
        return Response({
            'site_name': settings_obj.site_name,
            'admin_email': settings_obj.admin_email,
            'contact_phone': settings_obj.contact_phone,
            'max_login_attempts': settings_obj.max_login_attempts,
            'admin_max_attempts': settings_obj.admin_max_attempts,
            'lockout_hours': settings_obj.lockout_hours,
            'twofa_required': settings_obj.twofa_required,
            'session_timeout': settings_obj.session_timeout,
            'maintenance_mode': settings_obj.maintenance_mode,
            'features': {
                'roommate_finder': settings_obj.roommate_finder_enabled,
                'student_reviews': settings_obj.student_reviews_enabled,
                'owner_chat': settings_obj.owner_chat_enabled,
                'subscriptions': settings_obj.subscriptions_enabled,
                'google_maps': settings_obj.google_maps_enabled,
                'notifications': settings_obj.notifications_enabled
            }
        })

    def post(self, request):
        try:
            settings_obj = SystemSettings.get_settings()
            
            if 'site_name' in request.data:
                settings_obj.site_name = request.data['site_name']
            if 'admin_email' in request.data:
                settings_obj.admin_email = request.data['admin_email']
            if 'contact_phone' in request.data:
                settings_obj.contact_phone = request.data['contact_phone']
            if 'max_login_attempts' in request.data:
                settings_obj.max_login_attempts = int(request.data['max_login_attempts'])
            if 'admin_max_attempts' in request.data:
                settings_obj.admin_max_attempts = int(request.data['admin_max_attempts'])
            if 'lockout_hours' in request.data:
                settings_obj.lockout_hours = int(request.data['lockout_hours'])
            if 'twofa_required' in request.data:
                settings_obj.twofa_required = bool(request.data['twofa_required'])
            if 'session_timeout' in request.data:
                settings_obj.session_timeout = int(request.data['session_timeout'])
            if 'maintenance_mode' in request.data:
                settings_obj.maintenance_mode = bool(request.data['maintenance_mode'])
            
            features = request.data.get('features', {})
            if features:
                if 'roommate_finder' in features:
                    settings_obj.roommate_finder_enabled = bool(features['roommate_finder'])
                if 'student_reviews' in features:
                    settings_obj.student_reviews_enabled = bool(features['student_reviews'])
                if 'owner_chat' in features:
                    settings_obj.owner_chat_enabled = bool(features['owner_chat'])
                if 'subscriptions' in features:
                    settings_obj.subscriptions_enabled = bool(features['subscriptions'])
                if 'google_maps' in features:
                    settings_obj.google_maps_enabled = bool(features['google_maps'])
                if 'notifications' in features:
                    settings_obj.notifications_enabled = bool(features['notifications'])
            
            settings_obj.updated_by = request.user
            settings_obj.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='UPDATE_SYSTEM_SETTINGS',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'settings': request.data}
            )
            
            return Response({'status': 'success', 'message': 'Settings saved successfully'})
            
        except Exception as e:
            logger.error(f"Error saving system settings: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)

# ==================== ANALYTICS ====================
class UserAnalyticsView(APIView):
    """Get user analytics data"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        months = []
        student_data = []
        owner_data = []
        now = timezone.now()
        
        for i in range(5, -1, -1):
            month = now - timedelta(days=30 * i)
            month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            
            student_count = User.objects.filter(role='student', date_joined__lte=month_end).count()
            owner_count = User.objects.filter(role='owner', date_joined__lte=month_end).count()
            
            months.append(month_start.strftime('%b'))
            student_data.append(student_count)
            owner_data.append(owner_count)
        
        return Response({
            'labels': months,
            'datasets': [
                {
                    'label': 'Students',
                    'data': student_data,
                    'borderColor': '#006747',
                    'backgroundColor': 'rgba(0,103,71,0.1)',
                },
                {
                    'label': 'Owners',
                    'data': owner_data,
                    'borderColor': '#FFD700',
                    'backgroundColor': 'rgba(255,215,0,0.1)',
                }
            ]
        })

class HostelAnalyticsView(APIView):
    """Get hostel analytics data"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        months = []
        total_data = []
        approved_data = []
        
        now = timezone.now()
        for i in range(5, -1, -1):
            month = now - timedelta(days=30 * i)
            month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            
            total = Hostel.objects.filter(created_at__lte=month_end).count()
            approved = Hostel.objects.filter(created_at__lte=month_end, is_approved=True).count()
            
            months.append(month_start.strftime('%b'))
            total_data.append(total)
            approved_data.append(approved)
        
        room_types = Hostel.objects.values('room_type').annotate(count=Count('id'))
        locations = Hostel.objects.values('address').annotate(count=Count('id')).order_by('-count')[:10]
        
        return Response({
            'over_time': {
                'labels': months,
                'total': total_data,
                'approved': approved_data,
            },
            'by_room_type': list(room_types),
            'top_locations': list(locations)
        })

# ==================== SESSION MANAGEMENT ====================
class TerminateOtherSessionsView(APIView):
    """Terminate all other sessions for current admin"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        Session.objects.filter(expire_date__gte=timezone.now()).exclude(session_key=request.session.session_key).delete()
        
        AuditLog.objects.create(
            user=request.user,
            action='TERMINATE_OTHER_SESSIONS',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'status': 'other sessions terminated'}
        )
        
        return Response({'status': 'success'})

class ActiveSessionsView(APIView):
    """Get active sessions for current admin"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        sessions = Session.objects.filter(expire_date__gte=timezone.now())
        session_data = []
        for session in sessions:
            data = session.get_decoded()
            user_id = data.get('_auth_user_id')
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    session_data.append({
                        'session_token': session.session_key,
                        'user': user.email,
                        'created': session.expire_date - timedelta(seconds=settings.SESSION_COOKIE_AGE),
                        'expires': session.expire_date,
                        'ip': data.get('ip_address', 'N/A'),
                        'user_agent': data.get('user_agent', 'N/A'),
                        'current': session.session_key == request.session.session_key
                    })
                except User.DoesNotExist:
                    pass
        
        return Response({'sessions': session_data})

# ==================== TESTING ENDPOINTS ====================
class TestEmailView(APIView):
    """Test email configuration"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        to_email = request.data.get('email', request.user.email)
        
        try:
            send_mail(
                'Test Email from Kirinyaga Hostels',
                'This is a test email to verify SMTP configuration.',
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                fail_silently=False,
            )
            
            AuditLog.objects.create(
                user=request.user,
                action='TEST_EMAIL',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'status': 'success', 'to': to_email}
            )
            
            return Response({'status': 'success', 'message': 'Test email sent'})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=500)

class TestSMSView(APIView):
    """Test SMS configuration using Twilio"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        to_phone = request.data.get('phone')
        if not to_phone:
            if hasattr(request.user, 'owner_profile') and request.user.owner_profile.primary_phone:
                to_phone = str(request.user.owner_profile.primary_phone)
            elif hasattr(request.user, 'student_profile') and request.user.student_profile.phone_number:
                to_phone = str(request.user.student_profile.phone_number)
            else:
                return Response({'error': 'Phone number required'}, status=400)

        message = "This is a test SMS from Kirinyaga Hostels. Your SMS configuration is working!"
        success = send_sms(to_phone, message)

        AuditLog.objects.create(
            user=request.user,
            action='TEST_SMS',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'status': 'tested', 'to': to_phone, 'success': success}
        )

        if success:
            return Response({'status': 'success', 'message': f'Test SMS sent to {to_phone}'})
        else:
            return Response({'status': 'error', 'message': 'Failed to send SMS. Check Twilio configuration.'}, status=500)

class TestMpesaView(APIView):
    """Test M-Pesa integration"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        phone = request.data.get('phone', '254700000000')
        amount = request.data.get('amount', 10)
        
        AuditLog.objects.create(
            user=request.user,
            action='TEST_MPESA',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'status': 'tested', 'phone': phone, 'amount': amount}
        )
        
        return Response({'status': 'success', 'message': f'M-Pesa test simulated to {phone} for KSh {amount}'})

class ErrorLogsView(APIView):
    """View Django error logs"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        import os
        
        log_file = os.path.join(settings.BASE_DIR, 'logs', 'error.log')
        logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r') as f:
                lines = f.readlines()[-100:]
                for line in lines:
                    logs.append({
                        'level': 'ERROR',
                        'timestamp': timezone.now(),
                        'message': line.strip(),
                        'traceback': ''
                    })
        
        return Response({'logs': logs})



class AdminProfileUpdateView(APIView):
    permission_classes = [IsAdminUser]
    
    def put(self, request):
        user = request.user
        data = request.data
        
        # Update name and email
        if 'full_name' in data:
            user.full_name = data['full_name']
        if 'email' in data:
            # Check if email is already taken
            if User.objects.exclude(id=user.id).filter(email=data['email']).exists():
                return Response({'error': 'Email already in use'}, status=400)
            user.email = data['email']
        
        # Update password
        if 'new_password' in data and data['new_password']:
            if not user.check_password(data.get('current_password', '')):
                return Response({'error': 'Current password is incorrect'}, status=400)
            user.set_password(data['new_password'])
        
        user.save()
        return Response({
            'id': user.id,
            'full_name': user.full_name,
            'email': user.email
        })

# ==================== AVATAR UPLOAD (Cloudinary) ====================
class AdminProfileAvatarUpdateView(APIView):
    """Update admin profile avatar using Cloudinary"""
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        avatar_file = request.FILES.get('avatar')
        
        if not avatar_file:
            return Response({'error': 'No avatar file provided'}, status=400)
        
        if not avatar_file.content_type.startswith('image/'):
            return Response({'error': 'File must be an image'}, status=400)
        
        if avatar_file.size > 2 * 1024 * 1024:
            return Response({'error': 'Image must be less than 2MB'}, status=400)
        
        try:
            upload_result = cloudinary.uploader.upload(
                avatar_file,
                folder=f'admin_avatars/{user.id}',
                public_id=f'avatar_{user.id}',
                overwrite=True,
                transformation=[
                    {'width': 300, 'height': 300, 'crop': 'fill', 'gravity': 'face'},
                    {'quality': 'auto'}
                ]
            )
            
            avatar_url = upload_result.get('secure_url')
            public_id = upload_result.get('public_id')
            
            if hasattr(user, 'avatar'):
                user.avatar = avatar_url
                user.avatar_public_id = public_id
                user.save()
                
                AuditLog.objects.create(
                    user=request.user,
                    action='UPDATE_AVATAR',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'status': 'success', 'public_id': public_id}
                )
                
                return Response({
                    'status': 'success',
                    'message': 'Avatar updated successfully',
                    'avatar_url': avatar_url
                })
            else:
                return Response({
                    'status': 'success',
                    'message': 'Avatar uploaded to Cloudinary',
                    'avatar_url': avatar_url
                })
        except Exception as e:
            logger.error(f"Error uploading avatar to Cloudinary: {e}")
            return Response({'error': str(e)}, status=500)

    def delete(self, request):
        user = request.user
        try:
            if hasattr(user, 'avatar_public_id') and user.avatar_public_id:
                cloudinary.uploader.destroy(user.avatar_public_id)
                user.avatar = None
                user.avatar_public_id = None
                user.save()
                
                AuditLog.objects.create(
                    user=request.user,
                    action='DELETE_AVATAR',
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                    details={'status': 'success'}
                )
                return Response({'status': 'success', 'message': 'Avatar deleted successfully'})
            else:
                return Response({'status': 'success', 'message': 'No avatar to delete'})
        except Exception as e:
            logger.error(f"Error deleting avatar from Cloudinary: {e}")
            return Response({'error': str(e)}, status=500)        

class AnnouncementActiveView(APIView):
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        # Get active announcement from database
        from apps.notifications.models import Announcement
        announcement = Announcement.objects.filter(is_active=True, expires_at__gt=timezone.now()).first()
        if announcement:
            return Response({
                'id': announcement.id,
                'message': announcement.message,
                'link': announcement.link
            })
        return Response({})

class SmsBalanceView(APIView):
    """Get Twilio SMS balance"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            from twilio.rest import Client
            
            if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
                return Response({'balance': 0, 'currency': 'USD', 'error': 'Twilio not configured'}, status=200)
            
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            balance = client.balance.fetch()
            return Response({
                'balance': balance.balance,
                'currency': balance.currency
            })
        except Exception as e:
            logger.error(f"Error fetching SMS balance: {e}")
            # Return default response instead of 500 error
            return Response({
                'balance': 0,
                'currency': 'USD',
                'error': str(e)
            }, status=200)

# ==================== ADMIN PROFILE UPDATE ====================
class AdminProfileUpdateView(APIView):
    """Update admin profile information"""
    permission_classes = [IsAdminUser]

    def put(self, request):
        user = request.user
        data = request.data
        
        # Update name and email
        if 'full_name' in data:
            user.full_name = data['full_name']
        if 'email' in data:
            # Check if email is already taken by another user
            if User.objects.exclude(id=user.id).filter(email=data['email']).exists():
                return Response({'error': 'Email already in use'}, status=400)
            user.email = data['email']
        
        # Update password if provided
        if 'new_password' in data and data['new_password']:
            # Verify current password
            if not user.check_password(data.get('current_password', '')):
                return Response({'error': 'Current password is incorrect'}, status=400)
            user.set_password(data['new_password'])
        
        user.save()
        
        # Log the action
        AuditLog.objects.create(
            user=request.user,
            action='UPDATE_ADMIN_PROFILE',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'updated_fields': list(data.keys())}
        )
        
        return Response({
            'id': str(user.id),
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role,
            'is_superuser': user.is_superuser,
            'is_staff': user.is_staff
        })

# ==================== ANNOUNCEMENTS ====================
class AnnouncementActiveView(APIView):
    """Get active announcement"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            from apps.notifications.models import Announcement
            announcement = Announcement.objects.filter(
                is_active=True, 
                expires_at__gt=timezone.now()
            ).order_by('-created_at').first()
            
            if announcement:
                return Response({
                    'id': str(announcement.id),
                    'message': announcement.message,
                    'link': announcement.link,
                    'expires_at': announcement.expires_at
                })
            return Response({})
        except ImportError:
            # Announcement model not created yet
            return Response({})
        except Exception as e:
            logger.error(f"Error fetching announcement: {e}")
            return Response({})

class AnnouncementCreateView(APIView):
    """Create or update announcement"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        try:
            from apps.notifications.models import Announcement
            
            message = request.data.get('message')
            link = request.data.get('link', '')
            expires_at = request.data.get('expires_at')
            
            if not message:
                return Response({'error': 'Message is required'}, status=400)
            
            # Deactivate old announcements
            Announcement.objects.filter(is_active=True).update(is_active=False)
            
            # Create new announcement
            announcement = Announcement.objects.create(
                message=message,
                link=link,
                is_active=True,
                expires_at=expires_at or (timezone.now() + timedelta(days=7)),
                created_by=request.user
            )
            
            AuditLog.objects.create(
                user=request.user,
                action='CREATE_ANNOUNCEMENT',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'message': message[:100]}
            )
            
            return Response({
                'id': str(announcement.id),
                'message': announcement.message,
                'link': announcement.link,
                'expires_at': announcement.expires_at
            }, status=201)
        except ImportError:
            return Response({'error': 'Announcement model not configured'}, status=500)
        except Exception as e:
            logger.error(f"Error creating announcement: {e}")
            return Response({'error': str(e)}, status=500)

# ==================== SMS BALANCE ====================
class SmsBalanceView(APIView):
    """Get Twilio SMS balance"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            from twilio.rest import Client
            
            if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
                return Response({'balance': 0, 'currency': 'USD', 'error': 'Twilio not configured'}, status=200)
            
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            balance = client.balance.fetch()
            return Response({
                'balance': balance.balance,
                'currency': balance.currency
            })
        except Exception as e:
            logger.error(f"Error fetching SMS balance: {e}")
            # Return 200 with error message instead of 500
            return Response({
                'balance': 0,
                'currency': 'USD',
                'error': str(e)
            }, status=200)

# ==================== VERIFY USER ====================
class VerifyUserView(APIView):
    """Verify a student's email (admin action)"""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(id=user_id)
            
            # Only students can be verified by admin
            if user.role != 'student':
                return Response(
                    {'error': 'Only student accounts can be verified by admin'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if user.email_verified:
                return Response(
                    {'error': 'User already verified'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify the user
            user.email_verified = True
            user.email_verification_token = ''
            user.save()
            
            # Log the action
            AuditLog.objects.create(
                user=request.user,
                action='VERIFY_USER',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'user_id': str(user_id), 'email': user.email}
            )
            
            return Response({
                'status': 'success', 
                'message': f'Student {user.full_name} verified successfully'
            })
            
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error verifying user: {e}")
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== IMPERSONATION ====================
class ImpersonateStartView(APIView):
    """Start impersonating a user - returns JWT token for frontend redirect"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        email = request.data.get('email')
        user_id = request.data.get('user_id')
        
        try:
            if email:
                target_user = User.objects.get(email=email)
            elif user_id:
                target_user = User.objects.get(id=user_id)
            else:
                return Response({'error': 'Email or user ID required'}, status=400)
            
            # Don't allow impersonating other admins (but allow if superuser)
            if (target_user.role == 'admin' or target_user.is_superuser) and not request.user.is_superuser:
                return Response({'error': 'Cannot impersonate admin users'}, status=403)
            
            from rest_framework_simplejwt.tokens import RefreshToken
            
            # Store impersonation in session for audit trail
            request.session['impersonating_id'] = str(target_user.id)
            request.session['original_user_id'] = str(request.user.id)
            request.session['impersonating'] = True
            request.session.save()
            
            # Create JWT tokens for the target user
            refresh = RefreshToken.for_user(target_user)
            refresh['impersonated_by'] = str(request.user.id)
            refresh['impersonated_by_email'] = request.user.email
            refresh['is_impersonating'] = True
            refresh['original_role'] = request.user.role
            
            # Determine redirect URL based on user role
            if target_user.role == 'owner':
                redirect_url = '/owner/dashboard.html'
            elif target_user.role == 'student':
                redirect_url = '/student/dashboard.html'
            else:
                redirect_url = '/'
            
            # Log the impersonation
            AuditLog.objects.create(
                user=request.user,
                action='IMPERSONATE_USER',
                action_category='admin',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={
                    'impersonated_user': target_user.email,
                    'impersonated_user_id': str(target_user.id),
                    'impersonated_user_role': target_user.role
                }
            )
            
            return Response({
                'status': 'success',
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'user': {
                    'id': str(target_user.id),
                    'email': target_user.email,
                    'full_name': target_user.full_name,
                    'role': target_user.role
                },
                'redirect_url': redirect_url,
                'message': f'Now impersonating {target_user.email}. Redirecting to their dashboard...'
            })
            
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
        except Exception as e:
            logger.error(f"Error starting impersonation: {e}")
            return Response({'error': str(e)}, status=500)


class ImpersonateStopView(APIView):
    """Stop impersonating and return to admin account"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Check if currently impersonating
        original_user_id = request.session.get('original_user_id')
        
        if not original_user_id:
            return Response({'error': 'Not currently impersonating'}, status=400)
        
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            original_user = User.objects.get(id=original_user_id)
            
            # Create new JWT for original admin
            refresh = RefreshToken.for_user(original_user)
            
            # Clear impersonation session
            request.session.pop('impersonating_id', None)
            request.session.pop('original_user_id', None)
            request.session.pop('impersonating', None)
            
            # Log stop impersonation
            AuditLog.objects.create(
                user=original_user,
                action='STOP_IMPERSONATION',
                action_category='admin',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'status': 'stopped'}
            )
            
            return Response({
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
                'user_email': original_user.email,
                'user_name': original_user.full_name,
                'user_role': original_user.role,
                'is_impersonating': False
            })
            
        except User.DoesNotExist:
            return Response({'error': 'Original user not found'}, status=404)
        except Exception as e:
            logger.error(f"Error stopping impersonation: {e}")
            return Response({'error': str(e)}, status=500)


class CheckImpersonationView(APIView):
    """Check if currently impersonating"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_impersonating = request.session.get('impersonating', False)
        original_user_id = request.session.get('original_user_id')
        
        return Response({
            'is_impersonating': is_impersonating,
            'original_user_id': original_user_id
        })

class NewsletterSubscribeView(APIView):
    """Subscribe to newsletter"""
    permission_classes = [AllowAny]  # Allow anyone to subscribe

    def post(self, request):
        email = request.data.get('email')
        
        if not email:
            return Response({'error': 'Email is required'}, status=400)
        
        # Validate email format
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return Response({'error': 'Invalid email format'}, status=400)
        
        try:
           
            # For now, just log it
            print(f"Newsletter subscription: {email}")
            
            # Optional: Send welcome email
            send_mail(
              subject='Welcome to Kirinyaga Hostels Newsletter',
              message='Thank you for subscribing! You will receive updates on new hostels and offers.',
              from_email=settings.DEFAULT_FROM_EMAIL,
              recipient_list=[email],
              fail_silently=True,
             )
            
            return Response({
                'status': 'success',
                'message': 'Thank you for subscribing!'
            }, status=200)
            
        except Exception as e:
            return Response({'error': str(e)}, status=500)

class OwnerActivityLogView(APIView):
    """Get activity logs for the current owner (only their own activities)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Only owners can access their own activity logs
        if request.user.role != 'owner':
            return Response(
                {'error': 'Only owners can access this endpoint'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        # Get audit logs for this specific user (owner)
        logs = AuditLog.objects.filter(user=request.user).order_by('-timestamp')
        
        paginator = Paginator(logs, page_size)
        current_page = paginator.get_page(page)
        
        data = [{
            'id': log.id,
            'action': log.action,
            'action_category': log.action_category,
            'timestamp': log.timestamp,
            'details': log.details,
            'ip_address': log.ip_address,
        } for log in current_page]
        
        return Response({
            'results': data,
            'total': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages
        })