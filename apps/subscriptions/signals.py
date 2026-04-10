from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import logging

from .models import OwnerSubscription, SubscriptionLog, PaymentTransaction
from apps.accounts.models import User, AuditLog

logger = logging.getLogger(__name__)


@receiver(post_save, sender=OwnerSubscription)
def log_subscription_creation(sender, instance, created, **kwargs):
    """Log when a subscription is created or updated"""
    if created:
        SubscriptionLog.objects.create(
            subscription=instance,
            action='created',
            new_plan=instance.plan.name if instance.plan else 'free',
            details={
                'start_date': str(instance.start_date),
                'end_date': str(instance.end_date),
                'amount': str(instance.amount_paid) if instance.amount_paid else '0'
            }
        )
        
        # Send email notification for new subscription
        if instance.plan and instance.plan.price_kes > 0:
            send_subscription_email(instance, 'created')


@receiver(post_save, sender=PaymentTransaction)
def log_payment_transaction(sender, instance, created, **kwargs):
    """Log when a payment transaction is created or updated"""
    if created:
        logger.info(f"Payment transaction created: {instance.transaction_id} - {instance.amount}")
    
    if instance.status == 'completed' and instance.completed_at:
        logger.info(f"Payment completed: {instance.transaction_id}")


def send_subscription_email(subscription, action):
    """Send email notification for subscription events"""
    if not subscription.owner.email:
        return
    
    subject = ""
    message = ""
    
    if action == 'created':
        subject = f"Subscription Created - {subscription.plan.display_name}"
        message = f"""
        Hello {subscription.owner.full_name},
        
        Your {subscription.plan.display_name} subscription has been created.
        
        Details:
        - Plan: {subscription.plan.display_name}
        - Amount: KSh {subscription.amount_paid}
        - Start Date: {subscription.start_date.strftime('%Y-%m-%d')}
        - End Date: {subscription.end_date.strftime('%Y-%m-%d')}
        
        Thank you for choosing Kirinyaga Hostels!
        
        Regards,
        Kirinyaga Hostels Team
        """
    elif action == 'expiring':
        days_left = (subscription.end_date - timezone.now()).days
        subject = f"Subscription Expiring Soon - {days_left} days left"
        message = f"""
        Hello {subscription.owner.full_name},
        
        Your {subscription.plan.display_name} subscription will expire in {days_left} days.
        
        Please renew your subscription to continue enjoying all features.
        
        Renew now: https://kirinyaga-hostels-frontend.onrender.com/owner/subscription-plans.html
        
        Regards,
        Kirinyaga Hostels Team
        """
    elif action == 'expired':
        subject = "Subscription Expired"
        message = f"""
        Hello {subscription.owner.full_name},
        
        Your {subscription.plan.display_name} subscription has expired.
        
        Your hostels are now in read-only mode. Please renew to continue adding and editing hostels.
        
        Renew now: https://kirinyaga-hostels-frontend.onrender.com/owner/subscription-plans.html
        
        Regards,
        Kirinyaga Hostels Team
        """
    elif action == 'activated':
        subject = f"Subscription Activated - {subscription.plan.display_name}"
        message = f"""
        Hello {subscription.owner.full_name},
        
        Your {subscription.plan.display_name} subscription has been activated!
        
        You now have access to:
        - Up to {subscription.plan.max_hostels} hostels
        - {subscription.plan.max_images_per_hostel} images per hostel
        - {'Featured listings' if subscription.plan.can_feature_listings else 'Standard listings'}
        - {'Analytics access' if subscription.plan.analytics_access else 'Basic analytics'}
        
        Start managing your hostels now!
        
        Regards,
        Kirinyaga Hostels Team
        """
    
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[subscription.owner.email],
            fail_silently=True,
        )
        logger.info(f"Subscription email sent to {subscription.owner.email}")
    except Exception as e:
        logger.error(f"Failed to send subscription email: {e}")


def check_expiring_subscriptions():
    """Check for subscriptions expiring soon (to be called by management command)"""
    from datetime import timedelta
    
    # Subscriptions expiring in 7 days
    expiring_soon = OwnerSubscription.objects.filter(
        is_active=True,
        end_date__gte=timezone.now(),
        end_date__lte=timezone.now() + timedelta(days=7)
    )
    
    for sub in expiring_soon:
        send_subscription_email(sub, 'expiring')
        logger.info(f"Expiring notification sent to {sub.owner.email}")
    
    # Subscriptions that just expired
    just_expired = OwnerSubscription.objects.filter(
        is_active=True,
        end_date__lt=timezone.now(),
        end_date__gte=timezone.now() - timedelta(days=1)
    )
    
    for sub in just_expired:
        sub.is_active = False
        sub.save()
        send_subscription_email(sub, 'expired')
        
        # Create log
        SubscriptionLog.objects.create(
            subscription=sub,
            action='expired',
            details={'reason': 'Subscription period ended'}
        )
        
        logger.info(f"Subscription expired for {sub.owner.email}")
    
    return {
        'expiring_count': expiring_soon.count(),
        'expired_count': just_expired.count()
    }