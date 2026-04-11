from rest_framework import serializers
from django.utils import timezone
from .models import Booking
from apps.hostels.serializers import HostelListSerializer

class BookingSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.full_name', read_only=True)
    student_email = serializers.EmailField(source='student.email', read_only=True)
    student_phone = serializers.SerializerMethodField()
    hostel_details = HostelListSerializer(source='hostel', read_only=True)
    
    # Fields for admin dashboard frontend compatibility
    user_email = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    hostel_name = serializers.SerializerMethodField()
    check_in = serializers.SerializerMethodField()
    check_out = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'student', 'student_name', 'student_email', 'student_phone',
            'user_email', 'user_name', 'hostel', 'hostel_name', 'hostel_details',
            'move_in_date', 'check_in', 'check_out', 'guests', 'status',
            'special_requests', 'created_at', 'updated_at', 'expires_at',
            'total_amount', 'deposit_paid', 'deposit_amount', 'is_expired', 'time_remaining'
        ]
        read_only_fields = ['student', 'created_at', 'updated_at']

    def get_student_phone(self, obj):
        if hasattr(obj.student, 'student_profile'):
            return str(obj.student.student_profile.phone_number)
        return None

    def get_user_email(self, obj):
        return obj.student.email if obj.student else None

    def get_user_name(self, obj):
        return obj.student.full_name if obj.student else None

    def get_hostel_name(self, obj):
        return obj.hostel.name if obj.hostel else None

    def get_check_in(self, obj):
        return obj.move_in_date

    def get_check_out(self, obj):
        # If you have a move_out_date field, use it; otherwise return None
        return None

    def get_total_amount(self, obj):
        if obj.hostel:
            # Calculate total based on hostel price and guests
            return float(obj.hostel.price) * obj.guests
        return 0
    
    def get_is_expired(self, obj):
        return obj.is_expired()
    
    def get_time_remaining(self, obj):
        if obj.expires_at and obj.status == 'pending':
            remaining = obj.expires_at - timezone.now()
            if remaining.total_seconds() > 0:
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds % 3600) // 60
                return {'hours': hours, 'minutes': minutes, 'total_seconds': remaining.total_seconds()}
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = ['hostel', 'move_in_date', 'guests', 'special_requests']

    def validate_move_in_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError("Move‑in date cannot be in the past.")
        return value

    def validate(self, data):
        # Check for duplicate active booking
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            existing = Booking.objects.filter(
                student=request.user,
                hostel=data['hostel'],
                status__in=['pending', 'confirmed']
            ).first()
            if existing:
                raise serializers.ValidationError({
                    'existing_booking_id': str(existing.id),
                    'status': existing.status,
                    'message': 'You have already booked this hostel. You cannot book it again.'
                })
        
        # Check if hostel is available
        if not data['hostel'].available:
            raise serializers.ValidationError('This hostel is no longer available. Please choose another.')
        
        return data

    def create(self, validated_data):
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)