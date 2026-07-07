import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from .models import OwnerSubscription, PaymentTransaction, SubscriptionLog
from .utils import stk_push, check_transaction_status

logger = logging.getLogger(__name__)

# Safaricom's official callback IPs - only these can hit our callback endpoint
SAFARICOM_IPS = [
    '196.201.214.200', '196.201.214.206', '196.201.214.207',
    '196.201.214.208', '196.201.214.209', '196.201.213.114',
    '196.201.213.44', '196.201.212.127', '196.201.212.128',
    '196.201.212.129', '196.201.212.130', '196.201.212.131',
    '196.201.212.132', '196.201.212.133', '196.201.212.134',
    '196.201.212.135', '196.201.212.136', '196.201.212.138',
    '196.201.212.74', '196.201.212.69', '196.201.212.75',
    '196.201.212.76', '196.201.212.77', '196.201.212.78',
]


def verify_safaricom_ip(request):
    """
    Only accept callbacks from known Safaricom IP addresses.
    Stops random people from faking payment confirmations.
    In sandbox mode, we skip this since callbacks come from your own server.
    """
    if settings.MPESA_ENVIRONMENT == 'sandbox':
        return True

    client_ip = request.META.get('REMOTE_ADDR', '')
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')

    if x_forwarded:
        client_ip = x_forwarded.split(',')[0].strip()

    if client_ip in SAFARICOM_IPS:
        return True

    logger.warning(f"Callback from untrusted IP: {client_ip}")
    return False


@csrf_exempt
@require_http_methods(['POST'])
def mpesa_callback(request):
    """
    Safaricom calls this endpoint after a customer completes or cancels
    the STK push on their phone. We verify the IP, check for duplicates,
    and either activate or fail the subscription.
    """
    if not verify_safaricom_ip(request):
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Untrusted source'})

    try:
        data = json.loads(request.body)
        logger.info(f"M-Pesa Callback: {json.dumps(data, indent=2)}")

        body = data.get('Body', {})
        stk_callback = body.get('stkCallback', {})

        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc', '')
        checkout_request_id = stk_callback.get('CheckoutRequestID')

        if not checkout_request_id:
            logger.error("Callback missing CheckoutRequestID")
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Missing CheckoutRequestID'})

        try:
            transaction_obj = PaymentTransaction.objects.select_related(
                'subscription', 'subscription__owner', 'subscription__plan'
            ).get(transaction_id=checkout_request_id)
        except PaymentTransaction.DoesNotExist:
            logger.error(f"No transaction found for {checkout_request_id}")
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Not found, acknowledged'})

        # Don't process the same transaction twice
        if transaction_obj.status in ('completed', 'failed'):
            logger.info(f"Transaction {checkout_request_id} already processed as {transaction_obj.status}")
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Already processed'})

        subscription = transaction_obj.subscription

        if result_code == 0:
            # Payment successful
            callback_metadata = stk_callback.get('CallbackMetadata', {})
            items = callback_metadata.get('Item', [])

            mpesa_receipt = ''
            amount_paid = 0
            phone_number = ''

            for item in items:
                name = item.get('Name', '')
                value = item.get('Value', '')
                if name == 'MpesaReceiptNumber':
                    mpesa_receipt = value
                elif name == 'Amount':
                    amount_paid = float(value) if value else 0
                elif name == 'PhoneNumber':
                    phone_number = value

            logger.info(f"Payment confirmed - Receipt: {mpesa_receipt}, Amount: {amount_paid}")

            transaction_obj.status = 'completed'
            transaction_obj.mpesa_receipt = mpesa_receipt
            transaction_obj.response_description = result_desc
            transaction_obj.completed_at = timezone.now()
            transaction_obj.save()

            from django.db import transaction
            with transaction.atomic():
                OwnerSubscription.objects.filter(
                    owner=subscription.owner, is_active=True
                ).update(is_active=False)

                subscription.payment_status = 'completed'
                subscription.payment_reference = mpesa_receipt
                subscription.mpesa_receipt_number = mpesa_receipt
                subscription.amount_paid = amount_paid or transaction_obj.amount
                subscription.is_active = True
                subscription.start_date = timezone.now()
                if subscription.plan:
                    subscription.end_date = timezone.now() + timezone.timedelta(
                        days=subscription.plan.duration_days
                    )
                subscription.save()

            SubscriptionLog.objects.create(
                subscription=subscription,
                action='activated',
                details={'mpesa_receipt': mpesa_receipt, 'amount': amount_paid, 'phone': phone_number},
                performed_by=subscription.owner
            )

            logger.info(f"Subscription activated for {subscription.owner.email}")

        else:
            logger.warning(f"Payment failed: {result_desc}")

            transaction_obj.status = 'failed'
            transaction_obj.response_description = result_desc
            transaction_obj.save()

            subscription.payment_status = 'failed'
            subscription.save()

            SubscriptionLog.objects.create(
                subscription=subscription,
                action='payment_failed',
                details={'result_code': result_code, 'result_desc': result_desc},
                performed_by=subscription.owner
            )

        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Processed'})

    except json.JSONDecodeError:
        logger.error("Invalid JSON in callback")
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Invalid data, acknowledged'})
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Error, acknowledged'})


def initiate_mpesa_payment(owner, plan, phone_number):
    """
    Kick off the M-Pesa payment flow. Formats the phone, calls Safaricom,
    and returns the result so the frontend can show the user what's happening.
    """
    import uuid

    clean_phone = phone_number.strip().replace(' ', '')
    if clean_phone.startswith('+'):
        clean_phone = clean_phone[1:]
    if clean_phone.startswith('0'):
        clean_phone = '254' + clean_phone[1:]
    if not clean_phone.startswith('254'):
        clean_phone = '254' + clean_phone

    callback_url = getattr(
        settings, 'MPESA_CALLBACK_URL',
        'https://kirinyaga-hostels-backend.onrender.com/api/subscriptions/mpesa/callback/'
    )

    logger.info(f"Initiating M-Pesa: phone={clean_phone}, amount={plan.price_kes}, till={settings.MPESA_SHORTCODE}")

    result = stk_push(
        phone_number=clean_phone,
        amount=int(plan.price_kes),
        account_reference=f"KHS-{str(owner.id)[:8]}",
        transaction_desc=f"{plan.display_name[:13]}",
        callback_url=callback_url
    )

    if result and str(result.get('ResponseCode', '')) == '0':
        checkout_id = result.get('CheckoutRequestID', str(uuid.uuid4()))
        return {
            'success': True,
            'checkout_request_id': checkout_id,
            'merchant_request_id': result.get('MerchantRequestID', ''),
            'message': 'STK push sent. Check your phone and enter your PIN.'
        }
    else:
        error_msg = result.get('ResponseDescription', result.get('errorMessage', 'Payment could not be started'))
        if not error_msg and result:
            error_msg = str(result)
        logger.error(f"Payment initiation failed: {error_msg}")
        return {
            'success': False,
            'message': error_msg
        }


def process_mpesa_callback(callback_data):
    """
    Placeholder for processing callback data.
    The actual logic is in the mpesa_callback view above.
    """
    return callback_data
