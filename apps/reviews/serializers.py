from rest_framework import serializers
from .models import Review

class ReviewSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_email = serializers.EmailField(source='student.email', read_only=True)
    student_avatar = serializers.SerializerMethodField()
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = [
            'id', 'student', 'student_name', 'student_email', 'student_avatar',
            'hostel', 'hostel_name', 'rating', 'comment', 'is_approved', 
            'created_at', 'updated_at', 'time_ago'
        ]
        read_only_fields = ['student', 'created_at', 'updated_at']
    
    def get_student_avatar(self, obj):
        if obj.student.full_name:
            initials = ''.join([word[0] for word in obj.student.full_name.split()[:2]]).upper()
            return initials
        return obj.student.email[0].upper()
    
    def get_time_ago(self, obj):
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff < timedelta(minutes=1):
            return 'Just now'
        elif diff < timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f'{minutes} minute{"s" if minutes > 1 else ""} ago'
        elif diff < timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f'{hours} hour{"s" if hours > 1 else ""} ago'
        elif diff < timedelta(days=7):
            days = diff.days
            return f'{days} day{"s" if days > 1 else ""} ago'
        else:
            return obj.created_at.strftime('%b %d, %Y')

class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ['hostel', 'rating', 'comment']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value

    def create(self, validated_data):
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)