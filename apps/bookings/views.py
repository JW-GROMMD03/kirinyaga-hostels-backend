from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Q, Count
from datetime import timedelta
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer
from apps.accounts.models import User

# Helper permission for admin
class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser)

class IsStudentOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'student' or request.user.role == 'admin' or request.user.is_superuser
        )


# ==================== ADMIN ENDPOINTS ====================

class AdminBookingListView(generics.ListAPIView):
    """
    List all bookings for admin dashboard.
    Endpoint: /api/bookings/
    """
    permission_classes = [IsAdminUser]
    serializer_class = BookingSerializer

    def get_queryset(self):
        queryset = Booking.objects.select_related('student', 'hostel').order_by('-created_at')
        
        # Search by user email, name, or hostel name
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(student__email__icontains=search) |
                Q(student__full_name__icontains=search) |
                Q(hostel__name__icontains=search)
            )
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        return queryset


# ==================== STUDENT ENDPOINTS ====================

class StudentBookingListView(generics.ListAPIView):
    """List bookings for the authenticated student (or all for admin)"""
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role == 'student':
            return Booking.objects.filter(student=user).order_by('-created_at')
        elif user.role == 'owner':
            # Owners can see bookings for their hostels
            return Booking.objects.filter(hostel__owner=user).order_by('-created_at')
        elif user.role == 'admin' or user.is_superuser:
            return Booking.objects.all().order_by('-created_at')
        return Booking.objects.none()


class BookingCreateView(generics.CreateAPIView):
    """Create a new booking (students only)"""
    serializer_class = BookingCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        if self.request.user.role != 'student':
            raise permissions.PermissionDenied("Only students can create bookings")
        
        # Check for existing active booking
        hostel = serializer.validated_data.get('hostel')
        existing_booking = Booking.objects.filter(
            student=self.request.user,
            hostel=hostel,
            status__in=['pending', 'confirmed']
        ).first()
        
        if existing_booking:
            raise serializers.ValidationError({
                'error': 'You have already booked this hostel. You cannot book it again.',
                'existing_booking_id': str(existing_booking.id),
                'status': existing_booking.status
            })
        
        # Check if hostel is available
        if not hostel.available:
            raise serializers.ValidationError('This hostel is no longer available. Please choose another.')
        
        # Create booking with 4-hour expiry
        booking = serializer.save(
            student=self.request.user,
            expires_at=timezone.now() + timedelta(hours=4)
        )
        
        # Temporarily mark hostel as unavailable
        hostel.available = False
        hostel.save()
        
        # Create notification for hostel owner
        from apps.notifications.models import Notification
        Notification.objects.create(
            user=hostel.owner,
            type='booking',
            title='New Booking Request',
            message=f"{self.request.user.full_name} wants to book {hostel.name}. Payment window: 4 hours.",
            link=f"/owner/bookings.html?id={booking.id}"
        )


class BookingDetailView(generics.RetrieveUpdateAPIView):
    """Get or update a booking (student who owns it, or admin)"""
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin' or user.is_superuser:
            return Booking.objects.all()
        return Booking.objects.filter(student=user)


class CancelBookingView(APIView):
    """Cancel a booking and release the hostel"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            booking = Booking.objects.get(pk=pk)
            if booking.student != request.user and request.user.role != 'admin':
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            booking.status = 'cancelled'
            booking.save()
            
            # Release the hostel back to available
            if booking.hostel.available is False:
                other_active = Booking.objects.filter(
                    hostel=booking.hostel,
                    status='confirmed'
                ).exclude(id=booking.id).exists()
                if not other_active:
                    booking.hostel.available = True
                    booking.hostel.save()
            
            return Response({'status': 'success', 'message': 'Booking cancelled successfully'})
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=404)

class HostelBookingsView(generics.ListAPIView):
    """Get all bookings for a specific hostel (admin only)"""
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        hostel_id = self.kwargs.get('hostel_id')
        user = self.request.user
        if user.role == 'admin' or user.is_superuser:
            return Booking.objects.filter(hostel_id=hostel_id).order_by('-created_at')
        return Booking.objects.none()
    
class ConfirmPaymentView(APIView):
    """Confirm payment and mark booking as confirmed"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            booking = Booking.objects.get(pk=pk)
            
            # Check if user is owner or admin
            if booking.hostel.owner != request.user and request.user.role != 'admin':
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            booking.status = 'confirmed'
            booking.deposit_paid = True
            booking.save()
            
            # Hostel is already marked as unavailable from booking creation
            # No need to change again
            
            # Notify student
            from apps.notifications.models import Notification
            Notification.objects.create(
                user=booking.student,
                type='booking',
                title='Booking Confirmed',
                message=f"Your booking for {booking.hostel.name} has been confirmed! Welcome to your new home.",
                link=f"/student/bookings.html"
            )
            
            return Response({'status': 'success', 'message': 'Booking confirmed and hostel marked as taken'})
        except Booking.DoesNotExist:
            return Response({'error': 'Booking not found'}, status=404)


class MarkHostelAsTakenView(APIView):
    """Admin/Owner mark hostel as taken (available=False)"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, hostel_id):
        try:
            from apps.hostels.models import Hostel
            hostel = Hostel.objects.get(id=hostel_id)
            
            # Check permission
            if request.user.role != 'admin' and hostel.owner != request.user:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            hostel.available = False
            hostel.save()
            
            # Cancel any pending bookings for this hostel
            Booking.objects.filter(hostel=hostel, status='pending').update(status='cancelled')
            
            # Audit log
            from apps.accounts.models import AuditLog
            from apps.accounts.views_admin import get_client_ip
            AuditLog.objects.create(
                user=request.user,
                action='MARK_HOSTEL_TAKEN',
                action_category='hostel',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                details={'hostel_id': str(hostel.id), 'name': hostel.name}
            )
            
            return Response({'status': 'success', 'message': f'Hostel "{hostel.name}" marked as taken'})
        except Hostel.DoesNotExist:
            return Response({'error': 'Hostel not found'}, status=404)


class MarkHostelAsAvailableView(APIView):
    """Admin/Owner mark hostel as available (available=True)"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, hostel_id):
        try:
            from apps.hostels.models import Hostel
            hostel = Hostel.objects.get(id=hostel_id)
            
            if request.user.role != 'admin' and hostel.owner != request.user:
                return Response({'error': 'Permission denied'}, status=status.HTTP_403_FORBIDDEN)
            
            hostel.available = True
            hostel.save()
            
            return Response({'status': 'success', 'message': f'Hostel "{hostel.name}" marked as available'})
        except Hostel.DoesNotExist:
            return Response({'error': 'Hostel not found'}, status=404)


class HostelBookingsView(generics.ListAPIView):
    """Get all bookings for a specific hostel (admin only)"""
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        hostel_id = self.kwargs.get('hostel_id')
        user = self.request.user
        if user.role == 'admin' or user.is_superuser:
            return Booking.objects.filter(hostel_id=hostel_id).order_by('-created_at')
        return Booking.objects.none()


# ==================== OWNER DASHBOARD ENDPOINTS ====================

class OwnerBookingsSummaryView(APIView):
    """Get booking summary for the current owner (hostel owner)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Verify user is an owner
        if request.user.role != 'owner' and request.user.role != 'admin':
            return Response(
                {'error': 'Only owners can access this endpoint'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Get all bookings for the owner's hostels
        bookings = Booking.objects.filter(hostel__owner=request.user)
        
        total = bookings.count()
        pending = bookings.filter(status='pending').count()
        confirmed = bookings.filter(status='confirmed').count()
        cancelled = bookings.filter(status='cancelled').count()
        completed = bookings.filter(status='completed').count()
        
        # Recent bookings (last 5)
        recent = bookings.order_by('-created_at')[:5]
        recent_data = BookingSerializer(recent, many=True).data
        
        # Bookings for today
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        today_bookings = bookings.filter(
            created_at__gte=today_start,
            created_at__lt=today_end
        ).count()
        
        # This week's bookings
        week_start = timezone.now() - timedelta(days=timezone.now().weekday())
        week_bookings = bookings.filter(created_at__gte=week_start).count()
        
        return Response({
            'total': total,
            'pending': pending,
            'confirmed': confirmed,
            'cancelled': cancelled,
            'completed': completed,
            'today': today_bookings,
            'this_week': week_bookings,
            'recent': recent_data
        })


class OwnerBookingListView(generics.ListAPIView):
    """List all bookings for the current owner's hostels"""
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.role != 'owner' and self.request.user.role != 'admin':
            return Booking.objects.none()
        return Booking.objects.filter(hostel__owner=self.request.user).order_by('-created_at')


class OwnerBookingDetailView(generics.RetrieveAPIView):
    """Get detailed booking information for owner"""
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        if self.request.user.role != 'owner' and self.request.user.role != 'admin':
            return Booking.objects.none()
        return Booking.objects.filter(hostel__owner=self.request.user)


class UpdateBookingStatusView(APIView):
    """Update booking status (confirm/cancel) for owner"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            # Check if user is owner or admin
            if request.user.role != 'owner' and request.user.role != 'admin':
                return Response(
                    {'error': 'Permission denied'}, 
                    status=status.HTTP_403_FORBIDDEN
                )

            booking = Booking.objects.get(pk=pk, hostel__owner=request.user)
            new_status = request.data.get('status')
            
            valid_statuses = ['confirmed', 'cancelled']
            if new_status not in valid_statuses:
                return Response(
                    {'error': f'Invalid status. Must be one of: {", ".join(valid_statuses)}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            booking.status = new_status
            booking.save()
            
            if new_status == 'cancelled':
                # Release the hostel back to available
                other_active = Booking.objects.filter(
                    hostel=booking.hostel,
                    status='confirmed'
                ).exclude(id=booking.id).exists()
                if not other_active:
                    booking.hostel.available = True
                    booking.hostel.save()
            
            serializer = BookingSerializer(booking)
            return Response({
                'status': 'success',
                'message': f'Booking {new_status} successfully',
                'booking': serializer.data
            })
            
        except Booking.DoesNotExist:
            return Response(
                {'error': 'Booking not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )


class OwnerBookingStatsView(APIView):
    """Get detailed booking statistics for the owner"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role != 'owner' and request.user.role != 'admin':
            return Response(
                {'error': 'Only owners can access this endpoint'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        bookings = Booking.objects.filter(hostel__owner=request.user)
        
        # Monthly stats for the last 6 months
        monthly_stats = []
        now = timezone.now()
        for i in range(5, -1, -1):
            month = now - timedelta(days=30 * i)
            month_start = month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            
            month_bookings = bookings.filter(created_at__range=[month_start, month_end])
            monthly_stats.append({
                'month': month_start.strftime('%B %Y'),
                'total': month_bookings.count(),
                'confirmed': month_bookings.filter(status='confirmed').count(),
                'completed': month_bookings.filter(status='completed').count(),
                'cancelled': month_bookings.filter(status='cancelled').count()
            })
        
        # Stats by hostel
        hostel_stats = []
        for hostel in request.user.hostels.all():
            hostel_bookings = bookings.filter(hostel=hostel)
            hostel_stats.append({
                'hostel_id': str(hostel.id),
                'hostel_name': hostel.name,
                'total_bookings': hostel_bookings.count(),
                'confirmed': hostel_bookings.filter(status='confirmed').count(),
                'pending': hostel_bookings.filter(status='pending').count(),
                'cancelled': hostel_bookings.filter(status='cancelled').count()
            })
        
        return Response({
            'monthly_stats': monthly_stats,
            'hostel_stats': hostel_stats
        })