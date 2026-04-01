import uuid
import pyotp
import secrets
import logging
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from phonenumber_field.modelfields import PhoneNumberField

logger = logging.getLogger(__name__)


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('email_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLES = (
        ('student', 'Student'),
        ('owner', 'Hostel Owner'),
        ('admin', 'Administrator'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=10, choices=ROLES, default='student')
    
    # Security fields
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # 2FA
    otp_secret = models.CharField(max_length=32, blank=True)
    is_2fa_enabled = models.BooleanField(default=False)
    
    # Verification
    email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Rate limiting / lockout
    failed_login_attempts = models.IntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    
    # Session tracking for single-device login
    current_session_token = models.CharField(max_length=255, blank=True, null=True)
    last_session_created = models.DateTimeField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    avatar = models.URLField(max_length=500, null=True, blank=True)
    avatar_public_id = models.CharField(max_length=255, null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']
    
    def __str__(self):
        return f"{self.full_name} ({self.email})"
    
    def generate_otp_secret(self):
        self.otp_secret = pyotp.random_base32()
        self.save()
    
    def get_totp_uri(self):
        return pyotp.totp.TOTP(self.otp_secret).provisioning_uri(
            name=self.email,
            issuer_name="Kirinyaga Hostels"
        )
    
    def verify_totp(self, token):
        totp = pyotp.TOTP(self.otp_secret)
        return totp.verify(token)
    
    def generate_email_verification_token(self):
        self.email_verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        self.save()
        return self.email_verification_token
    
    def reset_lockout(self):
         """Reset lockout status"""
         self.failed_login_attempts = 0
         self.locked_until = None
         self.save()

    def send_verification_email(self):
        """Send email verification link - NO TEMPLATES"""
        try:
            token = self.generate_email_verification_token()
            verification_url = f"{settings.FRONTEND_URL}/verify-email.html?token={token}&email={self.email}"
            
            subject = "Verify Your Email - Kirinyaga Hostels"
            
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background-color: #006747;
            color: white;
            padding: 30px 20px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            background-color: white;
            padding: 30px 20px;
            border-radius: 0 0 10px 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .button {{
            display: inline-block;
            padding: 14px 30px;
            background-color: #006747;
            color: white !important;
            text-decoration: none;
            border-radius: 50px;
            font-weight: bold;
            font-size: 16px;
            margin: 20px 0;
            border: none;
            box-shadow: 0 4px 10px rgba(0,103,71,0.3);
        }}
        .button:hover {{
            background-color: #004d33;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            font-size: 12px;
            color: #999;
        }}
        .link-break {{
            word-break: break-all;
            background-color: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 14px;
            margin: 15px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Kirinyaga Hostels</h1>
        </div>
        <div class="content">
            <h2 style="color: #006747;">Hello {self.full_name},</h2>
            <p style="font-size: 16px;">Thank you for registering with <strong>Kirinyaga Hostels</strong>!</p>
            <p style="font-size: 16px;">Please verify your email address by clicking the button below:</p>
            <p style="text-align: center;">
                <a href="{verification_url}" class="button">✓ VERIFY EMAIL ADDRESS</a>
            </p>
            <p style="font-size: 16px;">Or copy and paste this link into your browser:</p>
            <div class="link-break">{verification_url}</div>
            <p style="font-size: 14px; color: #e67e22;"><strong>⏰ This link will expire in 24 hours.</strong></p>
            <p style="font-size: 14px; color: #666;">If you did not register for Kirinyaga Hostels, please ignore this email.</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 Kirinyaga Hostels. All rights reserved.</p>
            <p>Kirinyaga University, Kerugoya, Kenya</p>
            <p style="margin-top: 10px;">
                <small>This is an automated message, please do not reply to this email.</small>
            </p>
        </div>
    </div>
</body>
</html>"""
            
            text_content = f"""
Kirinyaga Hostels - Email Verification

Hello {self.full_name},

Thank you for registering with Kirinyaga Hostels!

Please verify your email address by clicking the link below:

{verification_url}

This link will expire in 24 hours.

If you did not register for Kirinyaga Hostels, please ignore this email.

Best regards,
Kirinyaga Hostels Team
Kirinyaga University, Kerugoya, Kenya
            """
            
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = [self.email]
            
            msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            
            logger.info(f"✅ Verification email sent to {self.email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send verification email to {self.email}: {str(e)}")
            # Fallback to plain text
            try:
                from django.core.mail import send_mail
                text_content = f"""
Kirinyaga Hostels - Email Verification

Hello {self.full_name},

Please verify your email by visiting: {verification_url}

This link expires in 24 hours.
                """
                send_mail(subject, text_content, from_email, to_email, fail_silently=False)
                logger.info(f"✅ Fallback plain text email sent to {self.email}")
                return True
            except Exception as e2:
                logger.error(f"❌ Fallback also failed: {str(e2)}")
                return False

    def send_password_reset_email(self, token):
        """Send password reset email - NO TEMPLATES"""
        try:
            reset_url = f"{settings.FRONTEND_URL}/owner/reset-password.html?token={token}&email={self.email}"
            
            subject = "Reset Your Password - Kirinyaga Hostels"
            
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background-color: #006747;
            color: white;
            padding: 30px 20px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            background-color: white;
            padding: 30px 20px;
            border-radius: 0 0 10px 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .button {{
            display: inline-block;
            padding: 14px 30px;
            background-color: #006747;
            color: white !important;
            text-decoration: none;
            border-radius: 50px;
            font-weight: bold;
            font-size: 16px;
            margin: 20px 0;
            border: none;
            box-shadow: 0 4px 10px rgba(0,103,71,0.3);
        }}
        .button:hover {{
            background-color: #004d33;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            font-size: 12px;
            color: #999;
        }}
        .warning {{
            color: #e67e22;
            font-weight: bold;
        }}
        .link-break {{
            word-break: break-all;
            background-color: #f5f5f5;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            font-size: 14px;
            margin: 15px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Kirinyaga Hostels</h1>
        </div>
        <div class="content">
            <h2 style="color: #006747;">Hello {self.full_name},</h2>
            <p style="font-size: 16px;">We received a request to reset your password for your Kirinyaga Hostels account.</p>
            <p style="font-size: 16px;">Click the button below to set a new password:</p>
            <p style="text-align: center;">
                <a href="{reset_url}" class="button">🔐 RESET PASSWORD</a>
            </p>
            <p style="font-size: 16px;">Or copy and paste this link into your browser:</p>
            <div class="link-break">{reset_url}</div>
            <p class="warning"><strong>⏰ This link will expire in 1 hour.</strong></p>
            <p style="font-size: 14px; color: #666;">If you did not request a password reset, please ignore this email. Your password will remain unchanged.</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 Kirinyaga Hostels. All rights reserved.</p>
            <p>Kirinyaga University, Kerugoya, Kenya</p>
        </div>
    </div>
</body>
</html>"""
            
            text_content = f"""
Kirinyaga Hostels - Password Reset

Hello {self.full_name},

We received a request to reset your password for your Kirinyaga Hostels account.

Click the link below to set a new password:

{reset_url}

This link will expire in 1 hour.

If you did not request a password reset, please ignore this email. Your password will remain unchanged.

Best regards,
Kirinyaga Hostels Team
Kirinyaga University, Kerugoya, Kenya
            """
            
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = [self.email]
            
            msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            
            logger.info(f"✅ Password reset email sent to {self.email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send password reset email to {self.email}: {str(e)}")
            return False

    def send_2fa_otp_email(self, otp_code):
        """Send 2FA OTP email - NO TEMPLATES"""
        try:
            subject = "Your Two-Factor Authentication Code - Kirinyaga Hostels"
            
            html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
        }}
        .header {{
            background-color: #006747;
            color: white;
            padding: 30px 20px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .content {{
            background-color: white;
            padding: 30px 20px;
            border-radius: 0 0 10px 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .otp-code {{
            font-size: 48px;
            font-weight: bold;
            color: #006747;
            letter-spacing: 10px;
            background-color: #f5f5f5;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            font-family: monospace;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            font-size: 12px;
            color: #999;
        }}
        .warning {{
            color: #e67e22;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Kirinyaga Hostels</h1>
        </div>
        <div class="content">
            <h2 style="color: #006747;">Hello {self.full_name},</h2>
            <p style="font-size: 16px;">Your two-factor authentication code is:</p>
            <div class="otp-code">{otp_code}</div>
            <p class="warning"><strong>⏰ This code will expire in 10 minutes.</strong></p>
            <p style="font-size: 14px; color: #666;">If you didn't request this code, please ignore this email and secure your account.</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 Kirinyaga Hostels. All rights reserved.</p>
            <p>Kirinyaga University, Kerugoya, Kenya</p>
        </div>
    </div>
</body>
</html>"""
            
            text_content = f"""
Kirinyaga Hostels - Two-Factor Authentication Code

Hello {self.full_name},

Your two-factor authentication code is: {otp_code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email and secure your account.

Best regards,
Kirinyaga Hostels Team
Kirinyaga University, Kerugoya, Kenya
            """
            
            from_email = settings.DEFAULT_FROM_EMAIL
            to_email = [self.email]
            
            msg = EmailMultiAlternatives(subject, text_content, from_email, to_email)
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            
            logger.info(f"✅ 2FA OTP email sent to {self.email}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send 2FA OTP email to {self.email}: {str(e)}")
            return False


class PasswordResetToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Password reset token for {self.user.email}"

    def is_valid(self):
        return not self.used and timezone.now() <= self.expires_at


class TwoFactorOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='two_factor_otps')
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"2FA OTP for {self.user.email}"

    def is_valid(self):
        return not self.used and timezone.now() <= self.expires_at


# ---------- RoomType and updated HostelOwnerProfile ----------
class RoomType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name


class HostelOwnerProfile(models.Model):
    LOCATION_CHOICES = (
        ('kutus', 'Kutus'),
        ('mjini', 'Mjini'),
        ('diaspora', 'Diaspora'),
        ('moringa', 'Moringa'),
        ('ngomongo', 'Ngomongo'),
        ('alabama', 'Alabama'),
        ('other', 'Other'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='owner_profile')
    hostel_name = models.CharField(max_length=255)
    hostel_location = models.CharField(max_length=50, choices=LOCATION_CHOICES)
    other_location = models.CharField(max_length=255, blank=True)
    specific_address = models.TextField()
    primary_phone = PhoneNumberField(region='KE')
    secondary_phone = PhoneNumberField(region='KE', blank=True)
    room_types = models.ManyToManyField(RoomType, related_name='owner_profiles', blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    distance_to_university = models.FloatField(null=True, blank=True, help_text="Distance in km")
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_owners')
    verified_badge = models.BooleanField(default=False)
    fraud_score = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Owner: {self.user.full_name} - {self.hostel_name}"
    
    def save(self, *args, **kwargs):
        if self.secondary_phone and self.primary_phone == self.secondary_phone:
            raise ValueError("Primary and secondary phone numbers must be different")
        if self.latitude and self.longitude:
            self.distance_to_university = self.calculate_distance_to_university()
        super().save(*args, **kwargs)
    
    def calculate_distance_to_university(self):
        import math
        uni_lat, uni_lon = -0.4975, 37.3214
        R = 6371
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(uni_lat), math.radians(uni_lon)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        return round(R * c, 2)


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    registration_number = models.CharField(max_length=50, unique=True)
    phone_number = PhoneNumberField(region='KE')
    course = models.CharField(max_length=100, blank=True)
    year_of_study = models.IntegerField(null=True, blank=True)
    emergency_contact = PhoneNumberField(region='KE', blank=True)
    budget_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Student: {self.user.full_name} ({self.registration_number})"


class AdminNotification(models.Model):
    NOTIFICATION_TYPES = (
        ('new_owner', 'New Owner Registration'),
        ('new_student', 'New Student Registration'),
        ('owner_approved', 'Owner Approved'),
        ('fraud_alert', 'Fraud Alert'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type}: {self.title}"


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    details = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']


class SystemSettings(models.Model):
    """System settings that persist in the database"""
    site_name = models.CharField(max_length=255, default='Kirinyaga Hostels')
    admin_email = models.EmailField(default='admin@kirinyagahostels.com')
    contact_phone = models.CharField(max_length=20, default='+254712345678')
    max_login_attempts = models.IntegerField(default=5)
    admin_max_attempts = models.IntegerField(default=3)
    lockout_hours = models.IntegerField(default=1)
    twofa_required = models.BooleanField(default=False)
    session_timeout = models.IntegerField(default=30, help_text='Session timeout in minutes')
    maintenance_mode = models.BooleanField(default=False)
    
    # Features
    roommate_finder_enabled = models.BooleanField(default=True)
    student_reviews_enabled = models.BooleanField(default=True)
    owner_chat_enabled = models.BooleanField(default=True)
    subscriptions_enabled = models.BooleanField(default=True)
    google_maps_enabled = models.BooleanField(default=True)
    notifications_enabled = models.BooleanField(default=True)
    
    # Metadata
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'
    
    def __str__(self):
        return f"System Settings (updated {self.updated_at})"
    
    @classmethod
    def get_settings(cls):
        """Get or create the singleton settings instance"""
        obj, created = cls.objects.get_or_create(id=1)
        return obj

