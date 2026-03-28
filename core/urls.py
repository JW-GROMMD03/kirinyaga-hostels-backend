from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse
from apps.accounts.views import SupportView, AdminProfileView
from apps.accounts import views_admin
from apps.accounts.views_admin import (
    AdminProfileUpdateView,
    AnnouncementActiveView,
    SmsBalanceView,
    ImpersonateStartView,
    NewsletterSubscribeView,
)

def home(request):
    return HttpResponse("Kirinyaga Hostels API is running!")

urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    
    # ==================== ROOT-LEVEL ADMIN ENDPOINTS (for frontend dashboard) ====================
    # Dashboard Stats
    path('api/dashboard/stats/', views_admin.DashboardStatsView.as_view(), name='dashboard-stats'),
    path('api/auth/bookings/', include('apps.bookings.urls')), 
    
    # User Management
    path('api/students/', views_admin.StudentListView.as_view(), name='students'),
    path('api/owners/', views_admin.OwnerListView.as_view(), name='owners'),
    
    # User Actions
    path('api/users/<uuid:user_id>/toggle-status/', views_admin.ToggleUserStatusView.as_view(), name='toggle-user-status'),
    path('api/users/<uuid:user_id>/delete/', views_admin.DeleteUserView.as_view(), name='delete-user'),
    path('api/users/<uuid:user_id>/unlock/', views_admin.UnlockUserView.as_view(), name='unlock-user'),
    path('api/users/<uuid:user_id>/update-fraud-score/', views_admin.UpdateFraudScoreView.as_view(), name='update-fraud-score'),
    
    # Owner Management
    path('api/owners/<uuid:owner_id>/approve/', views_admin.ApproveOwnerView.as_view(), name='approve-owner'),
    path('api/owners/<uuid:owner_id>/toggle-verified/', views_admin.ToggleVerifiedBadgeView.as_view(), name='toggle-verified'),
    
    # Hostel Management
    path('api/hostels/', include('apps.hostels.urls')),
    path('api/featured-hostels/', views_admin.FeaturedHostelsView.as_view(), name='featured-hostels'),
    path('api/hostels/<uuid:hostel_id>/approve/', views_admin.AdminApproveHostelView.as_view(), name='approve-hostel'),
    path('api/hostels/<uuid:hostel_id>/toggle-featured/', views_admin.AdminToggleFeaturedView.as_view(), name='toggle-featured'),
    path('api/hostels/<uuid:hostel_id>/delete/', views_admin.AdminDeleteHostelView.as_view(), name='delete-hostel'),
    
    # Security
    path('api/audit-logs/', views_admin.AuditLogListView.as_view(), name='audit-logs'),
    path('api/fraud-alerts/', views_admin.FraudAlertsView.as_view(), name='fraud-alerts'),
    path('api/sessions/', views_admin.ActiveSessionsView.as_view(), name='sessions'),
    
    # Analytics
    path('api/analytics/users/', views_admin.UserAnalyticsView.as_view(), name='user-analytics'),
    path('api/analytics/hostels/', views_admin.HostelAnalyticsView.as_view(), name='hostel-analytics'),
    
    # Settings
    path('api/settings/', views_admin.SystemSettingsView.as_view(), name='settings'),
    
    # Impersonation
    path('api/impersonate/start/', views_admin.ImpersonateStartView.as_view(), name='impersonate-start'),
    path('api/impersonate/stop/', views_admin.ImpersonateStopView.as_view(), name='impersonate-stop'),
    
    # SMS Balance
    path('api/sms/balance/', views_admin.SmsBalanceView.as_view(), name='sms-balance'),
    
    # Notifications
    path('api/notifications/', include('apps.notifications.urls')),
    path('api/notifications/send-bulk/', views_admin.SendBulkNotificationView.as_view(), name='send-bulk'),
    path('api/notifications/<int:notification_id>/mark-read/', views_admin.MarkNotificationReadView.as_view(), name='mark-notification-read'),
    
    # Bookings
    path('api/bookings/', include('apps.bookings.urls')),
    
    # Announcements
    path('api/announcements/active/', views_admin.AnnouncementActiveView.as_view(), name='announcement-active'),
    
    # ==================== AUTH ENDPOINTS (under /api/auth/) ====================
    path('api/auth/', include('apps.accounts.urls')),
    path('api/admin/', include('apps.accounts.urls_admin')),
    
    # Reviews
    path('api/reviews/', include('apps.reviews.urls')),
    
    # Roommate
    path('api/roommate/', include('apps.roommate.urls')),
    
    # Subscriptions
    path('api/subscriptions/', include('apps.subscriptions.urls')),
    
    # Chat
    path('api/chat/', include('apps.chat.urls')),
    
    # Support
    path('api/support/', SupportView.as_view(), name='support'),
    
    # Admin Profile
    path('api/admin/auth/profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('api/admin/auth/profile/update/', AdminProfileUpdateView.as_view(), name='admin-profile-update'),
    
    # Admin Announcements
    path('api/admin/announcements/active/', AnnouncementActiveView.as_view(), name='announcement-active'),
    
    # Admin SMS Balance
    path('api/admin/sms/balance/', SmsBalanceView.as_view(), name='admin-sms-balance'),
    
    # Admin Impersonation
    path('api/admin/impersonate/start/', ImpersonateStartView.as_view(), name='impersonate-start'),
    
    # Newsletter
    path('api/newsletter/subscribe/', NewsletterSubscribeView.as_view(), name='newsletter-subscribe'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)