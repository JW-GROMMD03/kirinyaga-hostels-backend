import uuid
from django.db import models
from django.conf import settings

class Notification(models.Model):
    TYPE_CHOICES = (
        ('bulk', 'Bulk Notification'),
        ('owner_approved', 'Owner Approved'),
        ('hostel_approved', 'Hostel Approved'),
        ('hostel_rejected', 'Hostel Rejected'),
        ('booking', 'Booking'),
        ('payment', 'Payment'),
        ('alert', 'Alert'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='bulk')
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    @classmethod
    def cleanup_old_notifications(cls, days=7):
        """Delete notifications older than specified days"""
        cutoff_date = timezone.now() - timedelta(days=days)
        deleted_count, _ = cls.objects.filter(created_at__lt=cutoff_date).delete()
        return deleted_count

class EmailLog(models.Model):
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    message = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('sent','Sent'),('failed','Failed')])
    error_message = models.TextField(blank=True)
    notification_id = models.ForeignKey('Notification', on_delete=models.SET_NULL, null=True)

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