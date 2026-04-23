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
from apps.subscriptions.utils import check_hostel_creation_eligibility, get_owner_subscription_status
from apps.accounts.models import AuditLog

logger = logging.getLogger(__name__)

def get_client_ip(request):
    """
    Figure out the actual IP address of whoever's making the request.
    Handles proxies and load balancers by checking the forwarded headers first.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip or '0.0.0.0'


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination settings used across most list views.
    Defaults to 12 items per page but lets the frontend request more or less.
    """
    page_size = 12
    page_size_query_param = 'page_size'
    max_page_size = 100


class HostelSearchView(generics.ListAPIView):
    """
    The main search endpoint that students use to find hostels.
    Anyone can access this - no login required.
    Supports filtering by price, distance, room type, and amenities.
    """
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
        """
        Build the base queryset - only show approved and available hostels to the public.
        Then apply any filters the user requested.
        """
        queryset = Hostel.objects.filter(
            is_approved=True, 
            available=True
        ).select_related('owner').prefetch_related('images', 'amenities__amenity')
        
        # Handle amenity filtering - if they pass a comma-separated list of amenity IDs,
        # we need to find hostels that have ANY of those (OR condition, not AND)
        amenities_param = self.request.query_params.get('amenities')
        if amenities_param:
            amenity_ids = amenities_param.split(',')
            q_filter = Q()
            for aid in amenity_ids:
                q_filter |= Q(amenities__amenity_id=aid)
            queryset = queryset.filter(q_filter).distinct()
        
        # Location-based search - find hostels within a certain radius
        lat = self.request.query_params.get('lat')
        lng = self.request.query_params.get('lng')
        radius = self.request.query_params.get('radius')
        
        if lat and lng and radius:
            # Rough conversion: 1 degree of latitude is about 111 km
            queryset = queryset.filter(
                location_lat__range=(float(lat) - float(radius)/111, float(lat) + float(radius)/111),
                location_lng__range=(float(lng) - float(radius)/111, float(lng) + float(radius)/111)
            )
        
        return queryset.distinct()

    def get_serializer_context(self):
        """Pass the request object to the serializer so it can build proper URLs."""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class HostelDetailView(generics.RetrieveAPIView):
    """
    Shows all the details for a single hostel.
    Special case: owners can see their own hostels even if they're not approved yet.
    Everyone else only sees approved and available hostels.
    """
    serializer_class = HostelDetailSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        user = self.request.user
        
        # Owners get to see their own stuff, approved or not
        if user.is_authenticated and user.role == 'owner':
            return Hostel.objects.filter(Q(is_approved=True, available=True) | Q(owner=user))
        
        # Everyone else only sees what's live and available
        return Hostel.objects.filter(is_approved=True, available=True)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def retrieve(self, request, *args, **kwargs):
        """
        Override the default retrieve so we can increment the view counter
        and log that someone looked at this hostel.
        """
        instance = self.get_object()
        instance.increment_views()
        
        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action='VIEW_HOSTEL',
            action_category='view',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
            details={'hostel_id': str(instance.id), 'name': instance.name}
        )
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class OwnerHostelListView(generics.ListAPIView):
    """
    Shows an owner all the hostels they've listed.
    Simple and straightforward - just their own properties.
    """
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
        
        if count == 0:
            total_hostels = Hostel.objects.count()
            print(f"Total hostels in database: {total_hostels}")
        
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
    """
    Owners need to see their own hostel details for editing.
    This endpoint makes sure they can only see their own properties.
    """
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
    """
    The endpoint owners hit when they want to list a new hostel.
    This is where all the subscription checks happen to make sure
    they're allowed to add another property.
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        print("\n=== HostelCreateView ===")
        print(f"User: {request.user.email} (ID: {request.user.id})")
        print(f"User role: {request.user.role}")
        
        # First things first - only owners can list hostels
        if request.user.role != 'owner':
            raise PermissionDenied("Only owners can create hostels.")
        
        # ========== CHECK IF OWNER CAN ADD A HOSTEL ==========
        # This function handles both free tier (1 per month) and paid plans
        can_add, message = check_hostel_creation_eligibility(request.user)
        
        if not can_add:
            # Get their full subscription status so we can give them a helpful error
            status_data = get_owner_subscription_status(request.user)
            
            error_message = message
            if not status_data.get('has_active_subscription'):
                error_message = f"{message} You're on the free plan which gives you one listing per month. Need more? Check out our paid plans. <a href='/owner/subscription-plans.html'>View Plans</a>"
            elif status_data.get('plan') == 'free' and status_data.get('current_hostels', 0) >= 1:
                error_message = f"{message} You've already used your free listing for this month. Upgrade to add more whenever you want."
            elif status_data.get('max_hostels') and status_data.get('current_hostels', 0) >= status_data.get('max_hostels'):
                error_message = f"{message} Your {status_data.get('plan_display')} plan maxes out at {status_data.get('max_hostels')} hostels. You'll need to upgrade to add more."
            
            return Response(
                {'error': error_message, 'requires_subscription': True, 'subscription_status': status_data},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # ========== PAID PLAN LIMIT CHECK ==========
        # Only do this extra check if they actually have a paid subscription.
        # Free tier users don't have a subscription record at all, and that's fine.
        subscription = OwnerSubscription.objects.filter(
            owner=request.user,
            is_active=True,
            end_date__gte=timezone.now()
        ).first()
        
        # If they're on a paid plan, make sure they haven't hit their cap
        if subscription and subscription.plan and subscription.plan.name != 'free':
            current_count = Hostel.objects.filter(owner=request.user).count()
            if subscription.plan.max_hostels > 0 and current_count >= subscription.plan.max_hostels:
                return Response(
                    {'error': f"You've hit the limit for your {subscription.plan.display_name} plan ({subscription.plan.max_hostels} hostels). Time to upgrade?"},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # If we made it this far, they're cleared to add their hostel!

        # Gather up all the basic information about the hostel
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
            # Handle the photos they uploaded (up to 6)
            image_fields = ['photo1', 'photo2', 'photo3', 'photo4', 'photo5', 'photo6']
            for i, field in enumerate(image_fields):
                if field in request.FILES:
                    image_file = request.FILES[field]
                    description = request.data.get(f'{field}_desc', '')

                    HostelImage.objects.create(
                        hostel=hostel,
                        image=image_file,
                        description=description,
                        is_primary=(i == 0)  # First photo becomes the main one
                    )
                    print(f"Image uploaded: {field}")

            # Save which amenities they selected
            amenities = request.data.getlist('amenities[]')
            if amenities:
                for amenity_id in amenities:
                    HostelAmenity.objects.create(
                        hostel=hostel,
                        amenity_id=amenity_id
                    )
                print(f"Added {len(amenities)} amenities")

            # Keep a record of this creation in the audit log
            AuditLog.objects.create(
                user=request.user,
                action='CREATE_HOSTEL',
                action_category='hostel',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                details={'hostel_id': str(hostel.id), 'name': hostel.name}
            )

            serializer = HostelDetailSerializer(hostel, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"Error during image upload or amenity creation: {e}")
            traceback.print_exc()
            raise


class HostelUpdateView(APIView):
    """
    Let owners edit their existing hostels.
    Any update resets the approval status so admins can review the changes.
    """
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def put(self, request, pk):
        print(f"\n=== HostelUpdateView for ID: {pk} ===")
        print(f"User: {request.user.email}")
        
        try:
            hostel = Hostel.objects.get(pk=pk)
            print(f"Found hostel: {hostel.name}, Owner ID: {hostel.owner_id}")
            
            # Security check - you can only edit your own hostels
            if hostel.owner != request.user:
                print(f"Ownership check failed. Hostel owner: {hostel.owner_id}, Request user: {request.user.id}")
                raise PermissionDenied("You can only edit your own hostels.")
            
            # Check if they're trying to feature this listing (paid feature)
            subscription = OwnerSubscription.objects.filter(
                owner=request.user,
                is_active=True,
                end_date__gte=timezone.now()
            ).first()
            
            if request.data.get('is_featured') and not subscription:
                return Response(
                    {'error': 'You need an active subscription to feature listings. Please subscribe.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            if request.data.get('is_featured') and subscription and subscription.plan:
                if not subscription.plan.can_feature_listings:
                    return Response(
                        {'error': f'Your {subscription.plan.display_name} plan does not include featured listings. Upgrade to Premium or Enterprise.'},
                        status=status.HTTP_403_FORBIDDEN
                    )
            
            # Update all the basic fields that changed
            for field in ['name', 'description', 'room_type', 'capacity', 'price', 
                         'deposit', 'utilities', 'address', 'location_lat', 'location_lng',
                         'distance_to_university', 'other_amenities', 'is_featured']:
                if field in request.data:
                    setattr(hostel, field, request.data[field])
            
            # Any update means the hostel needs to be reviewed again by admins
            hostel.is_approved = False
            hostel.save()
            print(f"Hostel updated successfully. Approval reset to False")
            
            # Check if they uploaded any new photos
            image_fields = ['photo1', 'photo2', 'photo3', 'photo4', 'photo5', 'photo6']
            new_images = False
            for field in image_fields:
                if field in request.FILES:
                    new_images = True
                    break
            
            # If they uploaded new photos, replace all the old ones
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
            
            # Update the amenities list
            if 'amenities[]' in request.data:
                amenities = request.data.getlist('amenities[]')
                hostel.amenities.all().delete()
                for amenity_id in amenities:
                    HostelAmenity.objects.create(
                        hostel=hostel,
                        amenity_id=amenity_id
                    )
                print(f"Updated {len(amenities)} amenities")
            
            # Log this update
            AuditLog.objects.create(
                user=request.user,
                action='UPDATE_HOSTEL',
                action_category='hostel',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
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
    """
    Permanently remove a hostel listing.
    Owners can only delete their own properties.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        print(f"\n=== HostelDeleteView for ID: {pk} ===")
        print(f"User: {request.user.email}")
        
        try:
            hostel = Hostel.objects.get(pk=pk)
            print(f"Found hostel: {hostel.name}, Owner ID: {hostel.owner_id}")
            
            # Security - only the owner can delete their own hostel
            if hostel.owner != request.user:
                print(f"Ownership check failed. Hostel owner: {hostel.owner_id}, Request user: {request.user.id}")
                raise PermissionDenied("You can only delete your own hostels.")
            
            # Log before we delete so we have a record
            AuditLog.objects.create(
                user=request.user,
                action='DELETE_HOSTEL',
                action_category='hostel',
                ip_address=get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
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
    """
    Students can save hostels to their favorites list.
    This endpoint shows their saved hostels and lets them add new ones.
    """
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
    """
    Remove a hostel from the student's saved list.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return SavedHostel.objects.filter(user=self.request.user)


class RecommendedHostelsView(generics.ListAPIView):
    """
    Smart recommendations for students based on their profile preferences.
    Uses their budget range if they've set one up.
    """
    serializer_class = HostelListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        base_qs = Hostel.objects.filter(
            is_approved=True, 
            available=True
        ).select_related('owner').prefetch_related('images', 'amenities__amenity')
        
        # If the student has set a budget, use it to filter recommendations
        if hasattr(user, 'student_profile') and user.student_profile:
            profile = user.student_profile
            if profile.budget_min and profile.budget_max:
                base_qs = base_qs.filter(
                    price__gte=profile.budget_min,
                    price__lte=profile.budget_max
                )
        
        # Featured hostels first, then newest
        return base_qs.order_by('-is_featured', '-created_at')[:20]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context


class AmenityListView(generics.ListAPIView):
    """
    Simple list of all available amenities that owners can select from.
    Used to populate the checkboxes on the add hostel form.
    """
    queryset = Amenity.objects.all().order_by('name')
    serializer_class = AmenitySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class HostelReviewListCreateView(generics.ListCreateAPIView):
    """
    Students can leave reviews on hostels they've experienced.
    Only approved reviews are shown to the public.
    """
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
            
            # One review per student per hostel
            if HostelReview.objects.filter(hostel=hostel, user=self.request.user).exists():
                raise PermissionDenied("You have already reviewed this hostel.")
            
            serializer.save(hostel=hostel)
            
        except Hostel.DoesNotExist:
            raise NotFound("Hostel not found")


class AvailabilityView(generics.ListCreateAPIView):
    """
    Owners can mark specific dates when their hostel is available or booked.
    Helps students see real-time availability.
    """
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
    """
    Dashboard stats for owners - shows them how their hostels are performing.
    Includes view counts, ratings, and their current subscription status.
    """
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
        
        # Include subscription info so the frontend knows their limits
        subscription_status = get_owner_subscription_status(request.user)
        
        print(f"Stats - Total: {total}, Approved: {approved}, Pending: {pending}, Featured: {featured}")
        
        return Response({
            'total': total,
            'approved': approved,
            'pending': pending,
            'featured': featured,
            'total_views': total_views,
            'recent_views': recent_views,
            'avg_rating': round(avg_rating, 1),
            'subscription': subscription_status
        })


class CheckHostelLimitView(APIView):
    """
    Quick check endpoint for the frontend to see if an owner can add another hostel.
    Returns all the relevant limit information in one clean response.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can access this endpoint'}, status=403)
        
        can_add, message = check_hostel_creation_eligibility(request.user)
        subscription_status = get_owner_subscription_status(request.user)
        
        return Response({
            'can_add_hostel': can_add,
            'message': message,
            'current_hostels': subscription_status.get('current_hostels', 0),
            'max_hostels': subscription_status.get('max_hostels', 1),
            'plan': subscription_status.get('plan', 'free'),
            'plan_display': subscription_status.get('plan_display', 'Free'),
            'has_active_subscription': subscription_status.get('has_active_subscription', False),
            'requires_upgrade': subscription_status.get('plan') == 'free' and subscription_status.get('current_hostels', 0) >= 1
        })