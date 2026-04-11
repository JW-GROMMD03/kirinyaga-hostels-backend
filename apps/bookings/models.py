import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from apps.hostels.models import Hostel

class Booking(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Payment'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
        ('completed', 'Completed'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='bookings')
    move_in_date = models.DateField()
    guests = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    special_requests = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # 4-hour payment window
    deposit_paid = models.BooleanField(default=False)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['hostel', 'move_in_date']),
            models.Index(fields=['expires_at']),
        ]
        unique_together = ['student', 'hostel', 'status']  # Prevent duplicate active bookings

    def __str__(self):
        return f"{self.student.email} - {self.hostel.name} (move‑in: {self.move_in_date})"

    def save(self, *args, **kwargs):
        # Set expiry to 4 hours from creation if pending
        if not self.expires_at and self.status == 'pending':
            self.expires_at = timezone.now() + timedelta(hours=4)
            if self.hostel.deposit:
                self.deposit_amount = self.hostel.deposit
        super().save(*args, **kwargs)

    def is_expired(self):
        if self.status == 'pending' and self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def confirm_booking(self):
        """Confirm booking and mark hostel as unavailable"""
        self.status = 'confirmed'
        self.hostel.available = False
        self.hostel.save()
        self.save()
        
    def release_hostel(self):
        """Release hostel back to available (when booking expires or is cancelled)"""
        if self.hostel.available is False:
            # Check if there are any other active confirmed bookings for this hostel
            other_active = Booking.objects.filter(
                hostel=self.hostel,
                status='confirmed'
            ).exclude(id=self.id).exists()
            if not other_active:
                self.hostel.available = True
                self.hostel.save()