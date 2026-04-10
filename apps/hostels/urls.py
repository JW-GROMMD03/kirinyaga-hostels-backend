from django.urls import path
from .views import (
    HostelSearchView, HostelDetailView, OwnerHostelListView,
    HostelCreateView, HostelUpdateView, HostelDeleteView,
    SavedHostelListCreateView, SavedHostelDeleteView,
    RecommendedHostelsView, AmenityListView, OwnerHostelDetailView,
    HostelReviewListCreateView, AvailabilityView, HostelStatsView
)

urlpatterns = [
    # ==================== PUBLIC ENDPOINTS ====================
    # Main search endpoint for students to find hostels with filtering
    path('', HostelSearchView.as_view(), name='hostel-list'),
    path('search/', HostelSearchView.as_view(), name='hostel-search'),  # Alias for search
    path('saved/<int:pk>/', SavedHostelDeleteView.as_view(), name='saved-hostel-delete')
    
    # Get all available amenities for filtering
    path('amenities/', AmenityListView.as_view(), name='amenity-list'),
    path('amenities/all/', AmenityListView.as_view(), name='amenity-list-all'),  # Alias
    
    # Get recommended hostels based on user preferences
    path('recommended/', RecommendedHostelsView.as_view(), name='recommended-hostels'),
    path('recommendations/', RecommendedHostelsView.as_view(), name='hostel-recommendations'),  # Alias
    
    # Get detailed information about a specific hostel
    path('<uuid:pk>/', HostelDetailView.as_view(), name='hostel-detail'),
    path('detail/<uuid:pk>/', HostelDetailView.as_view(), name='hostel-detail-alt'),  # Alias
    path('view/<uuid:pk>/', HostelDetailView.as_view(), name='hostel-view'),  # Alias
    
    # ==================== OWNER ENDPOINTS ====================
    # Get all hostels belonging to the logged-in owner
    path('my/', OwnerHostelListView.as_view(), name='my-hostels'),
    path('owner/', OwnerHostelListView.as_view(), name='owner-hostels'),  # Alias
    path('my-hostels/', OwnerHostelListView.as_view(), name='my-hostels-alt'),  # Alias
    
    # Get detailed information about a specific hostel (owner only)
    path('my/<uuid:pk>/', OwnerHostelDetailView.as_view(), name='my-hostel-detail'),
    path('owner/<uuid:pk>/', OwnerHostelDetailView.as_view(), name='owner-hostel-detail'),  # Alias
    path('my/detail/<uuid:pk>/', OwnerHostelDetailView.as_view(), name='my-hostel-detail-alt'),  # Alias
    
    # Get statistics for owner's hostels (total, approved, pending, etc.)
    path('my/stats/', HostelStatsView.as_view(), name='hostel-stats'),
    path('owner/stats/', HostelStatsView.as_view(), name='owner-stats'),  # Alias
    path('my/statistics/', HostelStatsView.as_view(), name='hostel-statistics'),  # Alias
    
    # Create a new hostel
    path('create/', HostelCreateView.as_view(), name='hostel-create'),
    path('new/', HostelCreateView.as_view(), name='hostel-new'),  # Alias
    path('add/', HostelCreateView.as_view(), name='hostel-add'),  # Alias
    
    # Update an existing hostel
    path('<uuid:pk>/update/', HostelUpdateView.as_view(), name='hostel-update'),
    path('update/<uuid:pk>/', HostelUpdateView.as_view(), name='hostel-update-alt'),  # Alias
    path('<uuid:pk>/edit/', HostelUpdateView.as_view(), name='hostel-edit'),  # Alias
    
    # Delete a hostel
    path('<uuid:pk>/delete/', HostelDeleteView.as_view(), name='hostel-delete'),
    path('delete/<uuid:pk>/', HostelDeleteView.as_view(), name='hostel-delete-alt'),  # Alias
    path('<uuid:pk>/remove/', HostelDeleteView.as_view(), name='hostel-remove'),  # Alias
    
    # ==================== STUDENT SAVED HOSTELS ENDPOINTS ====================
    # Get all saved hostels for the logged-in student
    path('saved/', SavedHostelListCreateView.as_view(), name='saved-hostels'),
    path('favorites/', SavedHostelListCreateView.as_view(), name='favorite-hostels'),  # Alias
    path('bookmarks/', SavedHostelListCreateView.as_view(), name='bookmarked-hostels'),  # Alias
    
    # Save a new hostel (POST to same endpoint)
    path('saved/add/', SavedHostelListCreateView.as_view(), name='save-hostel'),  # Alias
    
    # Remove a hostel from saved list
    path('saved/<uuid:pk>/', SavedHostelDeleteView.as_view(), name='delete-saved'),
    path('saved/remove/<uuid:pk>/', SavedHostelDeleteView.as_view(), name='remove-saved'),  # Alias
    path('favorites/<uuid:pk>/', SavedHostelDeleteView.as_view(), name='delete-favorite'),  # Alias
    path('unsave/<uuid:pk>/', SavedHostelDeleteView.as_view(), name='unsave-hostel'),  # Alias
    
    # ==================== REVIEW ENDPOINTS ====================
    # Get all reviews for a specific hostel
    path('<uuid:hostel_id>/reviews/', HostelReviewListCreateView.as_view(), name='hostel-reviews'),
    path('reviews/hostel/<uuid:hostel_id>/', HostelReviewListCreateView.as_view(), name='hostel-reviews-alt'),  # Alias
    
    # Create a new review for a hostel
    path('<uuid:hostel_id>/review/', HostelReviewListCreateView.as_view(), name='create-review'),
    path('review/add/<uuid:hostel_id>/', HostelReviewListCreateView.as_view(), name='add-review'),  # Alias
    
    # ==================== AVAILABILITY ENDPOINTS ====================
    # Get availability for a specific hostel
    path('<uuid:hostel_id>/availability/', AvailabilityView.as_view(), name='hostel-availability'),
    path('availability/hostel/<uuid:hostel_id>/', AvailabilityView.as_view(), name='hostel-availability-alt'),  # Alias
    
    # Get availability for a specific date
    path('<uuid:hostel_id>/availability/<str:date>/', AvailabilityView.as_view(), name='hostel-availability-date'),
    
    # Create availability entries (batch)
    path('<uuid:hostel_id>/availability/batch/', AvailabilityView.as_view(), name='hostel-availability-batch'),
    
    # ==================== NEARBY HOSTELS ENDPOINTS ====================
    # Get hostels near a location
    path('nearby/', HostelSearchView.as_view(), name='nearby-hostels'),
    path('near/<str:lat>/<str:lng>/<int:radius>/', HostelSearchView.as_view(), name='hostels-near'),
    
    # ==================== SIMILAR HOSTELS ENDPOINTS ====================
    # Get hostels similar to a specific hostel
    path('<uuid:pk>/similar/', RecommendedHostelsView.as_view(), name='similar-hostels'),
    
    # ==================== CATEGORY ENDPOINTS ====================
    # Get hostels by room type
    path('type/<str:room_type>/', HostelSearchView.as_view(), name='hostels-by-type'),
    
    # Get hostels by price range
    path('price/<int:min>/<int:max>/', HostelSearchView.as_view(), name='hostels-by-price'),
    
    # ==================== FEATURED HOSTELS ENDPOINTS ====================
    # Get featured hostels
    path('featured/', HostelSearchView.as_view(), name='featured-hostels'),
    
    # ==================== ANALYTICS ENDPOINTS ====================
    # Get detailed analytics for a hostel
    path('<uuid:pk>/analytics/', HostelStatsView.as_view(), name='hostel-analytics'),
    path('analytics/hostel/<uuid:pk>/', HostelStatsView.as_view(), name='hostel-analytics-alt'),  # Alias

]