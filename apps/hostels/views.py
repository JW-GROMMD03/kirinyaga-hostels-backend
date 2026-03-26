from rest_framework import generics, permissions, filters, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, NotFound
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q, Count, Avg, Sum
from django.db import transaction
from django.utils import timezone
import logging
import traceback

from .models import Hostel, HostelImage, SavedHostel, Amenity, HostelAmenity, HostelReview, Availability
from .serializers import (
    HostelListSerializer, HostelDetailSerializer, HostelCreateUpdateSerializer,
    SavedHostelSerializer, AmenitySerializer, HostelReviewSerializer,
    AvailabilitySerializer, SimpleHostelSerializer
)
from apps.subscriptions.models import OwnerSubscription
from apps.accounts.models import AuditLog

logger = logging.getLogger(__name__)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class HostelSearchView(generics.ListAPIView):
    """Public view for searching approved hostels"""
    serializer_class = HostelListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    
    filterset_fields = {
        'room_type': ['exact'],
        'price': ['gte', 'lte'],
        'distance_to_university': ['lte', 'gte'],
        'available': ['exact'],
        'is_featured': ['exact'],
        'capacity': ['gte', 'lte'],
    }
    
    search_fields = ['name', 'address', 'description']
    ordering_fields = ['price', 'distance_to_university', 'created_at', 'views_count']

    def get_queryset(self):
        queryset = Hostel.objects.filter(
            is_approved=True, 
            available=True
        ).select_related('owner').prefetch_related('images', 'amenities__amenity')
        
        # Amenities: single comma-separated string → OR condition
        amenities_param = self.request.query_params.get('amenities')
        if amenities_param:
            amenity_ids = amenities_param.split(',')
            q_filter = Q()
            for aid in amenity_ids:
                q_filter |= Q(amenities__amenity_id=aid)
            queryset = queryset.filter(q_filter).distinct()
        
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius')
        
        if lat and lng and radius:
            queryset = queryset.filter(
                location_lat__range=(float(lat) - float(radius)/111, float(lat) + float(radius)/111),
                location_lng__range=(float(lng) - float(radius)/111, float(lng) + float(radius)/111)
            )
        
        return queryset.distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class HostelDetailView(generics.RetrieveAPIView):
    """Public view for hostel details"""
    queryset = Hostel.objects.filter(is_approved=True, available=True)
    serializer_class = HostelDetailSerializer
    permission_classes = [permissions.AllowAny]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.increment_views()
        
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action='VIEW_HOSTEL',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'hostel_id': str(instance.id), 'name': instance.name}
        )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class OwnerHostelListView(generics.ListAPIView):
    """List all hostels for the logged-in owner"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HostelListSerializer

    def get_queryset(self):
        user = self.request.user
        print(f"\n=== OwnerHostelListView ===")
        print(f"User: {user.email} (ID: {user.id})")
        print(f"User role: {user.role}")
        
        if not user.is_authenticated:
            print("User is not authenticated")
            return Hostel.objects.none()
        
        if user.role != 'owner':
            print(f"User role is '{user.role}', not 'owner'")
            return Hostel.objects.none()
        
        print(f"Fetching hostels for owner ID: {user.id}")
        queryset = Hostel.objects.filter(owner=user).order_by('-created_at')
        
        count = queryset.count()
        print(f"Found {count} hostels")
        print(f"SQL: {str(queryset.query)}")
        
        if count == 0:
            total_hostels = Hostel.objects.count()
            print(f"Total hostels in database: {total_hostels}")
            if total_hostels > 0:
                sample = Hostel.objects.first()
                if sample:
                    print(f"Sample hostel - ID: {sample.id}, Name: {sample.name}, Owner ID: {sample.owner_id}")
        
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            print("\n=== Processing OwnerHostelListView request ===")
            queryset = self.get_queryset()
            
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                print(f"Returning paginated response with {len(serializer.data)} items")
                return self.get_paginated_response(serializer.data)
            
            serializer = self.get_serializer(queryset, many=True)
            print(f"Returning response with {len(serializer.data)} items")
            
            if len(serializer.data) > 0:
                print(f"First hostel data: {serializer.data[0]}")
            
            return Response(serializer.data)
            
        except Exception as e:
            print(f"ERROR in OwnerHostelListView: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': 'Failed to load hostels', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class OwnerHostelDetailView(generics.RetrieveAPIView):
    """Get detailed information about a specific hostel (owner only)"""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = HostelDetailSerializer

    def get_queryset(self):
        if self.request.user.role != 'owner':
            return Hostel.objects.none()
        return Hostel.objects.filter(owner=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class HostelCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        print("\n=== HostelCreateView ===")
        print(f"User: {request.user.email} (ID: {request.user.id})")
        print(f"User role: {request.user.role}")
        print(f"Request data keys: {list(request.data.keys())}")
        print(f"Files: {list(request.FILES.keys())}")
        
        if request.user.role != 'owner':
            raise PermissionDenied("Only owners can create hostels.")
        
        subscription = OwnerSubscription.objects.filter(
            owner=request.user,
            is_active=True,
            end_date__gte=timezone.now()
        ).first()
        if not subscription:
            return Response(
                {'error': 'Your subscription has expired. Please renew to add hostels.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        current_count = Hostel.objects.filter(owner=request.user).count()
        if subscription.plan and subscription.plan.max_hostels > 0:
            if current_count >= subscription.plan.max_hostels:
                return Response(
                    {'error': f'You have reached your hostel limit ({subscription.plan.max_hostels}). Upgrade your plan to add more.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        data = {
            'name': request.data.get('name'),
            'description': request.data.get('description', ''),
            'room_type': request.data.get('room_type', 'bedsitter'),
            'capacity': int(request.data.get('capacity', 1)),
            'price': request.data.get('price'),
            'deposit': request.data.get('deposit', 0),
            'utilities': request.data.get('utilities', 0),
            'address': request.data.get('address'),
            'location_lat': request.data.get('location_lat'),
            'location_lng': request.data.get('location_lng'),
            'distance_to_university': request.data.get('distance_to_university'),
            'other_amenities': request.data.get('other_amenities', '')
        }

        hostel = Hostel.objects.create(owner=request.user, **data)
        print(f"Hostel created: {hostel.id}")

        try:
            image_fields = ['photo1', 'photo2', 'photo3', 'photo4', 'photo5', 'photo6']
            for i, field in enumerate(image_fields):
                if field in request.FILES:
                    image_file = request.FILES[field]
                    description = request.data.get(f'{field}_desc', '')

                    HostelImage.objects.create(
                        hostel=hostel,
                        image=image_file,
                        description=description,
                        is_primary=(i == 0)
                    )
                    print(f"Image uploaded: {field}")

            amenities = request.data.getlist('amenities[]')
            if amenities:
                for amenity_id in amenities:
                    HostelAmenity.objects.create(
                        hostel=hostel,
                        amenity_id=amenity_id
                    )
                print(f"Added {len(amenities)} amenities")

            AuditLog.objects.create(
                user=request.user,
                action='CREATE_HOSTEL',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'hostel_id': str(hostel.id), 'name': hostel.name}
            )

            serializer = HostelDetailSerializer(hostel, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error during image upload or amenity creation: {e}")
            traceback.print_exc()
            # Re-raise to trigger transaction rollback
            raise


class HostelUpdateView(APIView):
    """Update an existing hostel"""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, pk):
        print(f"\n=== HostelUpdateView for ID: {pk} ===")
        print(f"User: {request.user.email}")
        
        try:
            hostel = Hostel.objects.get(pk=pk)
            print(f"Found hostel: {hostel.name}, Owner ID: {hostel.owner_id}")
            
            if hostel.owner != request.user:
                print(f"Ownership check failed. Hostel owner: {hostel.owner_id}, Request user: {request.user.id}")
                raise PermissionDenied("You can only edit your own hostels.")
            
            for field in ['name', 'description', 'room_type', 'capacity', 'price', 
                         'deposit', 'utilities', 'address', 'location_lat', 'location_lng',
                         'distance_to_university', 'other_amenities']:
                if field in request.data:
                    setattr(hostel, field, request.data[field])
            
            hostel.is_approved = False
            hostel.save()
            print(f"Hostel updated successfully. Approval reset to False")
            
            image_fields = ['photo1', 'photo2', 'photo3', 'photo4', 'photo5', 'photo6']
            new_images = False
            for field in image_fields:
                if field in request.FILES:
                    new_images = True
                    break
            
            if new_images:
                hostel.images.all().delete()
                for i, field in enumerate(image_fields):
                    if field in request.FILES:
                        image_file = request.FILES[field]
                        description = request.data.get(f'{field}_desc', '')
                        
                        HostelImage.objects.create(
                            hostel=hostel,
                            image=image_file,
                            description=description,
                            is_primary=(i == 0)
                        )
                        print(f"Image uploaded: {field}")
            
            if 'amenities[]' in request.data:
                amenities = request.data.getlist('amenities[]')
                hostel.amenities.all().delete()
                for amenity_id in amenities:
                    HostelAmenity.objects.create(
                        hostel=hostel,
                        amenity_id=amenity_id
                    )
                print(f"Updated {len(amenities)} amenities")
            
            AuditLog.objects.create(
                user=request.user,
                action='UPDATE_HOSTEL',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'hostel_id': str(hostel.id), 'name': hostel.name}
            )
            
            response_serializer = HostelDetailSerializer(
                hostel,
                context={'request': request}
            )
            return Response(response_serializer.data)
            
        except Hostel.DoesNotExist:
            print(f"Hostel with ID {pk} not found")
            raise NotFound("Hostel not found")
        except Exception as e:
            print(f"Error updating hostel: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class HostelDeleteView(APIView):
    """Delete a hostel"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        print(f"\n=== HostelDeleteView for ID: {pk} ===")
        print(f"User: {request.user.email}")
        
        try:
            hostel = Hostel.objects.get(pk=pk)
            print(f"Found hostel: {hostel.name}, Owner ID: {hostel.owner_id}")
            
            if hostel.owner != request.user:
                print(f"Ownership check failed. Hostel owner: {hostel.owner_id}, Request user: {request.user.id}")
                raise PermissionDenied("You can only delete your own hostels.")
            
            AuditLog.objects.create(
                user=request.user,
                action='DELETE_HOSTEL',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                details={'hostel_id': str(hostel.id), 'name': hostel.name}
            )
            
            hostel_name = hostel.name
            hostel.delete()
            print(f"Hostel '{hostel_name}' deleted successfully")
            
            return Response(
                {'status': 'success', 'message': 'Hostel deleted successfully'},
                status=status.HTTP_200_OK
            )
            
        except Hostel.DoesNotExist:
            print(f"Hostel with ID {pk} not found")
            raise NotFound("Hostel not found")
        except Exception as e:
            print(f"Error deleting hostel: {str(e)}")
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SavedHostelListCreateView(generics.ListCreateAPIView):
    """List and create saved hostels for students"""
    serializer_class = SavedHostelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SavedHostel.objects.filter(
            user=self.request.user
        ).select_related('hostel').order_by('-saved_at')

    def perform_create(self, serializer):
        hostel_id = self.request.data.get('hostel_id')
        try:
            hostel = Hostel.objects.get(id=hostel_id, is_approved=True, available=True)
            serializer.save(user=self.request.user, hostel=hostel)
        except Hostel.DoesNotExist:
            raise NotFound("Hostel not found or not available")


class SavedHostelDeleteView(generics.DestroyAPIView):
    """Delete a saved hostel"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SavedHostel.objects.filter(user=self.request.user)


class RecommendedHostelsView(generics.ListAPIView):
    """Get recommended hostels based on user preferences"""
    serializer_class = HostelListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        base_qs = Hostel.objects.filter(
            is_approved=True, 
            available=True
        ).select_related('owner').prefetch_related('images', 'amenities__amenity')
        
        if hasattr(user, 'student_profile') and user.student_profile:
            profile = user.student_profile
            if profile.budget_min and profile.budget_max:
                base_qs = base_qs.filter(
                    price__gte=profile.budget_min,
                    price__lte=profile.budget_max
                )
        
        return base_qs.order_by('-is_featured', '-created_at')[:20]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class AmenityListView(generics.ListAPIView):
    """List all amenities"""
    queryset = Amenity.objects.all().order_by('name')
    serializer_class = AmenitySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class HostelReviewListCreateView(generics.ListCreateAPIView):
    """List and create reviews for a hostel"""
    serializer_class = HostelReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        hostel_id = self.kwargs.get('hostel_id')
        return HostelReview.objects.filter(
            hostel_id=hostel_id,
            is_approved=True
        ).select_related('user').order_by('-created_at')

    def perform_create(self, serializer):
        hostel_id = self.kwargs.get('hostel_id')
        try:
            hostel = Hostel.objects.get(id=hostel_id, is_approved=True)
            
            if HostelReview.objects.filter(hostel=hostel, user=self.request.user).exists():
                raise PermissionDenied("You have already reviewed this hostel.")
            
            serializer.save(hostel=hostel)
            
        except Hostel.DoesNotExist:
            raise NotFound("Hostel not found")


class AvailabilityView(generics.ListCreateAPIView):
    """Manage hostel availability (for owners)"""
    serializer_class = AvailabilitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        hostel_id = self.kwargs.get('hostel_id')
        try:
            hostel = Hostel.objects.get(id=hostel_id)
            
            if hostel.owner != self.request.user:
                raise PermissionDenied("You can only manage your own hostels.")
            
            return Availability.objects.filter(hostel=hostel).order_by('date')
        except Hostel.DoesNotExist:
            raise NotFound("Hostel not found")

    def perform_create(self, serializer):
        hostel_id = self.kwargs.get('hostel_id')
        try:
            hostel = Hostel.objects.get(id=hostel_id)
            
            if hostel.owner != self.request.user:
                raise PermissionDenied("You can only manage your own hostels.")
            
            serializer.save(hostel=hostel)
        except Hostel.DoesNotExist:
            raise NotFound("Hostel not found")


class HostelStatsView(APIView):
    """Get statistics for owner's hostels"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        print(f"\n=== HostelStatsView for user: {request.user.email} ===")
        
        if request.user.role != 'owner':
            print(f"User role is '{request.user.role}', not 'owner'")
            return Response({'error': 'Only owners can access stats'}, status=403)
        
        hostels = Hostel.objects.filter(owner=request.user)
        print(f"Found {hostels.count()} hostels for stats")
        
        total = hostels.count()
        approved = hostels.filter(is_approved=True).count()
        pending = hostels.filter(is_approved=False).count()
        featured = hostels.filter(is_featured=True).count()
        total_views = hostels.aggregate(total=Sum('views_count'))['total'] or 0
        
        from apps.reviews.models import Review
        avg_rating = Review.objects.filter(
            hostel__in=hostels,
            is_approved=True
        ).aggregate(avg=Avg('rating'))['avg'] or 0
        
        recent_views = hostels.filter(
            updated_at__gte=timezone.now() - timezone.timedelta(days=30)
        ).aggregate(total=Sum('views_count'))['total'] or 0
        
        print(f"Stats - Total: {total}, Approved: {approved}, Pending: {pending}, Featured: {featured}")
        
        return Response({
            'total': total,
            'approved': approved,
            'pending': pending,
            'featured': featured,
            'total_views': total_views,
            'recent_views': recent_views,
            'avg_rating': round(avg_rating, 1),
        })