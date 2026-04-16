"""
Admin Subscription Management Views
"""
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.db import transaction
from datetime import timedelta
from .models import SubscriptionPlan, OwnerSubscription, PaymentTransaction, SubscriptionLog
from .serializers import OwnerSubscriptionSerializer, SubscriptionPlanSerializer
from apps.accounts.models import User, AuditLog
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and (request.user.role == 'admin' or request.user.is_superuser)


# ============================================
# ADMIN SUBSCRIPTION MANAGEMENT
# ============================================

class AdminAllSubscriptionsView(generics.ListAPIView):
    """Admin view: Get all subscriptions with filtering"""
    serializer_class = OwnerSubscriptionSerializer
    permission_classes = [IsAdminUser]
    
    def get_queryset(self):
        queryset = OwnerSubscription.objects.select_related('owner', 'plan').all()
        
        # Filter by status
        status_filter = self.request.query_params.get('status', '')
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True, end_date__gt=timezone.now())
        elif status_filter == 'expired':
            queryset = queryset.filter(end_date__lt=timezone.now())
        elif status_filter == 'pending':
            queryset = queryset.filter(payment_status='pending')
        elif status_filter == 'cancelled':
            queryset = queryset.filter(is_active=False)
        elif status_filter == 'bonus':
            queryset = queryset.filter(is_bonus=True)
        
        # Search by owner email or name
        search = self.request.query_params.get('search', '')
        if search:
            queryset = queryset.filter(
                Q(owner__email__icontains=search) |
                Q(owner__full_name__icontains=search)
            )
        
        # Filter by plan
        plan_filter = self.request.query_params.get('plan', '')
        if plan_filter:
            queryset = queryset.filter(plan__name=plan_filter)
        
        return queryset.order_by('-created_at')


class AdminAllOwnersStatusView(APIView):
    """Admin view: Get all owners with their current subscription status"""
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        # Get all owners
        owners = User.objects.filter(role='owner')
        
        # Search
        search = request.query_params.get('search', '')
        if search:
            owners = owners.filter(
                Q(email__icontains=search) |
                Q(full_name__icontains=search)
            )
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        start = (page - 1) * page_size
        end = start + page_size
        
        total = owners.count()
        owners_page = owners[start:end]
        
        result = []
        for owner in owners_page:
            active_sub = OwnerSubscription.objects.filter(
                owner=owner, 
                is_active=True, 
                end_date__gt=timezone.now()
            ).select_related('plan').first()
            
            # Get total hostels count
            hostel_count = owner.hostels.count() if hasattr(owner, 'hostels') else 0
            
            # Get total revenue from this owner
            total_revenue = PaymentTransaction.objects.filter(
                subscription__owner=owner, 
                status='completed'
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            # ✅ Extract bonus reason
            bonus_reason = None
            if active_sub and active_sub.is_bonus and active_sub.admin_notes:
                if ' - ' in active_sub.admin_notes:
                    bonus_reason = active_sub.admin_notes.split(' - ', 1)[1]
                else:
                    bonus_reason = active_sub.admin_notes
            
            result.append({
                'id': str(owner.id),
                'email': owner.email,
                'full_name': owner.full_name,
                'is_active': owner.is_active,
                'email_verified': owner.email_verified,
                'current_plan': active_sub.plan.display_name if active_sub and active_sub.plan else 'Free',
                'current_plan_id': str(active_sub.plan.id) if active_sub and active_sub.plan else None,
                'subscription_status': 'active' if active_sub else 'inactive',
                'is_bonus': active_sub.is_bonus if active_sub else False,
                'bonus_weeks': active_sub.bonus_weeks if active_sub else None,
                'bonus_reason': bonus_reason,
                'days_remaining': active_sub.days_remaining() if active_sub else 0,
                'end_date': active_sub.end_date if active_sub else None,
                'total_hostels': hostel_count,
                'total_revenue': float(total_revenue),
                'auto_renew': active_sub.auto_renew if active_sub else False,
            })
        
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'results': result
        })


class AdminGrantBonusSubscriptionView(APIView):
    """Admin grants a free bonus subscription (in weeks) to an owner"""
    permission_classes = [IsAdminUser]
    
    @transaction.atomic
    def post(self, request):
        owner_email = request.data.get('owner_email')
        owner_id = request.data.get('owner_id')
        plan_id = request.data.get('plan_id')
        bonus_weeks = int(request.data.get('bonus_weeks', 4))
        reason = request.data.get('reason', 'Bonus subscription granted by admin')
        
        # Get owner by email or ID
        owner = None
        if owner_id:
            try:
                owner = User.objects.get(id=owner_id, role='owner')
            except User.DoesNotExist:
                pass
        if not owner and owner_email:
            try:
                owner = User.objects.get(email=owner_email, role='owner')
            except User.DoesNotExist:
                pass
        
        if not owner:
            return Response({'error': 'Owner not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate duration in days
        duration_days = bonus_weeks * 7
        
        # Deactivate any existing active subscriptions
        OwnerSubscription.objects.filter(owner=owner, is_active=True).update(
            is_active=False,
            auto_renew=False
        )
        
        # ✅ Create admin_notes with reason clearly separated
        admin_notes = f'Bonus: {bonus_weeks} weeks - {reason}'
        
        # Create bonus subscription
        subscription = OwnerSubscription.objects.create(
            owner=owner,
            plan=plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=duration_days),
            is_active=True,
            payment_status='completed',
            payment_method='bonus',
            payment_reference=f'BONUS-{timezone.now().strftime("%Y%m%d%H%M%S")}',
            amount_paid=0,
            auto_renew=False,
            admin_notes=admin_notes,
            manually_activated_by=request.user,
            is_bonus=True,
            bonus_weeks=bonus_weeks
        )
        
        # Log it
        SubscriptionLog.objects.create(
            subscription=subscription,
            action='manual_activation',
            new_plan=plan.name,
            details={
                'bonus_weeks': bonus_weeks,
                'reason': reason,
                'granted_by': request.user.email
            },
            performed_by=request.user
        )
        
        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action='GRANT_BONUS_SUBSCRIPTION',
            action_category='admin',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={
                'owner': owner.email,
                'plan': plan.display_name,
                'bonus_weeks': bonus_weeks,
                'reason': reason
            }
        )
        
        # ✅ Return the created subscription with full details
        serializer = OwnerSubscriptionSerializer(subscription)
        return Response({
            'status': 'success',
            'message': f'Bonus subscription granted to {owner.email} for {bonus_weeks} weeks',
            'subscription': serializer.data,
            'subscription_id': str(subscription.id),
            'expires_on': subscription.end_date.strftime('%Y-%m-%d %H:%M:%S')
        })


class AdminRevokeSubscriptionView(APIView):
    """Admin revokes an owner's active subscription"""
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        owner_email = request.data.get('owner_email')
        owner_id = request.data.get('owner_id')
        subscription_id = request.data.get('subscription_id')
        reason = request.data.get('reason', 'Revoked by admin')
        
        subscription = None
        
        if subscription_id:
            try:
                subscription = OwnerSubscription.objects.get(id=subscription_id)
            except OwnerSubscription.DoesNotExist:
                pass
        
        if not subscription:
            owner = None
            if owner_id:
                try:
                    owner = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    pass
            if not owner and owner_email:
                try:
                    owner = User.objects.get(email=owner_email)
                except User.DoesNotExist:
                    pass
            
            if owner:
                subscription = OwnerSubscription.objects.filter(
                    owner=owner, 
                    is_active=True
                ).first()
        
        if not subscription:
            return Response({'error': 'No active subscription found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Revoke it
        subscription.is_active = False
        subscription.auto_renew = False
        subscription.admin_notes = f'Revoked: {reason}'
        subscription.revoked_by = request.user
        subscription.revoked_at = timezone.now()
        subscription.save()
        
        # Log it
        SubscriptionLog.objects.create(
            subscription=subscription,
            action='cancelled',
            details={'reason': reason, 'revoked_by': request.user.email},
            performed_by=request.user
        )
        
        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action='REVOKE_SUBSCRIPTION',
            action_category='admin',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={
                'owner': subscription.owner.email,
                'plan': subscription.plan.display_name if subscription.plan else 'None',
                'reason': reason
            }
        )
        
        return Response({
            'status': 'success',
            'message': f'Subscription revoked for {subscription.owner.email}'
        })


class AdminExtendSubscriptionView(APIView):
    """Admin extends an owner's subscription by days or weeks"""
    permission_classes = [IsAdminUser]
    
    def post(self, request):
        owner_email = request.data.get('owner_email')
        owner_id = request.data.get('owner_id')
        subscription_id = request.data.get('subscription_id')
        days = int(request.data.get('days', 0))
        weeks = int(request.data.get('weeks', 0))
        reason = request.data.get('reason', 'Extended by admin')
        
        total_days = days + (weeks * 7)
        if total_days <= 0:
            return Response({'error': 'Days or weeks must be greater than 0'}, status=400)
        
        subscription = None
        if subscription_id:
            try:
                subscription = OwnerSubscription.objects.get(id=subscription_id)
            except OwnerSubscription.DoesNotExist:
                pass
        
        if not subscription:
            owner = None
            if owner_id:
                try:
                    owner = User.objects.get(id=owner_id)
                except User.DoesNotExist:
                    pass
            if not owner and owner_email:
                try:
                    owner = User.objects.get(email=owner_email)
                except User.DoesNotExist:
                    pass
            
            if owner:
                subscription = OwnerSubscription.objects.filter(
                    owner=owner, 
                    is_active=True
                ).first()
        
        if not subscription:
            return Response({'error': 'No active subscription found'}, status=404)
        
        # Extend the subscription
        if subscription.end_date > timezone.now():
            subscription.end_date += timedelta(days=total_days)
        else:
            subscription.start_date = timezone.now()
            subscription.end_date = timezone.now() + timedelta(days=total_days)
            subscription.is_active = True
        
        subscription.admin_notes = f'{subscription.admin_notes or ""} Extended by {total_days} days: {reason}'
        subscription.save()
        
        # Log it
        SubscriptionLog.objects.create(
            subscription=subscription,
            action='renewed',
            details={'days': total_days, 'weeks': weeks, 'reason': reason},
            performed_by=request.user
        )
        
        # Audit log
        AuditLog.objects.create(
            user=request.user,
            action='EXTEND_SUBSCRIPTION',
            action_category='admin',
            ip_address=get_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            details={
                'owner': subscription.owner.email,
                'days': total_days,
                'weeks': weeks,
                'reason': reason
            }
        )
        
        return Response({
            'status': 'success',
            'message': f'Subscription extended by {total_days} days',
            'new_end_date': subscription.end_date.strftime('%Y-%m-%d %H:%M:%S')
        })


class AdminSubscriptionStatsView(APIView):
    """Get subscription statistics for admin dashboard"""
    permission_classes = [IsAdminUser]
    
    def get(self, request):
        total_subscriptions = OwnerSubscription.objects.count()
        active_subscriptions = OwnerSubscription.objects.filter(is_active=True, end_date__gt=timezone.now()).count()
        expired_subscriptions = OwnerSubscription.objects.filter(end_date__lt=timezone.now()).count()
        pending_payments = OwnerSubscription.objects.filter(payment_status='pending').count()
        bonus_subscriptions = OwnerSubscription.objects.filter(is_bonus=True).count()
        
        # Revenue stats
        total_revenue = OwnerSubscription.objects.filter(payment_status='completed').aggregate(
            total=Sum('amount_paid')
        )['total'] or 0
        
        monthly_revenue = OwnerSubscription.objects.filter(
            payment_status='completed',
            created_at__gte=timezone.now() - timedelta(days=30)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Plan distribution
        plan_distribution = OwnerSubscription.objects.filter(
            is_active=True
        ).values('plan__display_name').annotate(count=Count('id'))
        
        # Owners without subscription
        owners_without_sub = User.objects.filter(role='owner').exclude(
            subscriptions__is_active=True, 
            subscriptions__end_date__gt=timezone.now()
        ).count()
        
        return Response({
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'pending_payments': pending_payments,
            'bonus_subscriptions': bonus_subscriptions,
            'owners_without_subscription': owners_without_sub,
            'total_revenue': float(total_revenue),
            'monthly_revenue': float(monthly_revenue),
            'plan_distribution': list(plan_distribution)
        })