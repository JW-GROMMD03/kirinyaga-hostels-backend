from rest_framework import serializers
from .models import (
    Hostel, HostelImage, Amenity, HostelAmenity, 
    Availability, SavedHostel, HostelReview
)
from apps.accounts.models import User

class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ['id', 'name', 'icon']


class HostelImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = HostelImage
        fields = ['id', 'image', 'description', 'is_primary']
        read_only_fields = ['id']


class HostelListSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    amenities = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    average_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    distance_to_university = serializers.FloatField()

    class Meta:
        model = Hostel
        fields = [
            'id', 'name', 'owner', 'owner_name', 'owner_email', 'room_type', 'capacity',
            'price', 'deposit', 'distance_to_university', 'address',
            'is_approved', 'is_featured', 'available', 'created_at',
            'primary_image', 'amenities', 'average_rating', 'total_reviews'
        ]

    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first()
        if img and img.image:
            return img.image.url  # CloudinaryField returns a URL
        img = obj.images.first()
        if img and img.image:
            return img.image.url
        return None

    def get_amenities(self, obj):
        return [ha.amenity.name for ha in obj.amenities.select_related('amenity').all()[:8]]

    def get_average_rating(self, obj):
        reviews = obj.hostel_reviews.filter(is_approved=True)
        if reviews.exists():
            return round(sum(r.rating for r in reviews) / reviews.count(), 1)
        return None

    def get_total_reviews(self, obj):
        return obj.hostel_reviews.filter(is_approved=True).count()


class HostelDetailSerializer(serializers.ModelSerializer):
    images = HostelImageSerializer(many=True, read_only=True)
    amenities = serializers.SerializerMethodField()
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_email = serializers.EmailField(source='owner.email', read_only=True)
    owner_phone = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    deposit = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    utilities = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)

    class Meta:
        model = Hostel
        fields = '__all__'
        read_only_fields = ['owner', 'views_count', 'created_at', 'updated_at']

    def get_owner_phone(self, obj):
        if hasattr(obj.owner, 'owner_profile') and obj.owner.owner_profile:
            return str(obj.owner.owner_profile.primary_phone)
        return None

    def get_amenities(self, obj):
        amenities = obj.amenities.select_related('amenity').all()
        return AmenitySerializer([ha.amenity for ha in amenities], many=True).data

    def get_average_rating(self, obj):
        reviews = obj.hostel_reviews.filter(is_approved=True)
        if reviews.exists():
            return round(sum(r.rating for r in reviews) / reviews.count(), 1)
        return None

    def get_total_reviews(self, obj):
        return obj.hostel_reviews.filter(is_approved=True).count()

    def get_reviews(self, obj):
        reviews = obj.hostel_reviews.filter(is_approved=True).select_related('user')[:5]
        return [{
            'id': r.id,
            'user_name': r.user.full_name,
            'rating': r.rating,
            'comment': r.comment,
            'created_at': r.created_at
        } for r in reviews]

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedHostel.objects.filter(user=request.user, hostel=obj).exists()
        return False


class HostelCreateUpdateSerializer(serializers.ModelSerializer):
    images = serializers.ListField(
        child=serializers.ImageField(), 
        write_only=True, 
        required=False
    )
    image_descriptions = serializers.ListField(
        child=serializers.CharField(), 
        write_only=True, 
        required=False
    )
    amenity_ids = serializers.ListField(
        child=serializers.UUIDField(), 
        write_only=True, 
        required=False
    )

    class Meta:
        model = Hostel
        fields = [
            'name', 'description', 'room_type', 'capacity', 'price', 'deposit',
            'utilities', 'address', 'location_lat', 'location_lng',
            'distance_to_university', 'other_amenities', 'images', 
            'image_descriptions', 'amenity_ids'
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def create(self, validated_data):
        images = validated_data.pop('images', [])
        image_descriptions = validated_data.pop('image_descriptions', [])
        amenity_ids = validated_data.pop('amenity_ids', [])
        
        hostel = Hostel.objects.create(**validated_data)
        
        for i, image in enumerate(images):
            description = image_descriptions[i] if i < len(image_descriptions) else ''
            HostelImage.objects.create(
                hostel=hostel,
                image=image,          # CloudinaryField handles upload automatically
                description=description,
                is_primary=(i == 0)
            )
        
        for amenity_id in amenity_ids:
            HostelAmenity.objects.create(
                hostel=hostel,
                amenity_id=amenity_id
            )
        
        return hostel

    def update(self, instance, validated_data):
        images = validated_data.pop('images', [])
        image_descriptions = validated_data.pop('image_descriptions', [])
        amenity_ids = validated_data.pop('amenity_ids', None)
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        if images:
            instance.images.all().delete()
            for i, image in enumerate(images):
                description = image_descriptions[i] if i < len(image_descriptions) else ''
                HostelImage.objects.create(
                    hostel=instance,
                    image=image,
                    description=description,
                    is_primary=(i == 0)
                )
        
        if amenity_ids is not None:
            instance.amenities.all().delete()
            for amenity_id in amenity_ids:
                HostelAmenity.objects.create(
                    hostel=instance,
                    amenity_id=amenity_id
                )
        
        instance.is_approved = False
        instance.save()
        
        return instance


class HostelSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    primary_image = serializers.SerializerMethodField()
    
    class Meta:
        model = Hostel
        fields = [
            'id', 'name', 'owner', 'owner_name', 'address',
            'distance_to_university', 'price', 'room_type',
            'is_approved', 'is_featured', 'created_at', 'views_count', 'primary_image'
        ]
    
    def get_primary_image(self, obj):
        img = obj.images.filter(is_primary=True).first()
        if img and img.image:
            return img.image.url
        img = obj.images.first()
        if img and img.image:
            return img.image.url
        return None


class SavedHostelSerializer(serializers.ModelSerializer):
    hostel = HostelListSerializer(read_only=True)
    
    class Meta:
        model = SavedHostel
        fields = ['id', 'hostel', 'saved_at']


class HostelReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = HostelReview
        fields = ['id', 'user', 'user_name', 'rating', 'comment', 'created_at']
        read_only_fields = ['user', 'created_at']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1 and 5")
        return value

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Availability
        fields = ['id', 'date', 'available']


class SimpleHostelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hostel
        fields = ['id', 'name', 'price', 'is_approved', 'is_featured']