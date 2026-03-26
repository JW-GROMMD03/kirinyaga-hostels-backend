from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.db import transaction
from datetime import datetime, timedelta
from .models import SubscriptionPlan, OwnerSubscription
from .serializers import (
    SubscriptionPlanSerializer,
    OwnerSubscriptionSerializer,
)
from apps.accounts.models import AuditLog

# Set up logging
import logging
logger = logging.getLogger(__name__)

# Custom permission for admin access
class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and (request.user.role == 'admin' or request.user.is_superuser)

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

# REMOVED: M-Pesa helper functions (get_access_token, stk_push)

# ==================== PUBLIC PLAN VIEW ====================
class SubscriptionPlanListView(generics.ListAPIView):
    """List all active subscription plans"""
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]

# ==================== OWNER SUBSCRIPTION SELF-VIEW ====================
class OwnerSubscriptionView(generics.RetrieveUpdateAPIView):
    """Get or create subscription for the current owner - always active for free tier"""
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        print(f"\n=== OwnerSubscriptionView.get_object() ===")
        print(f"User: {self.request.user.email}")
        
        try:
            subscription = OwnerSubscription.objects.get(owner=self.request.user)
            print(f"✅ Found existing subscription: {subscription.id}")
            
            # Ensure subscription is active for free tier
            if not subscription.is_active:
                subscription.is_active = True
                subscription.end_date = timezone.now() + timedelta(days=3650)  # 10 years
                subscription.save()
                print(f"✅ Activated subscription for free tier")
            
            print(f"   Plan: {subscription.plan}")
            print(f"   Active: {subscription.is_active}")
            print(f"   Start: {subscription.start_date}")
            print(f"   End: {subscription.end_date}")
            return subscription
            
        except OwnerSubscription.DoesNotExist:
            print(f"⚠️ No subscription found, creating new one with free access")
            
            # Get a default plan
            default_plan = SubscriptionPlan.objects.first()
            
            subscription = OwnerSubscription.objects.create(
                owner=self.request.user,
                plan=default_plan,
                start_date=timezone.now(),
                end_date=timezone.now() + timedelta(days=3650),  # 10 years
                is_active=True
            )
            print(f"✅ Created new subscription with free access: {subscription.id}")
            return subscription

    def retrieve(self, request, *args, **kwargs):
        print(f"\n=== OwnerSubscriptionView.retrieve() ===")
        print(f"User: {request.user.email}")
        
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            print(f"📤 Sending response: {serializer.data}")
            return Response(serializer.data)
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return Response(
                {"error": "Failed to retrieve subscription", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# ==================== OWNER SUBSCRIPTION HISTORY ====================
class OwnerSubscriptionHistoryView(generics.ListAPIView):
    """Get subscription history for the logged-in owner"""
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OwnerSubscription.objects.filter(
            owner=self.request.user
        ).order_by('-start_date')

# REMOVED: InitiatePaymentView, PaymentDetailView, UserPaymentListView, MpesaCallbackView

# ==================== ADMIN: SUBSCRIPTION PLAN MANAGEMENT ====================
class PlanListCreateView(generics.ListCreateAPIView):
    """List all subscription plans or create a new plan (admin only)"""
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminUser]

class PlanRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update or delete a plan (admin only)"""
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminUser]

class PlanDeleteView(generics.DestroyAPIView):
    """Explicit delete endpoint for a plan (admin only)"""
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAdminUser]

# ==================== ADMIN: OWNER SUBSCRIPTION MANAGEMENT ====================
class OwnerSubscriptionListView(generics.ListAPIView):
    """List all owner subscriptions (admin only)"""
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return OwnerSubscription.objects.select_related('owner', 'plan').all().order_by('-start_date')

class OwnerSubscriptionDetailView(generics.RetrieveAPIView):
    """Retrieve a specific owner subscription (admin only)"""
    queryset = OwnerSubscription.objects.all()
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [IsAdminUser]
    lookup_field = 'pk'

class ExtendSubscriptionView(APIView):
    """Extend an owner's subscription by a number of days (admin only)"""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            subscription = OwnerSubscription.objects.get(pk=pk)
            days = request.data.get('days', 30)
            
            if subscription.end_date:
                subscription.end_date += timezone.timedelta(days=days)
            else:
                subscription.end_date = timezone.now() + timezone.timedelta(days=days)
            
            subscription.is_active = True
            subscription.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='SUBSCRIPTION_EXTENDED',
                ip_address=get_client_ip(request),
                details={
                    'subscription_id': str(subscription.id),
                    'days': days,
                    'new_end_date': str(subscription.end_date)
                }
            )
            
            return Response({
                'status': 'extended',
                'new_end_date': subscription.end_date
            })
        except OwnerSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=404)

class TerminateSubscriptionView(APIView):
    """Terminate an owner's subscription (set inactive) (admin only)"""
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            subscription = OwnerSubscription.objects.get(pk=pk)
            subscription.is_active = False
            subscription.save()
            
            AuditLog.objects.create(
                user=request.user,
                action='SUBSCRIPTION_TERMINATED',
                ip_address=get_client_ip(request),
                details={'subscription_id': str(subscription.id)}
            )
            
            return Response({'status': 'terminated'})
        except OwnerSubscription.DoesNotExist:
            return Response({'error': 'Subscription not found'}, status=404)

class DeleteSubscriptionView(generics.DestroyAPIView):
    """Delete an owner subscription record (admin only)"""
    queryset = OwnerSubscription.objects.all()
    permission_classes = [IsAdminUser]
    
    def perform_destroy(self, instance):
        AuditLog.objects.create(
            user=self.request.user,
            action='SUBSCRIPTION_DELETED',
            ip_address=get_client_ip(self.request),
            details={'subscription_id': str(instance.id)}
        )
        instance.delete()

# REMOVED: PaymentListView, AdminPaymentDetailView

# ==================== PUBLIC PLAN VIEWS ====================
class PlanListView(generics.ListAPIView):
    """Public list of active subscription plans"""
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.AllowAny]

class AdminPlanListView(generics.ListAPIView):
    """Admin view – shows all plans (including inactive)"""
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAdminUser]


# ==================== DEBUG AND FIX ENDPOINTS ====================

class DebugDbDataView(APIView):
    """Debug endpoint to check database data"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        data = {
            'user': {
                'email': user.email,
                'id': str(user.id),
                'role': user.role
            },
            'subscriptions': []
        }
        
        try:
            subs = OwnerSubscription.objects.filter(owner=user).select_related('plan')
            for sub in subs:
                sub_data = {
                    'id': str(sub.id),
                    'is_active': sub.is_active,
                    'start_date': str(sub.start_date) if sub.start_date else None,
                    'end_date': str(sub.end_date) if sub.end_date else None,
                    'plan': None
                }
                if sub.plan:
                    sub_data['plan'] = {
                        'id': sub.plan.id,
                        'name': sub.plan.name,
                        'price': float(sub.plan.price),
                        'max_hostels': sub.plan.max_hostels
                    }
                data['subscriptions'].append(sub_data)
        except Exception as e:
            data['error'] = str(e)
        
        return Response(data)


class FixSubscriptionView(APIView):
    """Fix subscription for current user - ensures free access"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        from django.utils import timezone
        from datetime import timedelta
        from decimal import Decimal
        
        user = request.user
        result = {'action': None, 'message': ''}
        
        try:
            # Get or create subscription
            sub, created = OwnerSubscription.objects.get_or_create(
                owner=user,
                defaults={
                    'is_active': True,
                    'start_date': timezone.now(),
                    'end_date': timezone.now() + timedelta(days=3650)
                }
            )
            
            # Get a plan
            plan = SubscriptionPlan.objects.first()
            if not plan:
                # Create a default plan
                plan = SubscriptionPlan.objects.create(
                    name="Free Plan",
                    price=Decimal('0.00'),
                    duration_days=3650,
                    max_hostels=999999,
                    max_images_per_hostel=999999,
                    is_featured_listing=True,
                    priority_support=True,
                    is_active=True
                )
                result['message'] += "Created default free plan. "
            
            # Update subscription to ensure free access
            sub.plan = plan
            sub.start_date = timezone.now()
            sub.end_date = timezone.now() + timedelta(days=3650)  # 10 years
            sub.is_active = True
            sub.save()
            
            result['action'] = 'updated' if not created else 'created'
            result['message'] += f"Subscription {result['action']} with free access"
            result['subscription'] = {
                'id': str(sub.id),
                'plan': plan.name,
                'is_active': sub.is_active,
                'end_date': str(sub.end_date)
            }
            
        except Exception as e:
            result['error'] = str(e)
        
        return Response(result)


class TestAllEndpointsView(APIView):
    """Test all subscription-related endpoints"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        results = {}
        
        # Test 1: Get current subscription
        try:
            sub = OwnerSubscription.objects.get(owner=request.user)
            results['subscription_exists'] = True
            results['subscription'] = {
                'id': str(sub.id),
                'has_plan': sub.plan is not None,
                'is_active': sub.is_active,
                'end_date': str(sub.end_date) if sub.end_date else None
            }
        except OwnerSubscription.DoesNotExist:
            results['subscription_exists'] = False
        
        # Test 2: Check plans
        plans = SubscriptionPlan.objects.all()
        results['plans_count'] = plans.count()
        results['plans'] = [{'id': p.id, 'name': p.name} for p in plans]
        
        return Response(results)