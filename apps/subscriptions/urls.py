from django.urls import path
from . import views

urlpatterns = [
    # Public/User endpoints
    path('plans/', views.SubscriptionPlanListView.as_view(), name='subscription-plans'),
    path('my/', views.CurrentSubscriptionView.as_view(), name='my-subscription'),
    path('create/', views.CreateSubscriptionView.as_view(), name='create-subscription'),
    path('history/', views.SubscriptionHistoryView.as_view(), name='subscription-history'),
    path('payments/', views.PaymentHistoryView.as_view(), name='payment-history'),
    path('cancel/', views.CancelSubscriptionView.as_view(), name='cancel-subscription'),
    path('auto-renew/', views.ToggleAutoRenewView.as_view(), name='toggle-auto-renew'),
    path('check-hostel-eligibility/', views.CheckHostelEligibilityView.as_view(), name='check-hostel-eligibility'),
    
    # Admin endpoints
    path('admin/list/', views.AdminSubscriptionListView.as_view(), name='admin-subscriptions'),
    path('admin/activate/', views.AdminManualActivateSubscriptionView.as_view(), name='admin-activate'),
    path('admin/stats/', views.AdminSubscriptionStatsView.as_view(), name='admin-stats'),
    path('check-analytics/', views.CheckAnalyticsAccessView.as_view(), name='check-analytics'),
]