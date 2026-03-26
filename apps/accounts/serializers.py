from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.db import models
import re
import random
from .models import User, StudentProfile, HostelOwnerProfile, RoomType, AdminNotification, PasswordResetToken, TwoFactorOTP, SystemSettings
from apps.hostels.models import Hostel
from apps.chat.models import Conversation, Message
from apps.subscriptions.models import SubscriptionPlan, OwnerSubscription
from apps.notifications.models import Notification

# -------------------- Student Signup --------------------
class StudentSignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    registration_number = serializers.CharField()
    phone_number = serializers.CharField()
    
    class Meta:
        model = User
        fields = ['email', 'full_name', 'password', 'password_confirm', 
                 'registration_number', 'phone_number']
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists")
        return value
    
    def validate_phone_number(self, value):
        pattern = r'^(?:\+254|0)[17]\d{8}$'
        if not re.match(pattern, value):
            raise serializers.ValidationError("Enter a valid Kenyan phone number (e.g., 0712345678 or +254712345678)")
        return value
    
    def validate_registration_number(self, value):
        if StudentProfile.objects.filter(registration_number=value).exists():
            raise serializers.ValidationError("This registration number is already registered")
        return value
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match"})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        registration_number = validated_data.pop('registration_number')
        phone_number = validated_data.pop('phone_number')
        
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data['full_name'],
            role='student'
        )
        
        StudentProfile.objects.create(
            user=user,
            registration_number=registration_number,
            phone_number=phone_number
        )
        
        user.send_verification_email()
        
        AdminNotification.objects.create(
            notification_type='new_student',
            title=f"New Student Registration: {user.full_name}",
            message=f"A new student has registered: {user.full_name} ({user.email})",
            related_user=user
        )
        
        return user


# -------------------- Owner Signup --------------------
class OwnerSignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    hostel_name = serializers.CharField()
    hostel_location = serializers.ChoiceField(choices=HostelOwnerProfile.LOCATION_CHOICES)
    other_location = serializers.CharField(required=False, allow_blank=True)
    specific_address = serializers.CharField()
    primary_phone = serializers.CharField()
    secondary_phone = serializers.CharField(required=False, allow_blank=True)
    room_types = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)

    class Meta:
        model = User
        fields = ['email', 'full_name', 'password', 'password_confirm',
                  'hostel_name', 'hostel_location', 'other_location', 'specific_address',
                  'primary_phone', 'secondary_phone', 'room_types']

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists")
        return value

    def validate_phone_numbers(self, primary, secondary):
        pattern = r'^(?:\+254|0)[17]\d{8}$'
        if not re.match(pattern, primary):
            raise serializers.ValidationError({"primary_phone": "Enter a valid Kenyan phone number"})
        if secondary and not re.match(pattern, secondary):
            raise serializers.ValidationError({"secondary_phone": "Enter a valid Kenyan phone number"})
        if secondary and primary == secondary:
            raise serializers.ValidationError({"secondary_phone": "Secondary phone must be different from primary"})

    def validate_room_types(self, value):
        valid_codes = set(RoomType.objects.values_list('code', flat=True))
        for code in value:
            if code not in valid_codes:
                raise serializers.ValidationError(f"Invalid room type code: {code}")
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match"})
        self.validate_phone_numbers(data['primary_phone'], data.get('secondary_phone', ''))
        if data['hostel_location'] == 'other' and not data.get('other_location'):
            raise serializers.ValidationError({"other_location": "Please specify the location"})
        if 'room_types' in data:
            self.validate_room_types(data['room_types'])
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        room_types_codes = validated_data.pop('room_types', [])
        owner_fields = {
            'hostel_name': validated_data.pop('hostel_name'),
            'hostel_location': validated_data.pop('hostel_location'),
            'other_location': validated_data.pop('other_location', ''),
            'specific_address': validated_data.pop('specific_address'),
            'primary_phone': validated_data.pop('primary_phone'),
            'secondary_phone': validated_data.pop('secondary_phone', ''),
        }

        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            full_name=validated_data['full_name'],
            role='owner'
        )

        profile = HostelOwnerProfile.objects.create(
            user=user,
            **owner_fields
        )

        if room_types_codes:
            room_types = RoomType.objects.filter(code__in=room_types_codes)
            profile.room_types.set(room_types)

        from .utils import geocode_address
        full_address = f"{owner_fields['specific_address']}, {owner_fields.get('other_location') or owner_fields['hostel_location']}, Kerugoya, Kenya"
        lat, lng = geocode_address(full_address)
        if lat and lng:
            profile.latitude = lat
            profile.longitude = lng
            profile.save()

        user.send_verification_email()

        AdminNotification.objects.create(
            notification_type='new_owner',
            title=f"New Hostel Owner Registration: {user.full_name}",
            message=f"A new hostel owner has registered: {user.full_name} - {owner_fields['hostel_name']}",
            related_user=user
        )

        return user


# -------------------- Student Login --------------------
class StudentLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    otp_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        otp_token = data.get('otp_token', '')

        # Check if account is locked
        try:
            user = User.objects.get(email=email)
            if user.locked_until and user.locked_until > timezone.now():
                remaining = user.locked_until - timezone.now()
                minutes = remaining.seconds // 60
                raise serializers.ValidationError(
                    f"Account locked due to too many failed attempts. Try again in {minutes} minute(s)."
                )
        except User.DoesNotExist:
            pass

        user = authenticate(email=email, password=password)
        
        if not user:
            # Increment failed attempts
            try:
                user = User.objects.get(email=email)
                user.failed_login_attempts += 1
                
                if user.failed_login_attempts == 5:
                    user.save()
                    raise serializers.ValidationError(
                        'Too many failed attempts. Please reset your password using the "Forgot Password" link.'
                    )
                elif user.failed_login_attempts >= 6:
                    user.locked_until = timezone.now() + timezone.timedelta(hours=1)
                    user.save()
                    raise serializers.ValidationError(
                        'Account locked for 1 hour due to multiple failed login attempts.'
                    )
                else:
                    user.save()
            except User.DoesNotExist:
                pass
            
            raise serializers.ValidationError('Invalid email or password')
        
        # SECURITY FIX: Check role for student login
        if user.role != 'student':
            raise serializers.ValidationError('This account is not a student account.')
        
        if not user.is_active:
            raise serializers.ValidationError('Account is disabled')
        
        if not user.email_verified:
            raise serializers.ValidationError('Please verify your email first')
        
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save()
        
        if user.is_2fa_enabled:
            if not otp_token:
                otp_code = f"{random.randint(100000, 999999)}"
                expires_at = timezone.now() + timezone.timedelta(minutes=10)
                TwoFactorOTP.objects.filter(user=user, used=False).update(used=True)
                TwoFactorOTP.objects.create(
                    user=user,
                    otp=otp_code,
                    expires_at=expires_at
                )
                user.send_2fa_otp_email(otp_code)
                raise serializers.ValidationError('OTP sent to your email. Please enter it to complete login.')
            else:
                try:
                    otp_obj = TwoFactorOTP.objects.filter(user=user, used=False).latest('created_at')
                    if not otp_obj.is_valid():
                        raise serializers.ValidationError('OTP has expired. Please request a new one.')
                    if otp_obj.otp != otp_token:
                        raise serializers.ValidationError('Invalid OTP code.')
                    otp_obj.used = True
                    otp_obj.save()
                except TwoFactorOTP.DoesNotExist:
                    raise serializers.ValidationError('No valid OTP found. Please request a new one.')

        data['user'] = user
        return data



# -------------------- Owner Login --------------------
# -------------------- Owner Login (with role validation) --------------------
class OwnerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    otp_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        otp_token = data.get('otp_token', '')

        try:
            user = User.objects.get(email=email)
            if user.locked_until and user.locked_until > timezone.now():
                remaining = user.locked_until - timezone.now()
                minutes = remaining.seconds // 60
                raise serializers.ValidationError(
                    f"Account locked due to too many failed attempts. Try again in {minutes} minute(s)."
                )
        except User.DoesNotExist:
            pass

        user = authenticate(email=email, password=password)
        
        if not user:
            try:
                user = User.objects.get(email=email)
                user.failed_login_attempts += 1
                
                if user.failed_login_attempts == 5:
                    user.save()
                    raise serializers.ValidationError(
                        'Too many failed attempts. Please reset your password using the "Forgot Password" link.'
                    )
                elif user.failed_login_attempts >= 6:
                    user.locked_until = timezone.now() + timezone.timedelta(hours=1)
                    user.save()
                    raise serializers.ValidationError(
                        'Account locked for 1 hour due to multiple failed login attempts.'
                    )
                else:
                    user.save()
            except User.DoesNotExist:
                pass
            
            raise serializers.ValidationError('Invalid email or password')
        
        # SECURITY FIX: Check role for owner login
        if user.role != 'owner':
            raise serializers.ValidationError('This account is not an owner account.')
        
        if not user.is_active:
            raise serializers.ValidationError('Account is disabled')
        
        if not user.email_verified:
            raise serializers.ValidationError('Please verify your email first')
        
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save()
        
        if user.is_2fa_enabled:
            if not otp_token:
                otp_code = f"{random.randint(100000, 999999)}"
                expires_at = timezone.now() + timezone.timedelta(minutes=10)
                TwoFactorOTP.objects.filter(user=user, used=False).update(used=True)
                TwoFactorOTP.objects.create(
                    user=user,
                    otp=otp_code,
                    expires_at=expires_at
                )
                user.send_2fa_otp_email(otp_code)
                raise serializers.ValidationError('OTP sent to your email. Please enter it to complete login.')
            else:
                try:
                    otp_obj = TwoFactorOTP.objects.filter(user=user, used=False).latest('created_at')
                    if not otp_obj.is_valid():
                        raise serializers.ValidationError('OTP has expired. Please request a new one.')
                    if otp_obj.otp != otp_token:
                        raise serializers.ValidationError('Invalid OTP code.')
                    otp_obj.used = True
                    otp_obj.save()
                except TwoFactorOTP.DoesNotExist:
                    raise serializers.ValidationError('No valid OTP found. Please request a new one.')

        data['user'] = user
        return data


# -------------------- Admin Login (with role validation) --------------------
class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    otp_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        otp_token = data.get('otp_token', '')

        try:
            user = User.objects.get(email=email)
            if user.locked_until and user.locked_until > timezone.now():
                remaining = user.locked_until - timezone.now()
                minutes = remaining.seconds // 60
                raise serializers.ValidationError(
                    f"Account locked due to too many failed attempts. Try again in {minutes} minute(s)."
                )
        except User.DoesNotExist:
            pass

        user = authenticate(email=email, password=password)
        
        if not user:
            try:
                user = User.objects.get(email=email)
                user.failed_login_attempts += 1
                
                if user.failed_login_attempts >= 3:
                    user.locked_until = timezone.now() + timezone.timedelta(hours=1)
                    user.save()
                    raise serializers.ValidationError(
                        'Account locked for 1 hour due to multiple failed login attempts.'
                    )
                else:
                    user.save()
            except User.DoesNotExist:
                pass
            
            raise serializers.ValidationError('Invalid email or password')
        
        # SECURITY FIX: Check role for admin login
        if user.role != 'admin' and not user.is_superuser:
            raise serializers.ValidationError('This account is not an admin account.')
        
        if not user.is_active:
            raise serializers.ValidationError('Account is disabled')
        
        if not user.email_verified:
            raise serializers.ValidationError('Please verify your email first')
        
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save()
        
        if user.is_2fa_enabled:
            if not otp_token:
                otp_code = f"{random.randint(100000, 999999)}"
                expires_at = timezone.now() + timezone.timedelta(minutes=10)
                TwoFactorOTP.objects.filter(user=user, used=False).update(used=True)
                TwoFactorOTP.objects.create(
                    user=user,
                    otp=otp_code,
                    expires_at=expires_at
                )
                user.send_2fa_otp_email(otp_code)
                raise serializers.ValidationError('OTP sent to your email. Please enter it to complete login.')
            else:
                try:
                    otp_obj = TwoFactorOTP.objects.filter(user=user, used=False).latest('created_at')
                    if not otp_obj.is_valid():
                        raise serializers.ValidationError('OTP has expired. Please request a new one.')
                    if otp_obj.otp != otp_token:
                        raise serializers.ValidationError('Invalid OTP code.')
                    otp_obj.used = True
                    otp_obj.save()
                except TwoFactorOTP.DoesNotExist:
                    raise serializers.ValidationError('No valid OTP found. Please request a new one.')

        data['user'] = user
        return data


# -------------------- Password Reset --------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value

class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match"})
        
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid token or email")
        
        try:
            reset_token = PasswordResetToken.objects.get(user=user, token=data['token'])
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid token or email")
        
        if not reset_token.is_valid():
            raise serializers.ValidationError("Token has expired or already used")
        
        data['user'] = user
        data['reset_token'] = reset_token
        return data


# -------------------- 2FA OTP --------------------
class TwoFactorOTPRequestSerializer(serializers.Serializer):
    pass

class TwoFactorOTPVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value

    def validate(self, data):
        user = self.context['request'].user
        if not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        try:
            otp_obj = TwoFactorOTP.objects.filter(user=user, used=False).latest('created_at')
        except TwoFactorOTP.DoesNotExist:
            raise serializers.ValidationError("No valid OTP found. Please request a new one.")

        if not otp_obj.is_valid():
            raise serializers.ValidationError("OTP has expired. Please request a new one.")

        if otp_obj.otp != data['otp']:
            raise serializers.ValidationError("Invalid OTP code.")

        data['otp_obj'] = otp_obj
        return data


# -------------------- 2FA Enable/Disable --------------------
class TwoFactorEnableSerializer(serializers.Serializer):
    pass

class TwoFactorDisableSerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value

    def validate(self, data):
        user = self.context['request'].user
        if not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        try:
            otp_obj = TwoFactorOTP.objects.filter(user=user, used=False).latest('created_at')
        except TwoFactorOTP.DoesNotExist:
            raise serializers.ValidationError("No valid OTP found. Please request a new one.")

        if not otp_obj.is_valid():
            raise serializers.ValidationError("OTP has expired. Please request a new one.")

        if otp_obj.otp != data['otp']:
            raise serializers.ValidationError("Invalid OTP code.")

        data['otp_obj'] = otp_obj
        return data


# -------------------- User Profile --------------------
class UserSerializer(serializers.ModelSerializer):
    student_profile = serializers.SerializerMethodField()
    owner_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'role', 'email_verified', 'is_2fa_enabled', 'student_profile', 'owner_profile']

    def get_student_profile(self, obj):
        if hasattr(obj, 'student_profile') and obj.student_profile:
            return {
                'registration_number': obj.student_profile.registration_number,
                'phone_number': str(obj.student_profile.phone_number),
                'course': obj.student_profile.course,
                'year_of_study': obj.student_profile.year_of_study,
                'budget_min': obj.student_profile.budget_min,
                'budget_max': obj.student_profile.budget_max,
            }
        return None

    def get_owner_profile(self, obj):
        if hasattr(obj, 'owner_profile') and obj.owner_profile:
            hostel_count = Hostel.objects.filter(owner=obj).count()
            return {
                'hostel_name': obj.owner_profile.hostel_name,
                'hostel_location': obj.owner_profile.hostel_location,
                'other_location': obj.owner_profile.other_location,
                'specific_address': obj.owner_profile.specific_address,
                'primary_phone': str(obj.owner_profile.primary_phone),
                'secondary_phone': str(obj.owner_profile.secondary_phone) if obj.owner_profile.secondary_phone else None,
                'room_types': list(obj.owner_profile.room_types.values_list('code', flat=True)),
                'latitude': obj.owner_profile.latitude,
                'longitude': obj.owner_profile.longitude,
                'distance_to_university': obj.owner_profile.distance_to_university,
                'is_approved': obj.owner_profile.is_approved,
                'verified_badge': obj.owner_profile.verified_badge,
                'fraud_score': obj.owner_profile.fraud_score,
                'hostel_count': hostel_count,
            }
        return None


# ==================== ADMIN SERIALIZERS ====================

class AdminStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    student_profile = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    last_login = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    locked_until = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'role', 'is_active', 
            'email_verified', 'is_2fa_enabled', 'date_joined',
            'last_login', 'failed_login_attempts', 'locked_until',
            'student_profile'
        ]

    def get_full_name(self, obj):
        return obj.full_name or obj.email.split('@')[0]

    def get_student_profile(self, obj):
        if hasattr(obj, 'student_profile') and obj.student_profile:
            profile = obj.student_profile
            return {
                'phone_number': str(profile.phone_number) if profile.phone_number else None,
                'registration_number': profile.registration_number,
                'course': profile.course,
                'year_of_study': profile.year_of_study,
            }
        return {
            'phone_number': None,
            'registration_number': None,
            'course': None,
            'year_of_study': None,
        }


class AdminOwnerSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    owner_profile = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'role', 'is_active',
            'email_verified', 'is_2fa_enabled', 'date_joined',
            'owner_profile'
        ]

    def get_full_name(self, obj):
        return obj.full_name or obj.email.split('@')[0]

    def get_owner_profile(self, obj):
        if hasattr(obj, 'owner_profile') and obj.owner_profile:
            profile = obj.owner_profile
            hostel_count = Hostel.objects.filter(owner=obj).count()
            return {
                'hostel_name': profile.hostel_name,
                'primary_phone': str(profile.primary_phone) if profile.primary_phone else None,
                'secondary_phone': str(profile.secondary_phone) if profile.secondary_phone else None,
                'specific_address': profile.specific_address,
                'is_approved': profile.is_approved,
                'verified_badge': profile.verified_badge,
                'fraud_score': profile.fraud_score,
                'hostel_count': hostel_count
            }
        return {
            'hostel_name': None,
            'primary_phone': None,
            'secondary_phone': None,
            'specific_address': None,
            'is_approved': False,
            'verified_badge': False,
            'fraud_score': 0,
            'hostel_count': 0
        }


class AdminHostelSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    owner_id = serializers.UUIDField(source='owner.id')
    images = serializers.SerializerMethodField()
    distance_to_university = serializers.FloatField()
    price = serializers.FloatField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    avg_rating = serializers.SerializerMethodField()
    total_reviews = serializers.SerializerMethodField()

    class Meta:
        model = Hostel
        fields = [
            'id', 'name', 'description', 'address', 'distance_to_university',
            'price', 'room_type', 'is_approved', 'is_featured', 'created_at',
            'owner_name', 'owner_id', 'images', 'avg_rating', 'total_reviews'
        ]

    def get_owner_name(self, obj):
        return obj.owner.full_name or obj.owner.email

    def get_images(self, obj):
        return [img.image.url for img in obj.images.all()[:3]]

    def get_avg_rating(self, obj):
        from apps.reviews.models import Review
        reviews = Review.objects.filter(hostel=obj, is_approved=True)
        avg = reviews.aggregate(avg=models.Avg('rating'))['avg']
        return float(avg) if avg else 0

    def get_total_reviews(self, obj):
        from apps.reviews.models import Review
        return Review.objects.filter(hostel=obj, is_approved=True).count()


class AdminSubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'price', 'duration_days', 'max_hostels']


class AdminOwnerSubscriptionSerializer(serializers.ModelSerializer):
    owner_email = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    plan_price = serializers.SerializerMethodField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = OwnerSubscription
        fields = [
            'id', 'owner_email', 'owner_name', 'plan_name', 'plan_price',
            'start_date', 'end_date', 'status', 'payment_status',
            'payment_method', 'amount_paid', 'is_active', 'created_at'
        ]

    def get_owner_email(self, obj):
        return obj.owner.email if obj.owner else None

    def get_owner_name(self, obj):
        return obj.owner.full_name if obj.owner else None

    def get_plan_name(self, obj):
        return obj.plan.name if obj.plan else None

    def get_plan_price(self, obj):
        return float(obj.plan.price) if obj.plan else None

    def get_start_date(self, obj):
        return obj.start_date.strftime("%Y-%m-%d %H:%M:%S") if obj.start_date else None

    def get_end_date(self, obj):
        return obj.end_date.strftime("%Y-%m-%d %H:%M:%S") if obj.end_date else None

    def get_created_at(self, obj):
        return obj.created_at.strftime("%Y-%m-%d %H:%M:%S") if obj.created_at else None

    def get_status(self, obj):
        return getattr(obj, 'status', None)

    def get_payment_status(self, obj):
        return getattr(obj, 'payment_status', None)

    def get_payment_method(self, obj):
        return getattr(obj, 'payment_method', None)

    def get_amount_paid(self, obj):
        return float(obj.amount_paid) if obj.amount_paid is not None else None

    def get_is_active(self, obj):
        return getattr(obj, 'is_active', False)


# ==================== ADMIN CHAT SERIALIZERS ====================
class AdminMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    timestamp = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Message
        fields = ['id', 'sender_name', 'content', 'timestamp', 'is_read']

    def get_sender_name(self, obj):
        return obj.sender.full_name if obj.sender else 'System'


class AdminConversationSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.EmailField(source='owner.email')
    last_message = serializers.SerializerMethodField()
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = ['id', 'owner_name', 'owner_email', 'last_message', 'updated_at', 'unread_count']

    def get_owner_name(self, obj):
        return obj.owner.full_name if obj.owner else None

    def get_last_message(self, obj):
        last = obj.messages.order_by('-timestamp').first()
        if last:
            return {'content': last.content, 'timestamp': last.timestamp}
        return None

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if request and request.user:
            return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
        return 0


# ==================== ADMIN NOTIFICATION SERIALIZER ====================
class AdminNotificationSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Notification
        fields = ['id', 'user_email', 'type', 'title', 'message', 'link', 'is_read', 'created_at']

    def get_user_email(self, obj):
        return obj.user.email if obj.user else None


# -------------------- Email Verification --------------------
class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    token = serializers.CharField()
    
    def validate(self, data):
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError('User not found')
        
        if user.email_verified:
            raise serializers.ValidationError('Email already verified')
        
        if user.email_verification_token != data['token']:
            raise serializers.ValidationError('Invalid verification token')
        
        if user.email_verification_sent_at:
            expiry = user.email_verification_sent_at + timezone.timedelta(hours=24)
            if timezone.now() > expiry:
                raise serializers.ValidationError('Verification link expired')
        
        data['user'] = user
        return data
    
# -------------------- Resend Verification --------------------
class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if user.email_verified:
                raise serializers.ValidationError('Email already verified')
        except User.DoesNotExist:
            pass
        return value

# ==================== EXTRA SERIALIZERS ====================
class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'role']


class SimpleHostelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Hostel
        fields = ['id', 'name', 'address', 'price']


class SimpleSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'price']


class SystemSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSettings
        fields = [
            'site_name', 'admin_email', 'contact_phone', 
            'max_login_attempts', 'admin_max_attempts', 'lockout_hours',
            'twofa_required', 'session_timeout', 'maintenance_mode',
            'roommate_finder_enabled', 'student_reviews_enabled', 
            'owner_chat_enabled', 'subscriptions_enabled', 
            'google_maps_enabled', 'notifications_enabled'
        ]


class SupportSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=50)
    subject = serializers.CharField(max_length=200)
    message = serializers.CharField()

    def validate_type(self, value):
        valid_types = ['question', 'complaint', 'feedback', 'bug', 'other']
        if value not in valid_types:
            raise serializers.ValidationError(f"Type must be one of: {', '.join(valid_types)}")
        return value