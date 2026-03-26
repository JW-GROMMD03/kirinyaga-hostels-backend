from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Avg, Count
from django.utils import timezone
from datetime import timedelta
from .models import Review
from .serializers import ReviewSerializer, ReviewCreateSerializer

class IsStudentOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'student' or request.user.role == 'admin' or request.user.is_superuser
        )

class ReviewListView(generics.ListAPIView):
    """List approved reviews for a hostel"""
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        hostel_id = self.kwargs.get('hostel_id')
        return Review.objects.filter(hostel_id=hostel_id, is_approved=True).order_by('-created_at')

class ReviewCreateView(generics.CreateAPIView):
    """Create a new review (students only)"""
    serializer_class = ReviewCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if self.request.user.role != 'student':
            raise permissions.PermissionDenied("Only students can create reviews")
        serializer.save()

class ReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get, update or delete a review"""
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_superuser:
            return Review.objects.all()
        return Review.objects.filter(student=user)

class HostelRatingView(APIView):
    """Get average rating for a hostel"""
    permission_classes = [permissions.AllowAny]

    def get(self, request, hostel_id):
        stats = Review.objects.filter(hostel_id=hostel_id, is_approved=True).aggregate(
            avg_rating=Avg('rating'),
            total_reviews=Count('id')
        )
        distribution = Review.objects.filter(hostel_id=hostel_id, is_approved=True).values('rating').annotate(
            count=Count('id')
        ).order_by('rating')
        
        dist_dict = {1:0, 2:0, 3:0, 4:0, 5:0}
        for item in distribution:
            dist_dict[item['rating']] = item['count']
        
        return Response({
            'average_rating': round(stats['avg_rating'] or 0, 1),
            'total_reviews': stats['total_reviews'] or 0,
            'distribution': [dist_dict[i] for i in range(1, 6)]
        })

class RecentReviewsView(generics.ListAPIView):
    """Get recent reviews across all hostels"""
    serializer_class = ReviewSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        days = int(self.request.query_params.get('days', 7))
        cutoff = timezone.now() - timedelta(days=days)
        return Review.objects.filter(created_at__gte=cutoff, is_approved=True).order_by('-created_at')[:20]