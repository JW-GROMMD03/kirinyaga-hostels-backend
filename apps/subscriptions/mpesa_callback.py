import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from .models import OwnerSubscription, PaymentTransaction, SubscriptionLog
from apps.accounts.models import AuditLog

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['POST'])
def mpesa_callback(request):
    """
    Handle M-Pesa STK Push callback from Safaricom
    This endpoint is called by Safaricom after user completes payment
    """
    try:
        # Parse the callback data
        data = json.loads(request.body)
        logger.info(f"M-Pesa Callback received: {data}")
        
        # Extract callback data
        body = data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        
        result_code = stk_callback.get('ResultCode')
        result_desc = stk_callback.get('ResultDesc')
        checkout_request_id = stk_callback.get('CheckoutRequestID')
        merchant_request_id = stk_callback.get('MerchantRequestID')
        
        logger.info(f"Result Code: {result_code}, Result Desc: {result_desc}")
        logger.info(f"CheckoutRequestID: {checkout_request_id}")
        
        # Find the transaction
        try:
            transaction = PaymentTransaction.objects.get(transaction_id=checkout_request_id)
        except PaymentTransaction.DoesNotExist:
            logger.error(f"Transaction not found for CheckoutRequestID: {checkout_request_id}")
            return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Transaction not found'})
        
        if result_code == 0:  # Payment successful
            # Extract callback metadata
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
            
            # Get the subscription
            subscription = transaction.subscription
            
            if subscription:
                # Activate the subscription
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
                
                # Create log entry
                SubscriptionLog.objects.create(
                    subscription=subscription,
                    action='activated',
                    details={
                        'mpesa_receipt': mpesa_receipt,
                        'amount': amount,
                        'checkout_request_id': checkout_request_id
                    },
                    performed_by=subscription.owner
                )
                
                # Create audit log
                AuditLog.objects.create(
                    user=subscription.owner,
                    action='SUBSCRIPTION_ACTIVATED',
                    ip_address='0.0.0.0',  # Callback has no request
                    user_agent='M-Pesa Callback',
                    details={
                        'plan': subscription.plan.display_name if subscription.plan else 'Unknown',
                        'amount': amount,
                        'receipt': mpesa_receipt
                    }
                )
                
                logger.info(f"Subscription activated for {subscription.owner.email}")
            
            return JsonResponse({'ResultCode': 0, 'ResultDesc': 'Success'})
            
        else:  # Payment failed
            # Update transaction as failed
            transaction.status = 'failed'
            transaction.response_description = result_desc
            transaction.save()
            
            # Update subscription if exists
            subscription = transaction.subscription
            if subscription:
                subscription.payment_status = 'failed'
                subscription.save()
                
                # Create log entry
                SubscriptionLog.objects.create(
                    subscription=subscription,
                    action='cancelled',
                    details={
                        'reason': result_desc,
                        'result_code': result_code
                    },
                    performed_by=subscription.owner
                )
                
                logger.error(f"Payment failed for {subscription.owner.email}: {result_desc}")
            
            return JsonResponse({'ResultCode': result_code, 'ResultDesc': result_desc})
            
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in callback: {e}")
        return JsonResponse({'ResultCode': 1, 'ResultDesc': 'Invalid JSON'})
        
    except Exception as e:
        logger.error(f"Error processing M-Pesa callback: {e}")
        return JsonResponse({'ResultCode': 1, 'ResultDesc': str(e)})


@csrf_exempt
@require_http_methods(['POST'])
def mpesa_validation(request):
    """
    Validate M-Pesa transaction before processing (C2B)
    """
    try:
        data = json.loads(request.body)
        logger.info(f"M-Pesa Validation received: {data}")
        
        # Always validate successfully
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Validation passed'
        })
        
    except Exception as e:
        logger.error(f"Error in M-Pesa validation: {e}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': str(e)
        })


@csrf_exempt
@require_http_methods(['POST'])
def mpesa_confirmation(request):
    """
    Confirm M-Pesa transaction (C2B)
    """
    try:
        data = json.loads(request.body)
        logger.info(f"M-Pesa Confirmation received: {data}")
        
        # Extract transaction details
        trans_time = data.get('TransTime')
        trans_amount = data.get('TransAmount')
        business_shortcode = data.get('BusinessShortCode')
        bill_ref_number = data.get('BillRefNumber')
        invoice_number = data.get('InvoiceNumber')
        msisdn = data.get('MSISDN')
        
        # Find pending subscription by reference
        if bill_ref_number:
            try:
                subscription = OwnerSubscription.objects.filter(
                    payment_reference=bill_ref_number,
                    payment_status='pending'
                ).first()
                
                if subscription:
                    subscription.payment_status = 'completed'
                    subscription.amount_paid = trans_amount
                    subscription.is_active = True
                    subscription.start_date = timezone.now()
                    if subscription.plan:
                        subscription.end_date = timezone.now() + timezone.timedelta(days=subscription.plan.duration_days)
                    subscription.save()
                    
                    logger.info(f"Subscription activated via C2B for {subscription.owner.email}")
                    
            except OwnerSubscription.DoesNotExist:
                logger.warning(f"No pending subscription found for reference: {bill_ref_number}")
        
        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Confirmation received successfully'
        })
        
    except Exception as e:
        logger.error(f"Error in M-Pesa confirmation: {e}")
        return JsonResponse({
            'ResultCode': 1,
            'ResultDesc': str(e)
        })