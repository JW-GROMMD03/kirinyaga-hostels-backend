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
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    # Check free tier monthly limit
    current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hostels_this_month = owner.hostels.filter(created_at__gte=current_month).count()
    
    if subscription and subscription.plan.name == 'free':
        if hostels_this_month >= 1:
            return False, "You have reached your free tier limit of 1 hostel per month. Please subscribe to add more hostels."
    
    if not subscription or not subscription.is_active or subscription.is_expired():
        if hostels_this_month >= 1:
            return False, "Your free trial has expired. Please subscribe to continue adding hostels."
        return True, "You can add your first hostel for free this month."
    
    # Check subscription limits
    can, message = subscription.can_add_hostel()
    return can, message

def get_owner_subscription_status(owner):
    """Get current subscription status for owner"""
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
        return {
            'has_active_subscription': not subscription.is_expired(),
            'plan': subscription.plan.name if subscription.plan else 'free',
            'plan_display': subscription.plan.display_name if subscription.plan else 'Free',
            'expires_at': subscription.end_date,
            'days_remaining': subscription.days_remaining(),
            'max_hostels': subscription.plan.max_hostels if subscription.plan else 1,
            'current_hostels': owner.hostels.count(),
            'can_add_hostel': subscription.can_add_hostel()[0],
            'can_feature': subscription.plan.can_feature_listings if subscription.plan else False,
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
            'current_hostels': owner.hostels.count(),
            'can_add_hostel': hostels_this_month < 1,
            'can_feature': False,
        }