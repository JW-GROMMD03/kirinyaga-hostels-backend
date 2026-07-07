import hashlib
import base64
import requests
from datetime import datetime
from django.conf import settings
from django.utils import timezone


def generate_password(shortcode, passkey, timestamp):
    """
    Safaricom needs a base64-encodede from the shortcode, passkey, and timestamp.
    We mash them together and encode them before every API call.
    """
    data_to_encode = shortcode + passkey + timestamp
    encoded = base64.b64encode(data_to_encode.encode())
    return encoded.decode('utf-8')


def get_access_token():
    """
    Grab an OAuth token from Safaricom. Every M-Pesa API call needs one of these.
    Switches between sandbox and production automatically based on your settings.
    """
    consumer_key = settings.MPESA_CONSUMER_KEY
    consumer_secret = settings.MPESA_CONSUMER_SECRET

    if settings.MPESA_ENVIRONMENT == 'production':
        api_url = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    else:
        api_url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

    try:
        response = requests.get(api_url, auth=(consumer_key, consumer_secret), timeout=15)
        response.raise_for_status()
        result = response.json()
        access_token = result.get('access_token')
        if not access_token:
            print("M-Pesa did not return an access token. Check your consumer key and secret.")
        return access_token
    except requests.exceptions.Timeout:
        print("M-Pesa auth request timed out. Safaricom servers might be slow right now.")
        return None
    except requests.exceptions.ConnectionError:
        print("Cannot reach Safaricom servers. Check your internet connection.")
        return None
    except Exception as e:
        print(f"M-Pesa auth error: {e}")
        return None


def stk_push(phone_number, amount, account_reference, transaction_desc, callback_url):
    """
    Sends the STK push to the customer's phone. This is the popup
    that asks them to enter their M-Pesa PIN. Uses till number 9270154.
    """
    access_token = get_access_token()
    if not access_token:
        return {'success': False, 'message': 'Payment service is temporarily unavailable. Try again in a moment.'}

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(settings.MPESA_SHORTCODE, settings.MPESA_PASSKEY, timestamp)

    if settings.MPESA_ENVIRONMENT == 'production':
        api_url = "https://api.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    else:
        api_url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"

    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    # Normalize the phone number to 254XXXXXXXXX
    clean_phone = phone_number.strip().replace(' ', '')
    if clean_phone.startswith('+'):
        clean_phone = clean_phone[1:]
    if clean_phone.startswith('0'):
        clean_phone = '254' + clean_phone[1:]
    if not clean_phone.startswith('254'):
        clean_phone = '254' + clean_phone

    payload = {
        'BusinessShortCode': settings.MPESA_SHORTCODE,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline', # Till number uses this
        'Amount': int(amount),
        'PartyA': clean_phone,
        'PartyB': settings.MPESA_SHORTCODE,
        'PhoneNumber': clean_phone,
        'CallBackURL': callback_url,
        'AccountReference': account_reference[:12],
        'TransactionDesc': transaction_desc[:13]
    }

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        result = response.json()

        response_code = result.get('ResponseCode', '')
        if response_code == '0':
            print(f"STK push sent successfully to {clean_phone}")
        else:
            print(f"STK push rejected by Safaricom: {result.get('ResponseDescription', result)}")

        return result
    except requests.exceptions.Timeout:
        print("STK push timed out. Safaricom might be slow.")
        return {'success': False, 'message': 'M-Pesa is taking too long. Please try again.'}
    except Exception as e:
        print(f"STK push failed: {e}")
        return {'success': False, 'message': 'Could not initiate payment. Try again shortly.'}


def check_transaction_status(checkout_request_id):
    """
    Ask Safaricom what happened with a specific transaction.
    Handy when the callback doesn't arrive or you want to double-check.
    """
    access_token = get_access_token()
    if not access_token:
        return None

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(settings.MPESA_SHORTCODE, settings.MPESA_PASSKEY, timestamp)

    if settings.MPESA_ENVIRONMENT == 'production':
        api_url = "https://api.safaricom.co.ke/mpesa/stkpushquery/v1/query"
    else:
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
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Status check failed: {e}")
        return None


def check_hostel_creation_eligibility(owner):
    """
    Can this owner add another hostel? Free tier gets one per month.
    Paid users get whatever their plan allows.
    """
    from .models import OwnerSubscription

    current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    hostels_this_month = owner.hostels.filter(created_at__gte=current_month).count()

    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None

    if subscription and not subscription.is_expired():
        if subscription.plan.name == 'free':
            if hostels_this_month >= 1:
                return False, "You've already used your free hostel this month. Upgrade to add more anytime."
            return True, "You can add your free hostel for this month."
        else:
            can, message = subscription.can_add_hostel()
            return can, message

    if hostels_this_month >= 1:
        return False, "You've hit the free tier limit of one hostel per month. Consider upgrading."

    return True, "Ready to add your first hostel! You get one free listing per month."


def check_image_upload_eligibility(owner, requested_image_count=1):
    """
    Makes sure the owner isn't trying to upload more photos than their plan allows.
    """
    from .models import OwnerSubscription

    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None

    max_images_per_hostel = 6

    if subscription and not subscription.is_expired():
        max_images_per_hostel = subscription.plan.max_images_per_hostel if subscription.plan else 6

    if requested_image_count > max_images_per_hostel:
        plan_name = subscription.plan.display_name if subscription else "Free"
        return False, f"Your {plan_name} plan allows {max_images_per_hostel} photos per hostel. You tried uploading {requested_image_count}."

    return True, ""


def check_analytics_access(owner):
    """
    Analytics are a premium feature. Not all plans include them.
    """
    from .models import OwnerSubscription

    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
    except OwnerSubscription.DoesNotExist:
        subscription = None

    if not subscription or subscription.is_expired():
        return False, "Analytics need an active subscription."

    if not subscription.plan.analytics_access:
        return False, f"Your {subscription.plan.display_name} plan doesn't include analytics. Upgrade to Premium or Enterprise."

    return True, ""


def extract_bonus_reason(subscription):
    """
    Admins can grant bonus weeks with a reason. This pulls that reason out
    from the admin_notes field. Format is "Bonus: X weeks - Reason here"
    """
    if not subscription:
        return None
    if subscription.is_bonus and subscription.admin_notes:
        if ' - ' in subscription.admin_notes:
            return subscription.admin_notes.split(' - ', 1)[1]
        return subscription.admin_notes
    return None


def get_owner_subscription_status(owner):
    """
    Gives a full picture of the owner's subscription - limits, days left, features.
    Everything the frontend dashboard needs in one call.
    """
    from .models import OwnerSubscription

    try:
        subscription = OwnerSubscription.objects.filter(owner=owner, is_active=True).latest('created_at')
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
