from django.urls import path
from .views import (
    RoommateAdListCreateView, RoommateAdDetailView, MyRoommateAdsView,
    ReportRoommateAdView, AdminDeactivateAdView, AdminBlockUserView
)

urlpatterns = [
    path('', RoommateAdListCreateView.as_view(), name='roommate-list'),
    path('my/', MyRoommateAdsView.as_view(), name='my-roommate-ads'),
    path('<uuid:pk>/', RoommateAdDetailView.as_view(), name='roommate-detail'),
    path('<uuid:pk>/report/', ReportRoommateAdView.as_view(), name='roommate-report'),
    path('admin/ad/<uuid:pk>/deactivate/', AdminDeactivateAdView.as_view(), name='admin-deactivate-ad'),
    path('admin/user/<uuid:user_id>/block/', AdminBlockUserView.as_view(), name='admin-block-user'),
]