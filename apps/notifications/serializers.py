from rest_framework import serializers
from .models import Notification, Announcement, NewsletterSubscriber

class NotificationSerializer(serializers.ModelSerializer):
    time_until_delete = serializers.SerializerMethodField()
    expires_soon = serializers.SerializerMethodField()
    created_at_formatted = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'type', 'link', 'is_read', 
            'created_at', 'created_at_formatted', 'time_until_delete', 
            'expires_soon', 'is_deleted'
        ]
    
    def get_time_until_delete(self, obj):
        return obj.time_until_delete
    
    def get_expires_soon(self, obj):
        return obj.expires_soon
    
    def get_created_at_formatted(self, obj):
        from django.utils import timezone
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff.days == 0:
            if diff.seconds < 3600:
                minutes = diff.seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                hours = diff.seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.days == 1:
            return "Yesterday"
        else:
            return f"{diff.days} days ago"


class AnnouncementSerializer(serializers.ModelSerializer):
    is_valid = serializers.SerializerMethodField()
    expires_in = serializers.SerializerMethodField()
    
    class Meta:
        model = Announcement
        fields = ['id', 'message', 'link', 'is_active', 'expires_at', 'is_valid', 'expires_in', 'created_at']
    
    def get_is_valid(self, obj):
        return obj.is_valid()
    
    def get_expires_in(self, obj):
        from django.utils import timezone
        remaining = obj.expires_at - timezone.now()
        if remaining.total_seconds() > 0:
            days = remaining.days
            hours = remaining.seconds // 3600
            return f"{days}d {hours}h"
        return "Expired"


class NewsletterSubscriberSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscriber
        fields = ['id', 'email', 'is_active', 'subscribed_at']