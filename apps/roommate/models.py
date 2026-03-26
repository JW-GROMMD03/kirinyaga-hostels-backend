import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField

class RoommateAd(models.Model):
    ROOM_TYPES = (
        ('bedsitter', 'Bedsitter'),
        ('single', 'Single Room'),
        ('one_bedroom', 'One Bedroom'),
        ('two_bedroom', 'Two Bedroom'),
        ('other', 'Other'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='roommate_ads')
    hostel_name = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='bedsitter')
    description = models.TextField(blank=True)
    amenities = models.ManyToManyField('hostels.Amenity', blank=True, related_name='roommate_ads')
    contact_phone = PhoneNumberField(region='KE')
    # Photos (up to 4)
    photo1 = models.ImageField(upload_to='roommate_photos/', blank=True, null=True)
    photo2 = models.ImageField(upload_to='roommate_photos/', blank=True, null=True)
    photo3 = models.ImageField(upload_to='roommate_photos/', blank=True, null=True)
    photo4 = models.ImageField(upload_to='roommate_photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    reported_count = models.IntegerField(default=0)
    blocked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.hostel_name} by {self.user.email}"

    def is_blocked(self):
        return self.blocked_until and timezone.now() < self.blocked_until


class ScamReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ad = models.ForeignKey(RoommateAd, on_delete=models.CASCADE, related_name='reports')
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    def __str__(self):
        return f"Report on {self.ad.id} by {self.reported_by.email if self.reported_by else 'Anonymous'}"