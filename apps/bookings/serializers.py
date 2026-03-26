from rest_framework import serializers
from django.utils import timezone
from .models import Booking
from apps.hostels.serializers import HostelListSerializer

class BookingSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_email = serializers.EmailField(source='student.email', read_only=True)
    student_phone = serializers.SerializerMethodField()
    hostel_details = HostelListSerializer(source='hostel', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'student', 'student_name', 'student_email', 'student_phone',
            'hostel', 'hostel_details', 'move_in_date',
            'guests', 'status', 'special_requests',
            'created_at', 'updated_at', 'expires_at'
        ]
        read_only_fields = ['student', 'created_at', 'updated_at']

    def get_student_phone(self, obj):
        # Adjust based on your user profile structure
        if hasattr(obj.student, 'student_profile'):
            return str(obj.student.student_profile.phone_number)
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['hostel', 'move_in_date', 'guests', 'special_requests']

    def validate_move_in_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Move‑in date cannot be in the past.")
        return value

    def create(self, validated_data):
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)