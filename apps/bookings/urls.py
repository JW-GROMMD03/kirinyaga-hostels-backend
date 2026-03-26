from django.urls import path
from . import views

urlpatterns = [
    # Student endpoints
    path('student/', views.StudentBookingListView.as_view(), name='student-bookings'),
    path('create/', views.BookingCreateView.as_view(), name='create-booking'),
    path('<int:pk>/', views.BookingDetailView.as_view(), name='booking-detail'),
    path('<int:pk>/cancel/', views.CancelBookingView.as_view(), name='cancel-booking'),
    
    # Admin endpoints
    path('hostel/<int:hostel_id>/', views.HostelBookingsView.as_view(), name='hostel-bookings'),
    
    # Owner dashboard endpoints
    path('owner-summary/', views.OwnerBookingsSummaryView.as_view(), name='owner-bookings-summary'),
    path('owner/', views.OwnerBookingListView.as_view(), name='owner-bookings'),
    path('owner/<int:pk>/', views.OwnerBookingDetailView.as_view(), name='owner-booking-detail'),
    path('owner/<int:pk>/update-status/', views.UpdateBookingStatusView.as_view(), name='update-booking-status'),
    path('owner-stats/', views.OwnerBookingStatsView.as_view(), name='owner-booking-stats'),
]