from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from .models import SubscriptionPlan, OwnerSubscription, PaymentTransaction, SubscriptionLog
from .serializers import (
    SubscriptionPlanSerializer, OwnerSubscriptionSerializer, 
    CreateSubscriptionSerializer, MpesaSTKPushSerializer,
    AdminManualSubscriptionSerializer, PaymentTransactionSerializer
)
from .utils import get_owner_subscription_status, check_hostel_creation_eligibility
from .mpesa import initiate_mpesa_payment
from apps.accounts.models import User, AuditLog
from apps.accounts.views_admin import get_client_ip

import logging
logger = logging.getLogger(__name__)


class SubscriptionPlanListView(generics.ListAPIView):
    """List all available subscription plans"""
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated]


class CurrentSubscriptionView(APIView):
    """Get current user's subscription status"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        status_data = get_owner_subscription_status(request.user)
        return Response(status_data)


class CreateSubscriptionView(APIView):
    """Create a new subscription (initiate payment)"""
    permission_classes = [permissions.IsAuthenticated]
    
    @transaction.atomic
    def post(self, request):
        # Only owners can subscribe
        if request.user.role != 'owner':
            return Response(
                {'error': 'Only hostel owners can subscribe to plans'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = CreateSubscriptionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        plan_id = serializer.validated_data['plan_id']
        auto_renew = serializer.validated_data.get('auto_renew', False)
        payment_method = serializer.validated_data.get('payment_method', 'mpesa')
        phone_number = serializer.validated_data.get('phone_number', '')
        
        # Get the plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Invalid subscription plan'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user already has an active subscription
        existing_subscription = OwnerSubscription.objects.filter(
            owner=request.user, 
            is_active=True
        ).first()
        
        if existing_subscription and not existing_subscription.is_expired():
            # Handle upgrade
            if existing_subscription.plan.price_kes >= plan.price_kes:
                return Response({
                    'error': f'You already have an active {existing_subscription.plan.display_name} plan. '
                             f'You can only upgrade to higher tiers.'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new subscription (pending payment)
        new_subscription = OwnerSubscription.objects.create(
            owner=request.user,
            plan=plan,
            auto_renew=auto_renew,
            payment_status='pending',
            payment_method=payment_method,
            amount_paid=plan.price_kes,
            is_active=False,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=plan.duration_days)
        )
        
        # Log creation
        SubscriptionLog.objects.create(
            subscription=new_subscription,
            action='created',
            new_plan=plan.name,
            details={'price': str(plan.price_kes)},
            performed_by=request.user
        )
        
        # Initiate payment based on method
        if payment_method == 'mpesa':
            if not phone_number:
                return Response({
                    'error': 'Phone number is required for M-Pesa payment'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            payment_result = initiate_mpesa_payment(request.user, plan, phone_number)
            
            if payment_result['success']:
                # Create payment transaction
                from .models import PaymentTransaction
                PaymentTransaction.objects.create(
                    subscription=new_subscription,
                    amount=plan.price_kes,
                    payment_method='mpesa',
                    transaction_id=payment_result.get('checkout_request_id', ''),
                    phone_number=phone_number,
                    status='pending'
                )
                
                return Response({
                    'subscription_id': str(new_subscription.id),
                    'payment': payment_result,
                    'message': 'Payment initiated. Please check your phone for the STK push.'
                }, status=status.HTTP_200_OK)
            else:
                new_subscription.payment_status = 'failed'
                new_subscription.save()
                return Response({
                    'error': payment_result.get('message', 'Payment initiation failed')
                }, status=status.HTTP_400_BAD_REQUEST)
        
        # Manual/Bank payment (admin will verify)
        return Response({
            'subscription_id': str(new_subscription.id),
            'message': f'Subscription created. Please complete payment via {payment_method}.'
        }, status=status.HTTP_201_CREATED)


class CheckHostelEligibilityView(APIView):
    """Check if owner can add a new hostel"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        can, message = check_hostel_creation_eligibility(request.user)
        status_data = get_owner_subscription_status(request.user)
        
        return Response({
            'can_add_hostel': can,
            'message': message,
            'subscription_status': status_data
        })


class SubscriptionHistoryView(generics.ListAPIView):
    """Get user's subscription history"""
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return OwnerSubscription.objects.filter(owner=self.request.user).order_by('-created_at')


class PaymentHistoryView(generics.ListAPIView):
    """Get user's payment history"""
    serializer_class = PaymentTransactionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return PaymentTransaction.objects.filter(
            subscription__owner=self.request.user
        ).order_by('-created_at')


class CancelSubscriptionView(APIView):
    """Cancel current subscription (no refund)"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            subscription = OwnerSubscription.objects.filter(
                owner=request.user,
                is_active=True
            ).latest('created_at')
        except OwnerSubscription.DoesNotExist:
            return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)
        
        if subscription.plan.name == 'free':
            return Response({'error': 'Cannot cancel free plan'}, status=status.HTTP_400_BAD_REQUEST)
        
        subscription.is_active = False
        subscription.auto_renew = False
        subscription.save()
        
        # Log cancellation
        SubscriptionLog.objects.create(
            subscription=subscription,
            action='cancelled',
            details={'reason': 'User cancelled'},
            performed_by=request.user
        )
        
        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action='CANCEL_SUBSCRIPTION',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'subscription_id': str(subscription.id), 'plan': subscription.plan.display_name if subscription.plan else 'None'}
        )
        
        return Response({
            'status': 'success',
            'message': 'Your subscription has been cancelled. You will have access until the end of your billing period.'
        })


class ToggleAutoRenewView(APIView):
    """Toggle auto-renew for subscription"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            subscription = OwnerSubscription.objects.filter(
                owner=request.user,
                is_active=True
            ).latest('created_at')
        except OwnerSubscription.DoesNotExist:
            return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)
        
        subscription.auto_renew = not subscription.auto_renew
        subscription.save()
        
        return Response({
            'status': 'success',
            'auto_renew': subscription.auto_renew,
            'message': f'Auto-renew has been {"enabled" if subscription.auto_renew else "disabled"}'
        })


# ==================== ADMIN VIEWS ====================

class AdminSubscriptionListView(generics.ListAPIView):
    """List all subscriptions (admin only)"""
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        # Check if admin
        if self.request.user.role != 'admin' and not self.request.user.is_superuser:
            return OwnerSubscription.objects.none()
        
        queryset = OwnerSubscription.objects.all().order_by('-created_at')
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_filter == 'expired':
            queryset = queryset.filter(end_date__lt=timezone.now())
        elif status_filter == 'pending':
            queryset = queryset.filter(payment_status='pending')
        
        # Filter by plan
        plan_filter = self.request.query_params.get('plan')
        if plan_filter:
            queryset = queryset.filter(plan__name=plan_filter)
        
        # Search by email
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(owner__email__icontains=search)
        
        return queryset


class AdminManualActivateSubscriptionView(APIView):
    """Admin manually activates a subscription for a user"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        # Check if admin
        if request.user.role != 'admin' and not request.user.is_superuser:
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = AdminManualSubscriptionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        owner_email = serializer.validated_data['owner_email']
        plan_id = serializer.validated_data['plan_id']
        duration_days = serializer.validated_data.get('duration_days', 30)
        notes = serializer.validated_data.get('notes', '')
        
        # Get owner
        try:
            owner = User.objects.get(email=owner_email)
        except User.DoesNotExist:
            return Response({'error': 'Owner not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Deactivate existing subscriptions
        OwnerSubscription.objects.filter(owner=owner, is_active=True).update(is_active=False)
        
        # Create new subscription
        subscription = OwnerSubscription.objects.create(
            owner=owner,
            plan=plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timezone.timedelta(days=duration_days),
            is_active=True,
            payment_status='completed',
            payment_method='manual',
            payment_reference=f'MANUAL-{timezone.now().strftime("%Y%m%d%H%M%S")}',
            amount_paid=plan.price_kes,
            auto_renew=False,
            admin_notes=notes,
            manually_activated_by=request.user
        )
        
        # Log activation
        SubscriptionLog.objects.create(
            subscription=subscription,
            action='manual_activation',
            new_plan=plan.name,
            details={'notes': notes, 'duration_days': duration_days},
            performed_by=request.user
        )
        
        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action='MANUAL_SUBSCRIPTION_ACTIVATION',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={'owner': owner_email, 'plan': plan.display_name, 'duration': duration_days}
        )
        
        return Response({
            'status': 'success',
            'message': f'Subscription activated for {owner_email}',
            'subscription_id': str(subscription.id)
        })


class AdminSubscriptionStatsView(APIView):
    """Get subscription statistics for admin dashboard"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        if request.user.role != 'admin' and not request.user.is_superuser:
            return Response({'error': 'Admin access required'}, status=status.HTTP_403_FORBIDDEN)
        
        total_subscriptions = OwnerSubscription.objects.count()
        active_subscriptions = OwnerSubscription.objects.filter(is_active=True, end_date__gt=timezone.now()).count()
        expired_subscriptions = OwnerSubscription.objects.filter(end_date__lt=timezone.now()).count()
        pending_payments = OwnerSubscription.objects.filter(payment_status='pending').count()
        
        # Revenue stats
        total_revenue = OwnerSubscription.objects.filter(payment_status='completed').aggregate(
            total=models.Sum('amount_paid')
        )['total'] or 0
        
        monthly_revenue = OwnerSubscription.objects.filter(
            payment_status='completed',
            created_at__gte=timezone.now() - timezone.timedelta(days=30)
        ).aggregate(total=models.Sum('amount_paid'))['total'] or 0
        
        # Plan distribution
        from django.db.models import Count
        plan_distribution = OwnerSubscription.objects.filter(
            is_active=True
        ).values('plan__display_name').annotate(count=Count('id'))
        
        return Response({
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'pending_payments': pending_payments,
            'total_revenue': float(total_revenue),
            'monthly_revenue': float(monthly_revenue),
            'plan_distribution': list(plan_distribution)
        })