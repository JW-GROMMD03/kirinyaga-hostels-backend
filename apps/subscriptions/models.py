import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class SubscriptionPlan(models.Model):
    """Available subscription plans for owners"""
    PLAN_TYPES = (
        ('free', 'Free'),
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('enterprise', 'Enterprise'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=20, choices=PLAN_TYPES, unique=True)
    display_name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    price_kes = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    duration_days = models.IntegerField(default=30)
    
    # Limits
    max_hostels = models.IntegerField(default=1)
    max_images_per_hostel = models.IntegerField(default=5)
    can_feature_listings = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    analytics_access = models.BooleanField(default=False)
    api_access = models.BooleanField(default=False)
    
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['price_kes']
    
    def __str__(self):
        return f"{self.display_name} - KSh {self.price_kes}"
    
    def get_features_list(self):
        features = [
            f"Up to {self.max_hostels} hostels",
            f"{self.max_images_per_hostel} images per hostel"
        ]
        if self.can_feature_listings:
            features.append("Featured listings")
        if self.priority_support:
            features.append("Priority support")
        if self.analytics_access:
            features.append("Advanced analytics")
        if self.api_access:
            features.append("API access")
        return features


class OwnerSubscription(models.Model):
    """Active subscription for an owner"""
    PAYMENT_STATUS = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    auto_renew = models.BooleanField(default=False)
    
    # Payment tracking
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default='pending')
    payment_method = models.CharField(max_length=50, blank=True, null=True)
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    mpesa_receipt_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Admin notes
    admin_notes = models.TextField(blank=True)
    manually_activated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='activated_subscriptions')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
     # NEW FIELDS for bonus subscriptions and revoking
    is_bonus = models.BooleanField(default=False, help_text="Whether this is a free bonus subscription")
    revoked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='revoked_subscriptions')
    revoked_at = models.DateTimeField(null=True, blank=True)
    bonus_weeks = models.IntegerField(null=True, blank=True, help_text="Number of weeks granted as bonus")
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.owner.email} - {self.plan.display_name if self.plan else 'None'} - {'Active' if self.is_active else 'Inactive'}"
    
    def is_expired(self):
        return timezone.now() > self.end_date
    
    def days_remaining(self):
        if self.is_expired():
            return 0
        remaining = self.end_date - timezone.now()
        return remaining.days
    
    def can_add_hostel(self):
        """Check if owner can add a new hostel based on subscription"""
        if not self.is_active or self.is_expired():
            return False, "Your subscription has expired. Please renew to add more hostels."
        
        current_hostel_count = self.owner.hostels.count()
        if current_hostel_count >= self.plan.max_hostels:
            return False, f"You have reached your plan limit of {self.plan.max_hostels} hostels. Upgrade to add more."
        
        return True, ""


class PaymentTransaction(models.Model):
    """Track all payment transactions"""
    TRANSACTION_STATUS = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(OwnerSubscription, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50)  # mpesa, card, bank, manual
    transaction_id = models.CharField(max_length=255, unique=True, db_index=True)
    mpesa_receipt = models.CharField(max_length=50, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending')
    response_code = models.CharField(max_length=10, blank=True, null=True)
    response_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.transaction_id} - {self.amount} - {self.status}"


class SubscriptionLog(models.Model):
    """Log all subscription changes"""
    ACTIONS = (
        ('created', 'Created'),
        ('activated', 'Activated'),
        ('upgraded', 'Upgraded'),
        ('downgraded', 'Downgraded'),
        ('renewed', 'Renewed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('manual_activation', 'Manual Activation by Admin'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subscription = models.ForeignKey(OwnerSubscription, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=20, choices=ACTIONS)
    old_plan = models.CharField(max_length=50, blank=True, null=True)
    new_plan = models.CharField(max_length=50, blank=True, null=True)
    details = models.JSONField(default=dict)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.subscription.owner.email} - {self.action} - {self.created_at}"