import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import OwnerSubscription, SubscriptionPlan, PaymentTransaction, SubscriptionLog
from .utils import stk_push, check_transaction_status
from django.conf import settings

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
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Transaction not found'})
        
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
            
            # Activate subscription
            subscription = transaction.subscription
            subscription.payment_status = 'completed'
            subscription.payment_reference = mpesa_receipt
            subscription.mpesa_receipt_number = mpesa_receipt
            subscription.amount_paid = amount
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
            
            logger.info(f"Subscription activated for {subscription.owner.email}")
            
        else:  # Failed
            transaction.status = 'failed'
            transaction.response_description = result_desc
            transaction.save()
            
            subscription = transaction.subscription
            subscription.payment_status = 'failed'
            subscription.save()
            
            logger.error(f"Payment failed for {subscription.owner.email}: {result_desc}")
        
        return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})
        
    except Exception as e:
        logger.error(f"Error processing M-Pesa callback: {e}")
        return JsonResponse({'ResultCode': 1, 'ResultDesc': str(e)})


def initiate_mpesa_payment(owner, plan, phone_number):
    """Initiate M-Pesa payment for subscription"""
    from .models import PaymentTransaction
    
    # Generate unique transaction ID
    import uuid
    transaction_id = str(uuid.uuid4())
    
    # Create transaction record
    transaction = PaymentTransaction.objects.create(
        subscription=None,  # Will be updated after subscription creation
        amount=float(plan.price_kes),
        payment_method='mpesa',
        transaction_id=transaction_id,
        phone_number=phone_number,
        status='pending'
    )
    
    # Create callback URL
    callback_url = f"{settings.MPESA_CALLBACK_URL}/api/subscriptions/mpesa/callback/"
    
    # Initiate STK Push
    result = stk_push(
        phone_number=phone_number,
        amount=int(plan.price_kes),
        account_reference=transaction_id[:12],
        transaction_desc=f"Subs: {plan.display_name}",
        callback_url=callback_url
    )
    
    if result and result.get('ResponseCode') == '0':
        checkout_request_id = result.get('CheckoutRequestID')
        transaction.transaction_id = checkout_request_id
        transaction.save()
        
        return {
            'success': True,
            'checkout_request_id': checkout_request_id,
            'message': 'STK Push sent. Please check your phone and enter PIN.'
        }
    else:
        transaction.status = 'failed'
        transaction.save()
        return {
            'success': False,
            'message': result.get('ResponseDescription', 'Payment initiation failed') if result else 'Payment service unavailable'
        }