import os
import dj_database_url
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build paths
BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================
# SECURITY SETTINGS
# ============================================
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY must be set in environment variables")

DEBUG = os.getenv('DEBUG', 'False') == 'True'

# Allow Render.com and other domains
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
ALLOWED_HOSTS.extend(['.onrender.com', '.railway.app', '.herokuapp.com', 'localhost', '127.0.0.1'])

# ============================================
# INSTALLED APPS
# ============================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',  # Only once!
    'phonenumber_field',
    'anymail',
    'django_filters',
    'whitenoise.runserver_nostatic',  # For static files in production
    
    # Cloudinary
    'cloudinary',
    'cloudinary_storage',
    
    # Local apps
    'apps.accounts',
    'apps.admin_dashboard',
    'apps.hostels',          
    'apps.bookings',         
    'apps.notifications', 
    'apps.roommate',
    'apps.subscriptions',
    'apps.chat',  
    'apps.reviews',
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # Must be FIRST
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.RateLimitMiddleware',
    'apps.accounts.middleware.SingleSessionMiddleware',
    'apps.accounts.middleware.IPWhitelistMiddleware',
    'apps.accounts.middleware.AdminActivityMiddleware',
    'apps.accounts.middleware.MaintenanceModeMiddleware', 
]

ROOT_URLCONF = 'core.urls'

# ============================================
# TEMPLATES
# ============================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# ============================================
# DATABASE - Use DATABASE_URL for production
# ============================================
# Try to use DATABASE_URL from environment (Render/Supabase)
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    # Production database (Supabase, Render PostgreSQL, etc.)
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('DATABASE_URL'),
            conn_max_age=600,
            ssl_require=True
        )
    }
else:
    # Local development database
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'kirinyaga_hostels'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
            'OPTIONS': {
                'sslmode': 'require' if not DEBUG else 'disable',
                'connect_timeout': 30,
            },
            'CONN_MAX_AGE': 60,
        }
    }

# ============================================
# FREE TIER CONFIGURATION
# ============================================
FREE_TIER_ENABLED = os.getenv('FREE_TIER_ENABLED', 'True') == 'True'
FREE_TIER_LIMITS = {
    'max_hostels': 999999,
    'max_images_per_hostel': 999999,
    'can_feature_listings': True,
    'has_priority_support': True,
    'has_analytics': True,
    'has_api_access': True,
}

# ============================================
# AUTHENTICATION
# ============================================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8}
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

AUTH_USER_MODEL = 'accounts.User'

# ============================================
# REST FRAMEWORK
# ============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/day',
        'user': '1000/day'
    },
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend'
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FormParser',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
}

# ============================================
# JWT SETTINGS
# ============================================
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
}

# ============================================
# CORS SETTINGS - FIXED VERSION
# ============================================
# Start with hardcoded defaults
CORS_ALLOWED_ORIGINS = [
    'https://kirinyaga-hostels-frontend.onrender.com',
    'http://localhost:5500',
    'http://127.0.0.1:5500',
    'https://student.kirinyagahostels.com',
    'https://owner.kirinyagahostels.com',
    'https://admin.kirinyagahostels.com',
    'https://kyu-hostels.destinymichael941.workers.dev',
]

# Add frontend Render URL
CORS_ALLOWED_ORIGINS.append('https://kirinyaga-hostels-frontend.onrender.com')

# Add from environment variable (if set)
env_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
if env_origins:
    for origin in env_origins.split(','):
        origin = origin.strip().rstrip('/')
        if origin and origin not in CORS_ALLOWED_ORIGINS:
            CORS_ALLOWED_ORIGINS.append(origin)

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with',
]

# Print CORS settings for debugging (will appear in Render logs)
print(f"🌐 CORS_ALLOWED_ORIGINS: {CORS_ALLOWED_ORIGINS}")

CSRF_TRUSTED_ORIGINS = [origin.rstrip('/') for origin in CORS_ALLOWED_ORIGINS]
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'

SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ============================================
# EMAIL CONFIGURATION
# ============================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', f'Kirinyaga Hostels <{EMAIL_HOST_USER}>')

# Use console backend in development if no credentials
if not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
    DEFAULT_FROM_EMAIL = 'noreply@kirinyagahostels.com'
    print("⚠️ Email credentials not set. Using console backend.")

print(f"📧 EMAIL BACKEND: {EMAIL_BACKEND}")
print(f"📧 EMAIL HOST: {EMAIL_HOST}")
print(f"📧 EMAIL USER: {EMAIL_HOST_USER}")

ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'admin@kirinyagahostels.com')
EMAIL_USE_LOCALTIME = True
EMAIL_TIMEOUT = 30
EMAIL_MULTIPART = True

# ============================================
# GOOGLE MAPS
# ============================================
GOOGLE_MAPS_API_KEY = os.getenv('GOOGLE_MAPS_API_KEY', '')

# ============================================
# FRONTEND URLs
# ============================================
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5500')
STUDENT_URL = os.getenv('STUDENT_URL', f'{FRONTEND_URL}/student')
OWNER_URL = os.getenv('OWNER_URL', f'{FRONTEND_URL}/owner')
ADMIN_URL = os.getenv('ADMIN_URL', f'{FRONTEND_URL}/admin')

# ============================================
# INTERNATIONALIZATION
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# ============================================
# STATIC & MEDIA FILES
# ============================================
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ============================================
# PHONE NUMBER SETTINGS
# ============================================
PHONENUMBER_DEFAULT_REGION = 'KE'
PHONENUMBER_DEFAULT_FORMAT = 'E164'

# ============================================
# AUTHENTICATION BACKENDS
# ============================================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

# ============================================
# PASSWORD HASHERS
# ============================================
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

# ============================================
# FILE UPLOAD SETTINGS
# ============================================
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_PERMISSIONS = 0o644

# ============================================
# LOGGING CONFIGURATION
# ============================================
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(LOGS_DIR, 'error.log'),
            'formatter': 'verbose',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ============================================
# SECURITY SETTINGS FOR PRODUCTION
# ============================================
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# ============================================
# TWILIO SMS CONFIGURATION
# ============================================
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# ============================================
# CLOUDINARY CONFIGURATION
# ============================================
import cloudinary
import cloudinary.uploader
import cloudinary.api

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
)

DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'

# ============================================
# SUPABASE STORAGE (Fallback)
# ============================================
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
SUPABASE_STORAGE_BUCKET = os.getenv('SUPABASE_STORAGE_BUCKET', 'hostel-images')

# ============================================
# IP WHITELIST FOR ADMIN
# ============================================
ADMIN_ALLOWED_IPS = os.getenv('ADMIN_ALLOWED_IPS', '').split(',')
ADMIN_ALLOWED_IPS = [ip.strip() for ip in ADMIN_ALLOWED_IPS if ip.strip()]

# In development, allow all
if DEBUG:
    ADMIN_ALLOWED_IPS = []
    print(f"🔒 Admin IP Whitelist: ALLOW ALL (development mode)")
else:
    print(f"🔒 Admin IP Whitelist: {ADMIN_ALLOWED_IPS if ADMIN_ALLOWED_IPS else 'ALLOW ALL (no restrictions)'}")