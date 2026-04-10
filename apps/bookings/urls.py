from django.urls import path
from . import views

urlpatterns = [
    # ==================== STUDENT ENDPOINTS (Primary) ====================
    # Student can access their own bookings via this endpoint
    path('', views.StudentBookingListView.as_view(), name='student-bookings'),
    
    # Create booking
    path('create/', views.BookingCreateView.as_view(), name='create-booking'),
    
    # Booking detail and actions - FIXED: int to uuid (bookings use UUID primary keys)
    path('<uuid:pk>/', views.BookingDetailView.as_view(), name='booking-detail'),
    path('<uuid:pk>/cancel/', views.CancelBookingView.as_view(), name='cancel-booking'),
    
    # ==================== ADMIN ENDPOINTS ====================
    path('admin/', views.AdminBookingListView.as_view(), name='admin-bookings'),
    path('hostel/<uuid:hostel_id>/', views.HostelBookingsView.as_view(), name='hostel-bookings'),
    
    # ==================== OWNER DASHBOARD ENDPOINTS ====================
    path('owner-summary/', views.OwnerBookingsSummaryView.as_view(), name='owner-bookings-summary'),
    path('owner/', views.OwnerBookingListView.as_view(), name='owner-bookings'),
    path('owner/<uuid:pk>/', views.OwnerBookingDetailView.as_view(), name='owner-booking-detail'),
    path('owner/<uuid:pk>/update-status/', views.UpdateBookingStatusView.as_view(), name='update-booking-status'),
    path('owner-stats/', views.OwnerBookingStatsView.as_view(), name='owner-booking-stats'),
]