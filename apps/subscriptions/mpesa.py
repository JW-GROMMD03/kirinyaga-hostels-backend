import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from .models import OwnerSubscription, SubscriptionPlan, PaymentTransaction, SubscriptionLog
from .utils import stk_push, check_transaction_status

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
def mpesa_callback(request):
    """Handle M-Pesa STK Push callback"""
    try:
        data = json.loads(request.body)
        logger.info(f"M-Pesa Callback Received: {data}")
        
        body = data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        
        # Find transaction
        try:
            transaction = PaymentTransaction.objects.get(transaction_id=checkout_request_id)
        except PaymentTransaction.DoesNotExist:
            logger.error(f"Transaction not found: {checkout_request_id}")
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Transaction not found, but acknowledged'})
        
        if result_code == 0:  # Success
            # Get callback metadata
            callback_metadata = stk_callback.get('CallbackMetadata', {})
            items = callback_metadata.get('Item', [])
            
            mpesa_receipt = None
            amount = None
            phone_number = None
            
            for item in items:
                if item.get('Name') == 'MpesaReceiptNumber':
                    mpesa_receipt = item.get('Value')
                elif item.get('Name') == 'Amount':
                    amount = item.get('Value')
                elif item.get('Name') == 'PhoneNumber':
                    phone_number = item.get('Value')
            
            # Update transaction
            transaction.status = 'completed'
            transaction.mpesa_receipt = mpesa_receipt
            transaction.completed_at = timezone.now()
            transaction.response_description = result_desc
            transaction.save()
            
            # Get the subscription from the transaction
            subscription = transaction.subscription
            if subscription:
                # Deactivate any existing active subscriptions for this owner
                OwnerSubscription.objects.filter(
                    owner=subscription.owner,
                    is_active=True
                ).update(is_active=False)
                
                # Activate this subscription
                subscription.payment_status = 'completed'
                subscription.payment_reference = mpesa_receipt
                subscription.mpesa_receipt_number = mpesa_receipt
                subscription.amount_paid = amount or transaction.amount
                subscription.is_active = True
                subscription.start_date = timezone.now()
                
                # Set end date based on plan duration
                if subscription.plan:
                    subscription.end_date = timezone.now() + timezone.timedelta(days=subscription.plan.duration_days)
                
                subscription.save()
                
                # Log the activation
                SubscriptionLog.objects.create(
                    subscription=subscription,
                    action='activated',
                    details={'mpesa_receipt': mpesa_receipt, 'amount': amount},
                    performed_by=subscription.owner
                )
                
                logger.info(f"✅ Subscription activated for {subscription.owner.email}")
            else:
                logger.error(f"No subscription found for transaction: {checkout_request_id}")
            
        else:  # Failed
            transaction.status = 'failed'
            transaction.response_description = result_desc
            transaction.save()
            
            subscription = transaction.subscription
            if subscription:
                subscription.payment_status = 'failed'
                subscription.save()
                
                logger.error(f"❌ Payment failed for {subscription.owner.email}: {result_desc}")
        
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})
        
    except Exception as e:
        logger.error(f"Error processing M-Pesa callback: {e}")
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Error but acknowledged'})


def initiate_mpesa_payment(owner, plan, phone_number):
    """Initiate M-Pesa payment for subscription"""
    import uuid
    
    # Format phone number
    formatted_phone = phone_number
    if formatted_phone.startswith('0'):
        formatted_phone = '254' + formatted_phone[1:]
    elif formatted_phone.startswith('+'):
        formatted_phone = formatted_phone[1:]
    
    # Generate unique transaction ID (fallback if STK push doesn't return one)
    fallback_checkout_id = str(uuid.uuid4())
    
    # ✅ FIXED: Use the callback URL directly from settings - DO NOT APPEND ANYTHING
    callback_url = getattr(settings, 'MPESA_CALLBACK_URL', 'https://kirinyaga-hostels-backend.onrender.com/api/subscriptions/mpesa/callback/')
    
    logger.info(f"📱 Initiating M-Pesa payment: phone={formatted_phone}, amount={plan.price_kes}, callback={callback_url}")
    
    # Initiate STK Push
    result = stk_push(
        phone_number=formatted_phone,
        amount=int(plan.price_kes),
        account_reference=f"SUB{owner.id}"[:12],
        transaction_desc=f"Subs:{plan.display_name[:13]}",
        callback_url=callback_url
    )
    
    if result and result.get('ResponseCode') == '0':
        actual_checkout_id = result.get('CheckoutRequestID', fallback_checkout_id)
        
        return {
            'success': True,
            'checkout_request_id': actual_checkout_id,
            'merchant_request_id': result.get('MerchantRequestID', ''),
            'message': 'STK Push sent. Please check your phone and enter PIN.'
        }
    else:
        error_msg = result.get('ResponseDescription', 'Payment initiation failed') if result else 'Payment service unavailable'
        logger.error(f"❌ M-Pesa payment failed: {error_msg}")
        return {
            'success': False,
            'message': error_msg
        }


def process_mpesa_callback(callback_data):
    """
    Process M-Pesa callback data.
    This is a placeholder - the actual processing happens in the view.
    """
    return callback_data