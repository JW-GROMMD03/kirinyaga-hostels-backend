from django.urls import path
from . import views_admin

urlpatterns = [
    # Dashboard
    path('dashboard/stats/', views_admin.DashboardStatsView.as_view(), name='admin_dashboard_stats'),

    # Student management
    path('students/', views_admin.StudentListView.as_view(), name='admin_students'),
    path('students/<uuid:pk>/', views_admin.StudentDetailView.as_view(), name='admin_student_detail'),

    # Owner management
    path('owners/', views_admin.OwnerListView.as_view(), name='admin_owners'),
    path('owners/<uuid:pk>/', views_admin.OwnerDetailView.as_view(), name='admin_owner_detail'),
    path('owners/<uuid:owner_id>/approve/', views_admin.ApproveOwnerView.as_view(), name='admin_approve_owner'),
    path('owners/<uuid:owner_id>/reject/', views_admin.RejectOwnerView.as_view(), name='admin_reject_owner'),
    path('owners/<uuid:owner_id>/toggle-verified/', views_admin.ToggleVerifiedBadgeView.as_view(), name='admin_toggle_verified'),

    # User actions
    path('users/<uuid:user_id>/toggle-status/', views_admin.ToggleUserStatusView.as_view(), name='admin_toggle_status'),
    path('users/<uuid:user_id>/delete/', views_admin.DeleteUserView.as_view(), name='admin_delete_user'),
    path('users/<uuid:user_id>/unlock/', views_admin.UnlockUserView.as_view(), name='admin_unlock_user'),
    path('users/<uuid:user_id>/update-fraud-score/', views_admin.UpdateFraudScoreView.as_view(), name='admin_update_fraud'),
    path('users/high-risk/', views_admin.HighRiskUsersView.as_view(), name='admin_high_risk'),

    # Hostel management
    path('hostels/', views_admin.AdminHostelListView.as_view(), name='admin_hostels'),
    path('hostels/<uuid:pk>/', views_admin.AdminHostelDetailView.as_view(), name='admin_hostel_detail'),
    path('hostels/<uuid:hostel_id>/approve/', views_admin.AdminApproveHostelView.as_view(), name='admin_approve_hostel'),
    path('hostels/<uuid:hostel_id>/toggle-featured/', views_admin.AdminToggleFeaturedView.as_view(), name='admin_toggle_featured'),
    path('hostels/<uuid:hostel_id>/delete/', views_admin.AdminDeleteHostelView.as_view(), name='admin_delete_hostel'),
    path('featured-hostels/', views_admin.FeaturedHostelsView.as_view(), name='admin_featured_hostels'),

    # REMOVED: All subscription-related endpoints
    # path('subscription-plans/', ...),
    # path('subscription-plans/<uuid:id>/', ...),
    # path('plans/', ...),
    # path('plans/<uuid:id>/', ...),
    # path('owner-subscriptions/', ...),
    # path('owner-subscriptions/<uuid:id>/', ...),

    # Chat
    path('chat/conversations/', views_admin.AdminConversationListView.as_view(), name='admin_chat_conversations'),
    path('chat/conversations/<uuid:conversation_id>/messages/', views_admin.AdminConversationMessagesView.as_view(), name='admin_chat_messages'),
    path('chat/conversations/<uuid:conversation_id>/send/', views_admin.AdminSendMessageView.as_view(), name='admin_chat_send'),
    path('chat/conversations/<uuid:conversation_id>/typing/', views_admin.AdminTypingIndicatorView.as_view(), name='admin_chat_typing'),

    # Notifications
    path('notifications/', views_admin.NotificationListView.as_view(), name='admin_notifications'),
    path('notifications/<int:notification_id>/mark-read/', views_admin.MarkNotificationReadView.as_view(), name='admin_mark_notification_read'),
    path('notifications/send-bulk/', views_admin.SendBulkNotificationView.as_view(), name='admin_send_bulk_notification'),

    # Audit logs
    path('audit-logs/', views_admin.AuditLogListView.as_view(), name='admin_audit_logs'),

    # Fraud alerts
    path('fraud-alerts/', views_admin.FraudAlertsView.as_view(), name='admin_fraud_alerts'),

    # System settings
    path('settings/', views_admin.SystemSettingsView.as_view(), name='admin_settings'),

    # Analytics
    path('analytics/users/', views_admin.UserAnalyticsView.as_view(), name='admin_user_analytics'),
    path('analytics/hostels/', views_admin.HostelAnalyticsView.as_view(), name='admin_hostel_analytics'),

    # Session management
    path('sessions/terminate-other/', views_admin.TerminateOtherSessionsView.as_view(), name='admin_terminate_sessions'),
    path('sessions/active/', views_admin.ActiveSessionsView.as_view(), name='admin_active_sessions'),

    # Testing endpoints
    path('test/email/', views_admin.TestEmailView.as_view(), name='admin_test_email'),
    path('test/sms/', views_admin.TestSMSView.as_view(), name='admin_test_sms'),
    path('test/mpesa/', views_admin.TestMpesaView.as_view(), name='admin_test_mpesa'),
    path('error-logs/', views_admin.ErrorLogsView.as_view(), name='admin_error_logs'),
]