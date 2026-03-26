from rest_framework import serializers
from .models import RoommateAd, ScamReport
from apps.hostels.models import Amenity

class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ['id', 'name']

class RoommateAdSerializer(serializers.ModelSerializer):
    amenities = serializers.PrimaryKeyRelatedField(queryset=Amenity.objects.all(), many=True, required=False)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_phone = serializers.SerializerMethodField()
    photo_urls = serializers.SerializerMethodField()

    class Meta:
        model = RoommateAd
        fields = [
            'id', 'user', 'user_name', 'user_email', 'user_phone',
            'hostel_name', 'location', 'room_type', 'description',
            'amenities', 'contact_phone', 'photo1', 'photo2', 'photo3', 'photo4',
            'photo_urls', 'created_at', 'is_active', 'reported_count'
        ]
        read_only_fields = ['user', 'is_active', 'reported_count']

    def get_user_phone(self, obj):
        if hasattr(obj.user, 'student_profile'):
            return str(obj.user.student_profile.phone_number)
        return None

    def get_photo_urls(self, obj):
        urls = []
        for field in ['photo1', 'photo2', 'photo3', 'photo4']:
            photo = getattr(obj, field)
            if photo:
                urls.append(photo.url)
        return urls

    def create(self, validated_data):
        amenities = validated_data.pop('amenities', [])
        validated_data['user'] = self.context['request'].user
        ad = RoommateAd.objects.create(**validated_data)
        ad.amenities.set(amenities)
        return ad

class ScamReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScamReport
        fields = ['id', 'ad', 'reason', 'created_at', 'resolved']
        read_only_fields = ['reported_by', 'resolved']

    def create(self, validated_data):
        validated_data['reported_by'] = self.context['request'].user
        report = ScamReport.objects.create(**validated_data)
        ad = validated_data['ad']
        ad.reported_count += 1
        ad.save()
        return report