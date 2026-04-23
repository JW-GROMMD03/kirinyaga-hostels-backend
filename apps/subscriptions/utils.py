import hashlib
import base64
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone

def generate_password(shortcode, passkey, timestamp):
    """
    Build the encoded password that Safaricom requires for API calls.
    Takes the business shortcode, passkey, and current timestamp,
    combines them into one string, then encodes it in base64 format.
    """
    data_to_encode = shortcode + passkey + timestamp
    encoded = base64.b64encode(data_to_encode.encode())
    return encoded.decode('utf-8')

def get_access_token():
    """
    Request an OAuth token from Safaricom's sandbox.
    This token is needed for all subsequent M-Pesa API requests.
    Returns the access token string if successful, None if something goes wrong.
    """
    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_CONSUMER_SECRET
    
    api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    
    try:
        response = requests.get(api_url, auth=(consumer_key, consumer_secret))
        response.raise_for_status()
        result = response.json()
        return result.get('access_token')
    except Exception as e:
        print(f"Could not fetch M-Pesa access token: {e}")
        return None

def stk_push(phone_number, amount, account_reference, transaction_desc, callback_url):
    """
    Trigger the STK push popup on a customer's phone.
    This is what makes the M-Pesa PIN entry screen appear.
    Returns the response data from Safaricom if successful.
    """
    access_token = get_access_token()
    if not access_token:
        return None
    
    # Build the timestamp that Safaricom expects (YYYYMMDDHHMMSS format)
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(settings.MPESA_SHORTCODE, settings.MPESA_PASSKEY, timestamp)
    
    api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # Clean up the phone number - Safaricom wants 254XXXXXXXXX format
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
        'AccountReference': account_reference[:12],  # Safaricom limits this to 12 characters
        'TransactionDesc': transaction_desc[:13]     # And this to 13 characters
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"STK push didn't go through: {e}")
        return None

def check_transaction_status(checkout_request_id):
    """
    Query Safaricom to find out what happened with a payment.
    Useful for confirming if money was actually sent when the callback fails.
    """
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
        print(f"Could not check transaction status: {e}")
        return None

def check_hostel_creation_eligibility(owner):
    """
    Figure out if this owner is allowed to add another hostel.
    Free users get one hostel per calendar month.
    Paid users are limited by whatever their plan allows.
    """
    from .models import OwnerSubscription
    
    # Count how many hostels they've added since the first of this month
    current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hostels_this_month = owner.hostels.filter(created_at__gte=current_month).count()
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    # SCENARIO 1: They're paying for a subscription
    if subscription and not subscription.is_expired():
        if subscription.plan.name == 'free':
            # Even if they have a "free" subscription record, enforce the monthly limit
            if hostels_this_month >= 1:
                return False, "You've already used your free hostel for this month. Upgrade to add more anytime you want."
            return True, "You can add your free hostel for this month."
        else:
            # Paid plan - let the subscription model check its own rules
            can, message = subscription.can_add_hostel()
            return can, message
    
    # SCENARIO 2: Pure free tier (no subscription record at all)
    if hostels_this_month >= 1:
        return False, "You've reached the free tier limit of one hostel per month. Consider upgrading to add more hostels."
    
    return True, "Ready to add your first hostel! You get one free listing per month."

def check_image_upload_eligibility(owner, requested_image_count=1):
    """
    Make sure the owner isn't trying to upload more photos than their plan permits.
    Different subscription tiers allow different numbers of images per hostel.
    """
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    # Everyone gets at least 6 images by default
    max_images_per_hostel = 6
    
    if subscription and not subscription.is_expired():
        max_images_per_hostel = subscription.plan.max_images_per_hostel if subscription.plan else 6
    
    if requested_image_count > max_images_per_hostel:
        plan_name = subscription.plan.display_name if subscription else "Free"
        return False, f"Your {plan_name} plan only allows {max_images_per_hostel} photos per hostel. You tried to upload {requested_image_count}."
    
    return True, ""

def check_analytics_access(owner):
    """
    Only certain paid plans get to see the analytics dashboard.
    Check if this owner's subscription includes that perk.
    """
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None
    
    if not subscription or subscription.is_expired():
        return False, "Analytics are a premium feature. You'll need an active subscription to view them."
    
    if not subscription.plan.analytics_access:
        return False, f"Your {subscription.plan.display_name} plan doesn't include analytics. The Premium and Enterprise plans do."
    
    return True, ""

def extract_bonus_reason(subscription):
    """
    Pull out the reason why a bonus was given, if there is one.
    The admin notes field stores this in a specific format: "Bonus: X weeks - Reason"
    """
    if not subscription:
        return None
    if subscription.is_bonus and subscription.admin_notes:
        # The note should be formatted like "Bonus: 4 weeks - Referral program reward"
        if ' - ' in subscription.admin_notes:
            return subscription.admin_notes.split(' - ', 1)[1]
        return subscription.admin_notes
    return None

def get_owner_subscription_status(owner):
    """
    Build a complete picture of where this owner stands with their subscription.
    Returns everything the frontend needs to show limits, remaining days, and features.
    """
    from .models import OwnerSubscription
    
    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
        
        # See if there's a reason attached to any bonus weeks they received
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
            'is_bonus': subscription.is_bonus if subscription else False,
            'bonus_weeks': subscription.bonus_weeks if subscription else None,
            'bonus_reason': bonus_reason,
            'payment_method': subscription.payment_method if subscription else None,
            'auto_renew': subscription.auto_renew if subscription else False,
            'start_date': subscription.start_date if subscription else None,
        }
    except OwnerSubscription.DoesNotExist:
        # This owner is on the basic free tier - no paid subscription at all
        current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        hostels_this_month = owner.hostels.filter(created_at__gte=current_month).count()
        
        return {
            'has_active_subscription': False,
            'plan': 'free',
            'plan_display': 'Free',
            'expires_at': None,
            'days_remaining': None,
            'max_hostels': 1,  # One hostel per month is the free offering
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