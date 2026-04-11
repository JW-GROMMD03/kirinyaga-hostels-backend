from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Count
from django.conf import settings
from .models import SubscriptionPlan, OwnerSubscription, PaymentTransaction, SubscriptionLog
from .serializers import (
    SubscriptionPlanSerializer, OwnerSubscriptionSerializer, 
    CreateSubscriptionSerializer, MpesaSTKPushSerializer,
    AdminManualSubscriptionSerializer, PaymentTransactionSerializer
)
from .utils import get_owner_subscription_status, check_hostel_creation_eligibility, check_analytics_access
from .mpesa import initiate_mpesa_payment
from apps.accounts.models import User, AuditLog
from apps.accounts.views_admin import get_client_ip

import logging
logger = logging.getLogger(__name__)


# ============================================
# PUBLIC CALLBACK ENDPOINT (NO AUTH REQUIRED)
# ============================================

class MpesaCallbackView(APIView):
    """
    Handle M-Pesa STK Push callback from Safaricom.
    This endpoint is PUBLIC - no authentication required.
    """
    permission_classes = []
    authentication_classes = []
    
    def post(self, request):
        """
        Process the callback from Safaricom after payment is completed.
        """
        logger.info("=" * 50)
        logger.info("📱 M-PESA CALLBACK RECEIVED")
        logger.info(f"📱 Request Data: {request.data}")
        logger.info("=" * 50)
        
        try:
            # Extract callback data
            body = request.data.get('Body', {})
            stk_callback = body.get('stkCallback', {})
            
            merchant_request_id = stk_callback.get('MerchantRequestID')
            checkout_request_id = stk_callback.get('CheckoutRequestID')
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc', '')
            
            logger.info(f"📱 CheckoutRequestID: {checkout_request_id}")
            logger.info(f"📱 ResultCode: {result_code}")
            logger.info(f"📱 ResultDesc: {result_desc}")
            
            # Find the payment transaction
            try:
                transaction_obj = PaymentTransaction.objects.get(
                    transaction_id=checkout_request_id
                )
            except PaymentTransaction.DoesNotExist:
                logger.error(f"❌ Transaction not found for CheckoutRequestID: {checkout_request_id}")
                # Still return success to Safaricom (prevents retries)
                return Response({
                    "ResultCode": 0,
                    "ResultDesc": "Transaction not found, but acknowledged"
                })
            
            subscription = transaction_obj.subscription
            
            if result_code == 0:
                # ============================================
                # PAYMENT SUCCESSFUL
                # ============================================
                logger.info("✅ Payment SUCCESSFUL!")
                
                # Extract metadata
                callback_metadata = stk_callback.get('CallbackMetadata', {})
                items = callback_metadata.get('Item', [])
                
                mpesa_receipt = ''
                amount_paid = 0
                phone_number = ''
                transaction_date = ''
                
                for item in items:
                    name = item.get('Name', '')
                    value = item.get('Value', '')
                    
                    if name == 'MpesaReceiptNumber':
                        mpesa_receipt = value
                    elif name == 'Amount':
                        amount_paid = float(value) if value else 0
                    elif name == 'PhoneNumber':
                        phone_number = value
                    elif name == 'TransactionDate':
                        transaction_date = value
                
                logger.info(f"📱 M-Pesa Receipt: {mpesa_receipt}")
                logger.info(f"📱 Amount Paid: {amount_paid}")
                logger.info(f"📱 Phone: {phone_number}")
                
                # Update transaction
                transaction_obj.status = 'completed'
                transaction_obj.mpesa_receipt = mpesa_receipt
                transaction_obj.response_description = result_desc
                transaction_obj.completed_at = timezone.now()
                transaction_obj.save()
                
                # Activate subscription
                with transaction.atomic():
                    # Deactivate any existing active subscriptions for this owner
                    OwnerSubscription.objects.filter(
                        owner=subscription.owner,
                        is_active=True
                    ).update(is_active=False)
                    
                    # Activate this subscription
                    subscription.payment_status = 'completed'
                    subscription.payment_reference = mpesa_receipt
                    subscription.is_active = True
                    subscription.start_date = timezone.now()
                    subscription.end_date = timezone.now() + timezone.timedelta(
                        days=subscription.plan.duration_days
                    )
                    subscription.save()
                
                # Log activation
                SubscriptionLog.objects.create(
                    subscription=subscription,
                    action='activated',
                    details={
                        'mpesa_receipt': mpesa_receipt,
                        'amount': amount_paid,
                        'phone': phone_number
                    },
                    performed_by=subscription.owner
                )
                
                # Create audit log
                AuditLog.objects.create(
                    user=subscription.owner,
                    action='SUBSCRIPTION_PAYMENT_SUCCESS',
                    ip_address='0.0.0.0',
                    user_agent='Safaricom',
                    details={
                        'subscription_id': str(subscription.id),
                        'plan': subscription.plan.display_name,
                        'amount': amount_paid,
                        'mpesa_receipt': mpesa_receipt
                    }
                )
                
                logger.info(f"✅ Subscription {subscription.id} activated successfully!")
                
            else:
                # ============================================
                # PAYMENT FAILED OR CANCELLED
                # ============================================
                logger.warning(f"❌ Payment FAILED: {result_desc}")
                
                # Update transaction
                transaction_obj.status = 'failed'
                transaction_obj.response_description = result_desc
                transaction_obj.save()
                
                # Log failure
                SubscriptionLog.objects.create(
                    subscription=subscription,
                    action='payment_failed',
                    details={
                        'result_code': result_code,
                        'result_desc': result_desc
                    },
                    performed_by=subscription.owner
                )
                
                # Create audit log
                AuditLog.objects.create(
                    user=subscription.owner,
                    action='SUBSCRIPTION_PAYMENT_FAILED',
                    ip_address='M-PESA-CALLBACK',
                    user_agent='Safaricom',
                    details={
                        'subscription_id': str(subscription.id),
                        'plan': subscription.plan.display_name,
                        'reason': result_desc
                    }
                )
            
            # Always return success to Safaricom
            return Response({
                "ResultCode": 0,
                "ResultDesc": "Callback processed successfully"
            })
            
        except Exception as e:
            logger.error(f"❌ Error processing callback: {str(e)}", exc_info=True)
            # Still return success to prevent Safaricom retries
            return Response({
                "ResultCode": 0,
                "ResultDesc": "Error but acknowledged"
            })


# ============================================
# USER-FACING VIEWS
# ============================================

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


class CheckAnalyticsAccessView(APIView):
    """Check if owner has access to analytics"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        if request.user.role != 'owner':
            return Response({'error': 'Only owners can access analytics'}, status=status.HTTP_403_FORBIDDEN)
        
        can_access, message = check_analytics_access(request.user)
        status_data = get_owner_subscription_status(request.user)
        
        return Response({
            'can_access': can_access,
            'message': message,
            'subscription_status': status_data
        })


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
                # Delete the subscription since payment can't be initiated
                new_subscription.delete()
                return Response({
                    'error': 'Phone number is required for M-Pesa payment'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Format phone number
            formatted_phone = phone_number
            if formatted_phone.startswith('0'):
                formatted_phone = '254' + formatted_phone[1:]
            elif formatted_phone.startswith('+'):
                formatted_phone = formatted_phone[1:]
            
            # ============================================
            # SANDBOX OVERRIDE: Use test phone number
            # ============================================
            if settings.MPESA_ENVIRONMENT == 'sandbox':
                logger.info(f"📱 Sandbox mode: Using test phone 254708374149 instead of {formatted_phone}")
                formatted_phone = '254708374149'
            
            payment_result = initiate_mpesa_payment(request.user, plan, formatted_phone)
            
            if payment_result['success']:
                # ✅ FIXED: Removed merchant_request_id
                PaymentTransaction.objects.create(
                    subscription=new_subscription,
                    amount=plan.price_kes,
                    payment_method='mpesa',
                    transaction_id=payment_result.get('checkout_request_id', ''),
                    phone_number=formatted_phone,
                    status='pending'
                )
                
                return Response({
                    'subscription_id': str(new_subscription.id),
                    'payment': payment_result,
                    'message': 'Payment initiated. Please check your phone for the STK push.'
                }, status=status.HTTP_200_OK)
            else:
                # Delete the subscription since payment failed
                new_subscription.delete()
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
            total=Sum('amount_paid')
        )['total'] or 0
        
        monthly_revenue = OwnerSubscription.objects.filter(
            payment_status='completed',
            created_at__gte=timezone.now() - timezone.timedelta(days=30)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Plan distribution
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