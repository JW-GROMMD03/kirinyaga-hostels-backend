from django.urls import path
from . import views

urlpatterns = [
    path('hostel/<uuid:hostel_id>/', views.ReviewListView.as_view(), name='review-list'),
    path('hostel/<uuid:hostel_id>/rating/', views.HostelRatingView.as_view(), name='hostel-rating'),
    path('create/', views.ReviewCreateView.as_view(), name='review-create'),
    path('<uuid:pk>/', views.ReviewDetailView.as_view(), name='review-detail'),
    path('recent/', views.RecentReviewsView.as_view(), name='recent-reviews'),
]