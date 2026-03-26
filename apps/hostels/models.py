import uuid
from django.db import models
from django.conf import settings
from phonenumber_field.modelfields import PhoneNumberField
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.notifications.models import Notification
from django.contrib.auth import get_user_model
from cloudinary.models import CloudinaryField

User = get_user_model()

class Hostel(models.Model):
    ROOM_TYPES = (
        ('bedsitter', 'Bedsitter'),
        ('single', 'Single Room'),
        ('one_bedroom', 'One Bedroom'),
        ('two_bedroom', 'Two Bedroom'),
        ('studio', 'Studio Apartment'),
        ('shared', 'Shared Room'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hostels')
    name = models.CharField(max_length=255)
    description = models.TextField()
    room_type = models.CharField(max_length=20, choices=ROOM_TYPES, default='bedsitter')
    capacity = models.IntegerField(default=1, help_text="Number of people the room can accommodate")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    deposit = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    utilities = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, help_text="Monthly utilities cost if separate")
    address = models.TextField()
    location_lat = models.FloatField(blank=True, null=True)
    location_lng = models.FloatField(blank=True, null=True)
    distance_to_university = models.FloatField(blank=True, null=True, help_text="Distance in km")
    is_approved = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    available = models.BooleanField(default=True)
    other_amenities = models.TextField(blank=True, help_text="Other amenities not in the list, separated by commas")
    views_count = models.IntegerField(default=0, help_text="Number of times the hostel has been viewed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner', 'is_approved']),
            models.Index(fields=['is_approved', 'available']),
            models.Index(fields=['is_featured']),
        ]

    def __str__(self):
        return f"{self.name} - {self.owner.email}"

    def increment_views(self):
        self.views_count += 1
        self.save(update_fields=['views_count'])


class HostelImage(models.Model):
    id = models.BigAutoField(primary_key=True)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='images')
    image = CloudinaryField('image')  # This stores the image on Cloudinary
    description = models.CharField(max_length=255, blank=True)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'created_at']

    def __str__(self):
        return f"Image for {self.hostel.name}"


class Amenity(models.Model):
    CATEGORY_CHOICES = (
        ('general', 'General'),
        ('security', 'Security'),
        ('furniture', 'Furniture'),
        ('utility', 'Utilities'),
        ('kitchen', 'Kitchen'),
        ('bathroom', 'Bathroom'),
        ('outdoor', 'Outdoor'),
    )
    
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    
    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Amenities'

    def __str__(self):
        return self.name


class HostelAmenity(models.Model):
    id = models.BigAutoField(primary_key=True)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='amenities')
    amenity = models.ForeignKey(Amenity, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('hostel', 'amenity')
        ordering = ['amenity__name']

    def __str__(self):
        return f"{self.hostel.name} - {self.amenity.name}"


class Availability(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='availability')
    date = models.DateField()
    available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('hostel', 'date')
        ordering = ['date']

    def __str__(self):
        return f"{self.hostel.name} - {self.date} - {'Available' if self.available else 'Booked'}"


class SavedHostel(models.Model):
    id = models.BigAutoField(primary_key=True) 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='saved_hostels')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'hostel')
        ordering = ['-saved_at']

    def __str__(self):
        return f"{self.user.email} saved {self.hostel.name}"


class HostelReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='hostel_reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('hostel', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.hostel.name} - {self.rating}★"


# Signals (unchanged)
@receiver(post_save, sender=Hostel)
def notify_students_on_new_hostel(sender, instance, created, **kwargs):
    if created and instance.is_approved and instance.available:
        students = User.objects.filter(role='student', is_active=True)
        for student in students:
            Notification.objects.create(
                user=student,
                type='hostel',
                title='New Hostel Available!',
                message=f"A new hostel '{instance.name}' has been added. Check it out now!",
                link=f"/student/hostel-detail.html?id={instance.id}"
            )


@receiver(post_save, sender=Hostel)
def notify_owner_on_approval(sender, instance, **kwargs):
    if not kwargs.get('created', False) and instance.is_approved:
        Notification.objects.create(
            user=instance.owner,
            type='hostel_approved',
            title='Hostel Approved!',
            message=f"Your hostel '{instance.name}' has been approved and is now visible to students.",
            link=f"/owner/hostel-detail.html?id={instance.id}"
        )