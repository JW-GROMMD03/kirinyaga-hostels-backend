from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
import json
from .models import AuditLog
from apps.hostels.models import Hostel, HostelImage
from apps.bookings.models import Booking
from apps.reviews.models import Review
from apps.subscriptions.models import OwnerSubscription


def get_default_ip():
    """Return default IP address for signal logs"""
    return '0.0.0.0'


@receiver(post_save, sender=Hostel)
def log_hostel_save(sender, instance, created, **kwargs):
    """Log when a hostel is created or updated"""
    action = 'CREATE_HOSTEL' if created else 'UPDATE_HOSTEL'
    
    # Get changes if updating
    changes = {}
    if not created and hasattr(instance, '_old_values'):
        for field, old_value in instance._old_values.items():
            new_value = getattr(instance, field)
            if old_value != new_value:
                changes[field] = {'old': str(old_value), 'new': str(new_value)}
    
    details = {
        'hostel_name': instance.name,
        'owner_email': instance.owner.email if instance.owner else None,
        'address': instance.address,
        'price': float(instance.price) if instance.price else None,
        'room_type': instance.room_type,
        'changes': changes if changes else None,
    }
    
    AuditLog.objects.create(
        user=instance.owner if instance.owner else None,
        action=action,
        action_category='hostel',
        resource_type='Hostel',
        resource_id=str(instance.id),
        ip_address=get_default_ip(),  # FIXED: Added default IP
        user_agent='System Signal',   # FIXED: Added default user agent
        details=details,
    )


@receiver(pre_save, sender=Hostel)
def store_hostel_old_values(sender, instance, **kwargs):
    """Store old values before update"""
    if instance.pk:
        try:
            old_instance = Hostel.objects.get(pk=instance.pk)
            instance._old_values = {
                'name': old_instance.name,
                'price': old_instance.price,
                'address': old_instance.address,
                'description': old_instance.description,
                'is_approved': old_instance.is_approved,
                'available': old_instance.available,
            }
        except Hostel.DoesNotExist:
            instance._old_values = {}
    else:
        instance._old_values = {}


@receiver(post_delete, sender=Hostel)
def log_hostel_delete(sender, instance, **kwargs):
    """Log when a hostel is deleted"""
    AuditLog.objects.create(
        user=instance.owner if instance.owner else None,
        action='DELETE_HOSTEL',
        action_category='hostel',
        resource_type='Hostel',
        resource_id=str(instance.id),
        ip_address=get_default_ip(),  # FIXED: Added default IP
        user_agent='System Signal',   # FIXED: Added default user agent
        details={
            'hostel_name': instance.name,
            'owner_email': instance.owner.email if instance.owner else None,
            'price': float(instance.price) if instance.price else None,
        }
    )


@receiver(post_save, sender=Booking)
def log_booking_save(sender, instance, created, **kwargs):
    """Log when a booking is created or updated"""
    action = 'CREATE_BOOKING' if created else 'UPDATE_BOOKING'
    details = {
        'hostel_name': instance.hostel.name if instance.hostel else None,
        'student_email': instance.student.email if instance.student else None,
        'check_in': str(instance.check_in),
        'check_out': str(instance.check_out),
        'status': instance.status,
        'total_price': float(instance.total_price) if hasattr(instance, 'total_price') else None,
    }
    
    AuditLog.objects.create(
        user=instance.student if instance.student else None,
        action=action,
        action_category='booking',
        resource_type='Booking',
        resource_id=str(instance.id),
        ip_address=get_default_ip(),  # FIXED: Added default IP
        user_agent='System Signal',   # FIXED: Added default user agent
        details=details,
    )


@receiver(post_save, sender=Review)
def log_review_save(sender, instance, created, **kwargs):
    """Log when a review is created"""
    if created:
        AuditLog.objects.create(
            user=instance.user if instance.user else None,
            action='CREATE_REVIEW',
            action_category='review',
            resource_type='Review',
            resource_id=str(instance.id),
            ip_address=get_default_ip(),  # FIXED: Added default IP
            user_agent='System Signal',   # FIXED: Added default user agent
            details={
                'hostel_name': instance.hostel.name if instance.hostel else None,
                'rating': instance.rating,
                'comment_preview': instance.comment[:100] if instance.comment else '',
            }
        )


@receiver(post_save, sender=OwnerSubscription)
def log_subscription_save(sender, instance, created, **kwargs):
    """Log when a subscription is created or updated"""
    action = 'CREATE_SUBSCRIPTION' if created else 'UPDATE_SUBSCRIPTION'
    details = {
        'owner_email': instance.owner.email if instance.owner else None,
        'plan_name': instance.plan.name if instance.plan else None,
        'start_date': str(instance.start_date) if instance.start_date else None,
        'end_date': str(instance.end_date) if instance.end_date else None,
        'is_active': instance.is_active,
    }
    
    AuditLog.objects.create(
        user=instance.owner if instance.owner else None,
        action=action,
        action_category='payment',
        resource_type='Subscription',
        resource_id=str(instance.id),
        ip_address=get_default_ip(),  # FIXED: Added default IP
        user_agent='System Signal',   # FIXED: Added default user agent
        details=details,
    )