import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class Notification(models.Model):
    TYPE_CHOICES = (
        ('bulk', 'Bulk Notification'),
        ('owner_approved', 'Owner Approved'),
        ('hostel_approved', 'Hostel Approved'),
        ('hostel_rejected', 'Hostel Rejected'),
        ('booking', 'Booking'),
        ('payment', 'Payment'),
        ('alert', 'Alert'),
        ('account_status', 'Account Status'),
        ('system', 'System'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='system')
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Auto-delete fields
    delete_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['is_read', 'user']),
            models.Index(fields=['delete_at']),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"
    
    def save(self, *args, **kwargs):
        # Set delete_at to 3 days from creation if not set
        if not self.delete_at and not self.pk:
            self.delete_at = timezone.now() + timedelta(days=3)
        super().save(*args, **kwargs)
    
    @property
    def time_until_delete(self):
        """Returns time until notification is deleted"""
        if self.delete_at:
            remaining = self.delete_at - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                seconds = remaining.seconds % 60
                return {
                    'days': days,
                    'hours': hours,
                    'minutes': minutes,
                    'seconds': seconds,
                    'total_seconds': remaining.total_seconds(),
                    'formatted': self.format_time_remaining(days, hours, minutes, seconds)
                }
        return {'days': 0, 'hours': 0, 'minutes': 0, 'seconds': 0, 'total_seconds': 0, 'formatted': 'Expired'}
    
    def format_time_remaining(self, days, hours, minutes, seconds):
        """Format time remaining in human readable format"""
        if days > 0:
            return f"{days}d {hours}h remaining"
        elif hours > 0:
            return f"{hours}h {minutes}m remaining"
        elif minutes > 0:
            return f"{minutes}m {seconds}s remaining"
        elif seconds > 0:
            return f"{seconds}s remaining"
        return "Expiring soon"
    
    @property
    def expires_soon(self):
        """Returns True if notification expires in less than 24 hours"""
        remaining = self.time_until_delete['total_seconds']
        return 0 < remaining < 86400  # 24 hours
    
    @property
    def is_expired(self):
        """Returns True if notification should be deleted"""
        return self.delete_at and timezone.now() >= self.delete_at
    
    @classmethod
    def cleanup_old_notifications(cls):
        """Delete notifications older than 3 days"""
        cutoff_date = timezone.now() - timedelta(days=3)
        deleted_count, _ = cls.objects.filter(
            created_at__lt=cutoff_date,
            is_deleted=False
        ).delete()
        return deleted_count


class EmailLog(models.Model):
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('sent','Sent'),('failed','Failed')])
    error_message = models.TextField(blank=True)
    notification = models.ForeignKey(Notification, on_delete=models.SET_NULL, null=True)


class Announcement(models.Model):
    """Site-wide announcement banner"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.TextField()
    link = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='created_announcements'  
    )
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'kyu_announcements'  
        verbose_name = 'Announcement'
        verbose_name_plural = 'Announcements'
    
    def __str__(self):
        return self.message[:50]
    
    def is_valid(self):
        return self.is_active and timezone.now() <= self.expires_at


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-subscribed_at']
    
    def __str__(self):
        return self.email