import uuid
from django.db import models
from django.conf import settings
from apps.hostels.models import Hostel

class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='reviews')
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5 stars
    comment = models.TextField()
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['student', 'hostel']  # One review per student per hostel
        indexes = [
            models.Index(fields=['hostel', 'is_approved']),
            models.Index(fields=['student']),
        ]

    def __str__(self):
        return f"Review by {self.student.email} for {self.hostel.name} - {self.rating}★"