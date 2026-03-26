import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField()
    max_hostels = models.IntegerField(help_text="Use -1 for unlimited")
    max_images_per_hostel = models.IntegerField(default=5)
    is_featured_listing = models.BooleanField(default=False)
    priority_support = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class OwnerSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)
    auto_renew = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.owner.email} - {'Active' if self.is_active else 'Inactive'}"

    def is_valid(self):
        return self.is_active and self.end_date and self.end_date > timezone.now()
    
    @property
    def has_unlimited_access(self):
        """Always return True for free tier"""
        return True

# REMOVED: Payment model