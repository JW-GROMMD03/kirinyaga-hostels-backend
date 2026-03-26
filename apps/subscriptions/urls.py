from django.urls import path
from . import views
from .views import (
    PlanListCreateView,
    PlanRetrieveUpdateDestroyView,
    PlanDeleteView,
    OwnerSubscriptionListView,
    OwnerSubscriptionDetailView,
    ExtendSubscriptionView,
    TerminateSubscriptionView,
    DeleteSubscriptionView,
    OwnerSubscriptionView,
    OwnerSubscriptionHistoryView,
    SubscriptionPlanListView,
    PlanListView,
    AdminPlanListView,
    DebugDbDataView,
    FixSubscriptionView,
    TestAllEndpointsView,
)

urlpatterns = [
    # ==================== PUBLIC/OWNER ENDPOINTS ====================
    # Plans
    path('plans/', SubscriptionPlanListView.as_view(), name='plan-list'),
    
    # Owner subscription
    path('owner-subscriptions/me/', OwnerSubscriptionView.as_view(), name='my-subscription'),
    path('history/', OwnerSubscriptionHistoryView.as_view(), name='subscription-history'),
    
    # REMOVED: All payment-related endpoints
    # path('initiate-payment/', InitiatePaymentView.as_view(), name='initiate-payment'),
    # path('payments/', UserPaymentListView.as_view(), name='payment-list'),
    # path('payments/<uuid:id>/', PaymentDetailView.as_view(), name='payment-detail'),
    # path('mpesa-callback/', MpesaCallbackView.as_view(), name='mpesa-callback'),
    
    # ==================== ADMIN ENDPOINTS ====================
    # Plan management
    path('admin/plans/', PlanListCreateView.as_view(), name='admin-plan-list'),
    path('admin/plans/<int:pk>/', PlanRetrieveUpdateDestroyView.as_view(), name='admin-plan-detail'),
    path('admin/plans/<int:pk>/delete/', PlanDeleteView.as_view(), name='admin-plan-delete'),
    
    # Owner subscription management
    path('admin/owner-subscriptions/', OwnerSubscriptionListView.as_view(), name='admin-owner-subscriptions'),
    path('admin/owner-subscriptions/<uuid:pk>/', OwnerSubscriptionDetailView.as_view(), name='admin-owner-subscription-detail'),
    path('admin/owner-subscriptions/<uuid:pk>/extend/', ExtendSubscriptionView.as_view(), name='admin-extend-subscription'),
    path('admin/owner-subscriptions/<uuid:pk>/terminate/', TerminateSubscriptionView.as_view(), name='admin-terminate-subscription'),
    path('admin/owner-subscriptions/<uuid:pk>/delete/', DeleteSubscriptionView.as_view(), name='admin-delete-subscription'),
    
    # REMOVED: Payment management endpoints
    # path('admin/payments/', PaymentListView.as_view(), name='admin-payment-list'),
    # path('admin/payments/<uuid:id>/', AdminPaymentDetailView.as_view(), name='admin-payment-detail'),
    
    # Public and debug endpoints
    path('public/plans/', PlanListView.as_view(), name='public-plan-list'),
    path('admin/all-plans/', AdminPlanListView.as_view(), name='admin-all-plans'),
    path('debug/db-data/', views.DebugDbDataView.as_view(), name='debug-db-data'),
    path('fix-subscription/', views.FixSubscriptionView.as_view(), name='fix-subscription'),
    path('debug/test-all/', views.TestAllEndpointsView.as_view(), name='test-all'),
]