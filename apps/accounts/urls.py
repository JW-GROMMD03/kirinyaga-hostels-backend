from django.urls import path
from apps.bookings import views as bookings_views
from .views import (
    StudentSignupView, OwnerSignupView,
    StudentLoginView, OwnerLoginView, AdminLoginView,
    VerifyEmailView, ResendVerificationView, LogoutView,
    PasswordResetRequestView, PasswordResetConfirmView,
    TwoFactorOTPSendView, TwoFactorOTPVerifyView,
    TwoFactorStatusView, TwoFactorEnableRequestView, TwoFactorEnableConfirmView,
    TwoFactorDisableView, TwoFactorDisableConfirmView, OwnerActivityLogView,
    UserProfileView, SupportView
)
from . import views_admin

urlpatterns = [
    # ==================== AUTHENTICATION ====================
    path('signup/student/', StudentSignupView.as_view(), name='student-signup'),
    path('signup/owner/', OwnerSignupView.as_view(), name='owner-signup'),
    path('student/login/', StudentLoginView.as_view(), name='student-login'),
    path('owner/login/', OwnerLoginView.as_view(), name='owner-login'),
    path('admin/login/', AdminLoginView.as_view(), name='admin-login'),
    path('verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('resend-verification/', ResendVerificationView.as_view(), name='resend-verification'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    
    # 2FA
    path('2fa/send-otp/', TwoFactorOTPSendView.as_view(), name='2fa-send-otp'),
    path('2fa/verify-otp/', TwoFactorOTPVerifyView.as_view(), name='2fa-verify-otp'),
    path('2fa/status/', TwoFactorStatusView.as_view(), name='2fa-status'),
    path('2fa/enable-request/', TwoFactorEnableRequestView.as_view(), name='2fa-enable-request'),
    path('2fa/enable-confirm/', TwoFactorEnableConfirmView.as_view(), name='2fa-enable-confirm'),
    path('2fa/disable-request/', TwoFactorDisableView.as_view(), name='2fa-disable-request'),
    path('2fa/disable-confirm/', TwoFactorDisableConfirmView.as_view(), name='2fa-disable-confirm'),
    
    # Profile
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/update/', views_admin.AdminProfileUpdateView.as_view(), name='admin-profile-update'),
    path('support/', SupportView.as_view(), name='support'),
    
    # ==================== ADMIN DASHBOARD ENDPOINTS (without /admin/ prefix for cleaner URLs) ====================
    # Dashboard
    path('dashboard/stats/', views_admin.DashboardStatsView.as_view(), name='admin-dashboard-stats'),
    path('bookings/', bookings_views.AdminBookingListView.as_view(), name='admin-bookings'),
    
    # User Management
    path('students/', views_admin.StudentListView.as_view(), name='admin-students'),
    path('students/<uuid:pk>/', views_admin.StudentDetailView.as_view(), name='admin-student-detail'),
    path('owners/', views_admin.OwnerListView.as_view(), name='admin-owners'),
    path('owners/<uuid:pk>/', views_admin.OwnerDetailView.as_view(), name='admin-owner-detail'),
    path('owners/<uuid:owner_id>/approve/', views_admin.ApproveOwnerView.as_view(), name='admin-approve-owner'),
    path('owners/<uuid:owner_id>/toggle-verified/', views_admin.ToggleVerifiedBadgeView.as_view(), name='admin-toggle-verified'),
    
    # User Actions
    path('users/<uuid:user_id>/toggle-status/', views_admin.ToggleUserStatusView.as_view(), name='admin-toggle-status'),
    path('users/<uuid:user_id>/delete/', views_admin.DeleteUserView.as_view(), name='admin-delete-user'),
    path('users/<uuid:user_id>/unlock/', views_admin.UnlockUserView.as_view(), name='admin-unlock-user'),
    path('users/<uuid:user_id>/update-fraud-score/', views_admin.UpdateFraudScoreView.as_view(), name='admin-update-fraud'),
    path('users/high-risk/', views_admin.HighRiskUsersView.as_view(), name='admin-high-risk'),
    
    # Hostel Management
    path('hostels/', views_admin.AdminHostelListView.as_view(), name='admin-hostels'),
    path('hostels/<uuid:pk>/', views_admin.AdminHostelDetailView.as_view(), name='admin-hostel-detail'),
    path('hostels/<uuid:hostel_id>/approve/', views_admin.AdminApproveHostelView.as_view(), name='admin-approve-hostel'),
    path('hostels/<uuid:hostel_id>/toggle-featured/', views_admin.AdminToggleFeaturedView.as_view(), name='admin-toggle-featured'),
    path('hostels/<uuid:hostel_id>/delete/', views_admin.AdminDeleteHostelView.as_view(), name='admin-delete-hostel'),
    path('featured-hostels/', views_admin.FeaturedHostelsView.as_view(), name='admin-featured-hostels'),
    
    # Analytics
    path('analytics/users/', views_admin.UserAnalyticsView.as_view(), name='admin-user-analytics'),
    path('analytics/hostels/', views_admin.HostelAnalyticsView.as_view(), name='admin-hostel-analytics'),
    
    # Security
    path('audit-logs/', views_admin.AuditLogListView.as_view(), name='admin-audit-logs'),
    path('fraud-alerts/', views_admin.FraudAlertsView.as_view(), name='admin-fraud-alerts'),
    path('sessions/', views_admin.ActiveSessionsView.as_view(), name='admin-sessions'),
    
    # Settings
    path('settings/', views_admin.SystemSettingsView.as_view(), name='admin-settings'),
    
    # Impersonation
    path('impersonate/start/', views_admin.ImpersonateStartView.as_view(), name='admin-impersonate-start'),
    path('impersonate/stop/', views_admin.ImpersonateStopView.as_view(), name='admin-impersonate-stop'),
    
    # Notifications
    path('notifications/', views_admin.NotificationListView.as_view(), name='admin-notifications'),
    path('notifications/<int:notification_id>/mark-read/', views_admin.MarkNotificationReadView.as_view(), name='admin-mark-read'),
    path('notifications/send-bulk/', views_admin.SendBulkNotificationView.as_view(), name='admin-send-bulk'),
    
    # SMS Balance
    path('sms/balance/', views_admin.SmsBalanceView.as_view(), name='admin-sms-balance'),
    
    # Announcements
    path('announcements/active/', views_admin.AnnouncementActiveView.as_view(), name='admin-announcement-active'),
    
    # ==================== EXISTING ADMIN API ENDPOINTS (keeping your existing ones) ====================
    path('admin/dashboard/stats/', views_admin.DashboardStatsView.as_view(), name='admin_dashboard_stats'),
    path('admin/students/', views_admin.StudentListView.as_view(), name='admin_students'),
    path('admin/students/<uuid:pk>/', views_admin.StudentDetailView.as_view(), name='admin_student_detail'),
    path('admin/owners/', views_admin.OwnerListView.as_view(), name='admin_owners'),
    path('admin/owners/<uuid:pk>/', views_admin.OwnerDetailView.as_view(), name='admin_owner_detail'),
    path('admin/owners/<uuid:owner_id>/approve/', views_admin.ApproveOwnerView.as_view(), name='admin_approve_owner'),
    path('admin/owners/<uuid:owner_id>/reject/', views_admin.RejectOwnerView.as_view(), name='admin_reject_owner'),
    path('admin/owners/<uuid:owner_id>/toggle-verified/', views_admin.ToggleVerifiedBadgeView.as_view(), name='admin_toggle_verified'),
    path('admin/users/<uuid:user_id>/toggle-status/', views_admin.ToggleUserStatusView.as_view(), name='admin_toggle_status'),
    path('admin/users/<uuid:user_id>/delete/', views_admin.DeleteUserView.as_view(), name='admin_delete_user'),
    path('admin/users/<uuid:user_id>/unlock/', views_admin.UnlockUserView.as_view(), name='admin_unlock_user'),
    path('admin/users/<uuid:user_id>/update-fraud-score/', views_admin.UpdateFraudScoreView.as_view(), name='admin_update_fraud'),
    path('admin/users/high-risk/', views_admin.HighRiskUsersView.as_view(), name='admin_high_risk'),
    path('admin/hostels/', views_admin.AdminHostelListView.as_view(), name='admin_hostels'),
    path('admin/hostels/<uuid:pk>/', views_admin.AdminHostelDetailView.as_view(), name='admin_hostel_detail'),
    path('admin/hostels/<uuid:hostel_id>/approve/', views_admin.AdminApproveHostelView.as_view(), name='admin_approve_hostel'),
    path('admin/hostels/<uuid:hostel_id>/toggle-featured/', views_admin.AdminToggleFeaturedView.as_view(), name='admin_toggle_featured'),
    path('admin/hostels/<uuid:hostel_id>/delete/', views_admin.AdminDeleteHostelView.as_view(), name='admin_delete_hostel'),
    path('admin/featured-hostels/', views_admin.FeaturedHostelsView.as_view(), name='admin_featured_hostels'),
    path('admin/subscription-plans/', views_admin.SubscriptionPlanListCreateView.as_view(), name='admin_subscription_plans'),
    path('admin/subscription-plans/<uuid:id>/', views_admin.SubscriptionPlanRetrieveUpdateDestroyView.as_view(), name='admin_subscription_plan_detail'),
    path('admin/plans/', views_admin.SubscriptionPlanListCreateView.as_view(), name='admin_plans'),
    path('admin/plans/<uuid:id>/', views_admin.SubscriptionPlanRetrieveUpdateDestroyView.as_view(), name='admin_plan_detail'),
    path('admin/owner-subscriptions/', views_admin.OwnerSubscriptionListView.as_view(), name='admin_owner_subscriptions'),
    path('admin/owner-subscriptions/<uuid:id>/', views_admin.OwnerSubscriptionDetailView.as_view(), name='admin_owner_subscription_detail'),
    path('admin/owner-subscriptions/<uuid:id>/update/', views_admin.OwnerSubscriptionUpdateView.as_view(), name='admin_owner_subscription_update'),
    path('admin/owner-subscriptions/<uuid:id>/delete/', views_admin.OwnerSubscriptionDeleteView.as_view(), name='admin_owner_subscription_delete'),
    path('admin/owner-subscriptions/<uuid:id>/extend/', views_admin.AdminExtendSubscriptionView.as_view(), name='admin_sub_extend'),
    path('admin/owner-subscriptions/<uuid:id>/terminate/', views_admin.AdminCancelSubscriptionView.as_view(), name='admin_sub_terminate'),
    path('admin/owner-subscriptions/create/', views_admin.OwnerSubscriptionCreateView.as_view(), name='admin_owner_subscription_create'),
    path('admin/chat/conversations/', views_admin.AdminConversationListView.as_view(), name='admin_chat_conversations'),
    path('admin/chat/conversations/<uuid:conversation_id>/messages/', views_admin.AdminConversationMessagesView.as_view(), name='admin_chat_messages'),
    path('admin/chat/conversations/<uuid:conversation_id>/send/', views_admin.AdminSendMessageView.as_view(), name='admin_chat_send'),
    path('admin/chat/conversations/<uuid:conversation_id>/typing/', views_admin.AdminTypingIndicatorView.as_view(), name='admin_chat_typing'),
    path('admin/notifications/', views_admin.NotificationListView.as_view(), name='admin_notifications'),
    path('admin/notifications/<int:notification_id>/mark-read/', views_admin.MarkNotificationReadView.as_view(), name='admin_mark_notification_read'),
    path('admin/notifications/send-bulk/', views_admin.SendBulkNotificationView.as_view(), name='admin_send_bulk_notification'),
    path('admin/audit-logs/', views_admin.AuditLogListView.as_view(), name='admin_audit_logs'),
    path('admin/fraud-alerts/', views_admin.FraudAlertsView.as_view(), name='admin_fraud_alerts'),
    path('admin/settings/', views_admin.SystemSettingsView.as_view(), name='admin_settings'),
    path('admin/analytics/users/', views_admin.UserAnalyticsView.as_view(), name='admin_user_analytics'),
    path('admin/analytics/hostels/', views_admin.HostelAnalyticsView.as_view(), name='admin_hostel_analytics'),
    path('admin/sessions/terminate-other/', views_admin.TerminateOtherSessionsView.as_view(), name='admin_terminate_sessions'),
    path('admin/sessions/active/', views_admin.ActiveSessionsView.as_view(), name='admin_active_sessions'),
    path('admin/sessions/', views_admin.ActiveSessionsView.as_view(), name='admin_sessions'),
    path('admin/test/email/', views_admin.TestEmailView.as_view(), name='admin_test_email'),
    path('admin/test/sms/', views_admin.TestSMSView.as_view(), name='admin_test_sms'),
    path('admin/test/mpesa/', views_admin.TestMpesaView.as_view(), name='admin_test_mpesa'),
    path('admin/error-logs/', views_admin.ErrorLogsView.as_view(), name='admin_error_logs'),
    path('activity-logs/', OwnerActivityLogView.as_view(), name='owner-activity-logs'),
]