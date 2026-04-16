import hashlib
import base64
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone

def generate_password(shortcode, passkey, timestamp):
    """Generate M-Pesa API password"""
    data_to_encode = shortcode + passkey + timestamp
    encoded = base64.b64encode(data_to_encode.encode())
    return encoded.decode('utf-8')

def get_access_token():
    """Get M-Pesa access token"""
    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_CONSUMER_SECRET
    
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    
    try:
        response = requests.get(api_url, auth=(consumer_key, consumer_secret))
        response.raise_for_status()
        result = response.json()
        return result.get('access_token')
    except Exception as e:
        print(f"Error getting access token: {e}")
        return None

def stk_push(phone_number, amount, account_reference, transaction_desc, callback_url):
    """Initiate M-Pesa STK Push"""
    access_token = get_access_token()
    if not access_token:
        return None
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(settings.MPESA_SHORTCODE, settings.MPESA_PASSKEY, timestamp)
    
    api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Format phone number (remove 0 or +254, add 254)
    if phone_number.startswith('0'):
        phone_number = '254' + phone_number[1:]
    elif phone_number.startswith('+'):
        phone_number = phone_number[1:]
    
    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone_number,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': phone_number,
        'CallBackURL': callback_url,
        'AccountReference': account_reference[:12],
        'TransactionDesc': transaction_desc[:13]
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error in STK push: {e}")
        return None

def check_transaction_status(checkout_request_id):
    """Check M-Pesa transaction status"""
    access_token = get_access_token()
    if not access_token:
        return None
    
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(settings.MPESA_SHORTCODE, settings.MPESA_PASSKEY, timestamp)
    
    api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery/v1/query"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'CheckoutRequestID': checkout_request_id
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error checking transaction status: {e}")
        return None

def check_hostel_creation_eligibility(owner):
    """Check if owner can create a new hostel"""
    from .models import OwnerSubscription
    
    # Get current month's hostels
    current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hostels_this_month = owner.hostels.filter(created_at__gte=current_month).count()
    total_hostels = owner.hostels.count()
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    # CASE 1: User has an active paid subscription
    if subscription and not subscription.is_expired():
        if subscription.plan.name == 'free':
            # Free plan: 1 hostel per month
            if hostels_this_month >= 1:
                return False, "You have reached your free tier limit of 1 hostel per month. Please subscribe to add more hostels."
            return True, "You can add 1 hostel this month on the free plan."
        else:
            # Paid plan: check plan limits
            can, message = subscription.can_add_hostel()
            return can, message
    
    #  CASE 2: No active subscription (true free tier)
    if hostels_this_month >= 1:
        return False, "You have reached the free tier limit of 1 hostel per month. Subscribe to add more."
    
    return True, "You can add your first hostel for free this month."

def check_image_upload_eligibility(owner, requested_image_count=1):
    """Check if owner can upload images for a hostel"""
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    # Default max images per hostel is 6
    max_images_per_hostel = 6
    
    if subscription and not subscription.is_expired():
        max_images_per_hostel = subscription.plan.max_images_per_hostel if subscription.plan else 6
    
    if requested_image_count > max_images_per_hostel:
        return False, f"You can only upload up to {max_images_per_hostel} images per hostel. Your {subscription.plan.display_name if subscription else 'Free'} plan allows {max_images_per_hostel} images."
    
    return True, ""

def check_analytics_access(owner):
    """Check if owner has access to analytics features"""
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    if not subscription or subscription.is_expired():
        return False, "Analytics access requires an active subscription. Please subscribe to view analytics."
    
    if not subscription.plan.analytics_access:
        return False, f"Your {subscription.plan.display_name} plan does not include analytics access. Upgrade to Premium or Enterprise to access analytics."
    
    return True, ""

def extract_bonus_reason(subscription):
    """Extract the bonus reason from admin_notes"""
    if not subscription:
        return None
    if subscription.is_bonus and subscription.admin_notes:
        # Format: "Bonus: X weeks - Reason here"
        if ' - ' in subscription.admin_notes:
            return subscription.admin_notes.split(' - ', 1)[1]
        return subscription.admin_notes
    return None

def get_owner_subscription_status(owner):
    """Get current subscription status for owner"""
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
        
        # ✅ Extract bonus reason
        bonus_reason = extract_bonus_reason(subscription)
        
        return {
            'has_active_subscription': not subscription.is_expired(),
            'plan': subscription.plan.name if subscription.plan else 'free',
            'plan_display': subscription.plan.display_name if subscription.plan else 'Free',
            'expires_at': subscription.end_date,
            'days_remaining': subscription.days_remaining(),
            'max_hostels': subscription.plan.max_hostels if subscription.plan else 1,
            'max_images_per_hostel': subscription.plan.max_images_per_hostel if subscription.plan else 6,
            'current_hostels': owner.hostels.count(),
            'can_add_hostel': check_hostel_creation_eligibility(owner)[0],
            'can_feature': subscription.plan.can_feature_listings if subscription.plan else False,
            'has_analytics_access': subscription.plan.analytics_access if subscription.plan else False,
            # ✅ ADDED BONUS FIELDS
            'is_bonus': subscription.is_bonus if subscription else False,
            'bonus_weeks': subscription.bonus_weeks if subscription else None,
            'bonus_reason': bonus_reason,
            'payment_method': subscription.payment_method if subscription else None,
            'auto_renew': subscription.auto_renew if subscription else False,
            'start_date': subscription.start_date if subscription else None,
        }
    except OwnerSubscription.DoesNotExist:
        # Free tier
        current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        hostels_this_month = owner.hostels.filter(created_at__gte=current_month).count()
        
        return {
            'has_active_subscription': False,
            'plan': 'free',
            'plan_display': 'Free',
            'expires_at': None,
            'days_remaining': None,
            'max_hostels': 1,
            'max_images_per_hostel': 6,
            'current_hostels': owner.hostels.count(),
            'can_add_hostel': hostels_this_month < 1,
            'can_feature': False,
            'has_analytics_access': False,
            'is_bonus': False,
            'bonus_weeks': None,
            'bonus_reason': None,
            'payment_method': None,
            'auto_renew': False,
            'start_date': None,
        }