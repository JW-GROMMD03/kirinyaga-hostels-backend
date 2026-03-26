from rest_framework import serializers
from .models import SubscriptionPlan, OwnerSubscription

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'price', 'duration_days', 'max_hostels', 
                  'max_images_per_hostel', 'is_featured_listing', 
                  'priority_support', 'is_active', 'created_at', 'updated_at']

class OwnerSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=SubscriptionPlan.objects.all(), 
        source='plan', 
        write_only=True, 
        required=False,
        allow_null=True
    )
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)

    class Meta:
        model = OwnerSubscription
        fields = [
            'id', 'owner', 'owner_email', 'owner_name', 'plan', 'plan_id',
            'start_date', 'end_date', 'is_active', 'auto_renew', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['owner', 'start_date', 'end_date', 'is_active', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """Ensure plan data is properly formatted"""
        data = super().to_representation(instance)
        
        # If plan exists but plan data is None, try to populate it
        if instance.plan and not data.get('plan'):
            # Manually serialize the plan
            data['plan'] = {
                'id': instance.plan.id,
                'name': instance.plan.name,
                'price': instance.plan.price,
                'duration_days': instance.plan.duration_days,
                'max_hostels': instance.plan.max_hostels,
                'max_images_per_hostel': instance.plan.max_images_per_hostel,
                'is_active': instance.plan.is_active
            }
        
        # Ensure is_active is included
        data['is_active'] = instance.is_active
            
        return data

# REMOVED: PaymentSerializer, PaymentInitiateSerializer, PaymentVerifySerializer