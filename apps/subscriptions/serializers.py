from rest_framework import serializers
from .models import SubscriptionPlan, OwnerSubscription, PaymentTransaction, SubscriptionLog
from django.utils import timezone

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    features_list = serializers.SerializerMethodField()
    
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'display_name', 'description', 'price_kes', 'duration_days',
                  'max_hostels', 'max_images_per_hostel', 'can_feature_listings', 
                  'priority_support', 'analytics_access', 'api_access', 'features_list', 'is_active']
    
    def get_features_list(self, obj):
        return obj.get_features_list()


class OwnerSubscriptionSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source='plan', read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_id = serializers.UUIDField(source='owner.id', read_only=True)
    plan_name = serializers.CharField(source='plan.display_name', read_only=True)
    plan_display_name = serializers.CharField(source='plan.display_name', read_only=True)
    days_remaining = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    can_add_hostel = serializers.SerializerMethodField()
    bonus_reason = serializers.SerializerMethodField()
    
    class Meta:
        model = OwnerSubscription
        fields = [
            'id', 'owner', 'owner_id', 'owner_email', 'owner_name', 'plan', 'plan_details',
            'plan_name', 'plan_display_name',
            'start_date', 'end_date', 'is_active', 'auto_renew', 'payment_status',
            'payment_method', 'payment_reference', 'amount_paid', 'mpesa_receipt_number',
            'days_remaining', 'is_expired', 'can_add_hostel', 'admin_notes',
            'created_at', 'updated_at',
            # ✅ ADDED BONUS FIELDS
            'is_bonus', 'bonus_weeks', 'bonus_reason',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_days_remaining(self, obj):
        return obj.days_remaining()
    
    def get_is_expired(self, obj):
        return obj.is_expired()
    
    def get_can_add_hostel(self, obj):
        can, message = obj.can_add_hostel()
        return {'can': can, 'message': message}
    
    def get_bonus_reason(self, obj):
        """Extract the bonus reason from admin_notes"""
        if obj.is_bonus and obj.admin_notes:
            # Try to extract reason from admin_notes
            # Format: "Bonus: X weeks - Reason here"
            if ' - ' in obj.admin_notes:
                return obj.admin_notes.split(' - ', 1)[1]
            return obj.admin_notes
        return None


class CreateSubscriptionSerializer(serializers.Serializer):
    plan_id = serializers.UUIDField()
    auto_renew = serializers.BooleanField(default=False)
    payment_method = serializers.CharField(default='mpesa')
    phone_number = serializers.CharField(required=False, allow_blank=True)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = '__all__'


class SubscriptionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionLog
        fields = '__all__'


class MpesaSTKPushSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    plan_id = serializers.UUIDField()


class AdminManualSubscriptionSerializer(serializers.Serializer):
    owner_email = serializers.EmailField()
    plan_id = serializers.UUIDField()
    duration_days = serializers.IntegerField(default=30)
    notes = serializers.CharField(required=False, allow_blank=True)