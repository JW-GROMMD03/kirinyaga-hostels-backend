import os
import logging
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from .models import Notification
from .serializers import NotificationSerializer
from twilio.rest import Client

# Set up logging
logger = logging.getLogger(__name__)

User = get_user_model()


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


class MarkNotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            notification = Notification.objects.get(id=pk, user=request.user)
            notification.is_read = True
            notification.save()
            return Response({'status': 'ok'})
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=404)


class NotificationDeleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        print(f"=== DELETE ATTEMPT ===")
        print(f"User: {request.user.email}")
        print(f"User ID: {request.user.id}")
        print(f"Is Staff: {request.user.is_staff}")
        print(f"Notification ID: {pk}")
        
        try:
            # First check if notification exists at all
            notification_exists = Notification.objects.filter(id=pk).exists()
            print(f"Notification exists in DB: {notification_exists}")
            
            if notification_exists:
                # Check if it belongs to current user
                user_has_notification = Notification.objects.filter(id=pk, user=request.user).exists()
                print(f"Belongs to current user: {user_has_notification}")
            
            # Allow staff/superusers to delete any notification
            if request.user.is_staff or request.user.is_superuser:
                print("Staff user - attempting to delete")
                notification = Notification.objects.get(id=pk)
            else:
                print("Regular user - can only delete own notifications")
                notification = Notification.objects.get(id=pk, user=request.user)
            
            notification.delete()
            print("=== DELETE SUCCESS ===")
            return Response({'status': 'deleted'}, status=204)
            
        except Notification.DoesNotExist as e:
            print(f"=== DELETE FAILED: {e} ===")
            return Response({'error': 'Notification not found'}, status=404)


class SendBulkNotificationView(APIView):
    """
    View to send real notifications to users via email and/or SMS using Twilio.
    """
    permission_classes = [permissions.IsAuthenticated]

    def send_email_html(self, to_email, subject, message, link=''):
        """Send real HTML email using Django's email system"""
        try:
            print(f"\n📧 Sending notification email to: {to_email}")
            print(f"   Subject: {subject}")
            print(f"   From: {settings.DEFAULT_FROM_EMAIL}")
            print(f"   Email Host: {settings.EMAIL_HOST}")
            print(f"   Email User: {settings.EMAIL_HOST_USER}")
            
            # Create HTML email content
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>{subject}</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        background-color: #f5f5f5;
                        margin: 0;
                        padding: 20px;
                    }}
                    .container {{
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        border-radius: 12px;
                        overflow: hidden;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    }}
                    .header {{
                        background: linear-gradient(135deg, #006747 0%, #00855a 100%);
                        color: white;
                        padding: 30px 20px;
                        text-align: center;
                    }}
                    .header h1 {{
                        margin: 0;
                        font-size: 24px;
                    }}
                    .content {{
                        padding: 30px;
                    }}
                    .message-box {{
                        background: #f9f9f9;
                        border-left: 4px solid #FFD700;
                        padding: 15px 20px;
                        margin: 20px 0;
                        border-radius: 8px;
                    }}
                    .button {{
                        display: inline-block;
                        padding: 12px 30px;
                        background: #006747;
                        color: white;
                        text-decoration: none;
                        border-radius: 50px;
                        margin: 20px 0;
                    }}
                    .footer {{
                        text-align: center;
                        padding: 20px;
                        background: #f8f9fa;
                        font-size: 12px;
                        color: #666;
                        border-top: 1px solid #eee;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🏠 Kirinyaga University Hostels</h1>
                        <p>Official Notification</p>
                    </div>
                    <div class="content">
                        <h2 style="color: #006747;">{subject}</h2>
                        <div class="message-box">
                            <p style="margin: 0;">{message}</p>
                        </div>
                        {f'<a href="{link}" class="button">📌 View Details</a>' if link else ''}
                        <p style="font-size: 12px; color: #666; margin-top: 20px;">
                            <i>This is an automated notification from Kirinyaga University Hostels system.</i>
                        </p>
                    </div>
                    <div class="footer">
                        <p>© 2025 Kirinyaga University Hostels. All rights reserved.</p>
                        <p>Kirinyaga University, P.O. Box 143-10300, Kerugoya, Kenya</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Plain text version
            text_content = f"""
            Kirinyaga University Hostels
            ============================
            
            {subject}
            {'=' * len(subject)}
            
            {message}
            
            {f'View details: {link}' if link else ''}
            
            ---
            This is an automated notification from Kirinyaga University Hostels.
            Please do not reply to this email.
            """
            
            # Create email with HTML and plain text alternatives
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to_email],
                reply_to=[settings.DEFAULT_FROM_EMAIL]
            )
            email.attach_alternative(html_content, "text/html")
            
            # Send the email
            email.send(fail_silently=False)
            
            print(f"✅ Email sent successfully to {to_email}")
            logger.info(f"Email sent to {to_email}")
            return True, "Email sent successfully"
            
        except Exception as e:
            print(f"❌ Failed to send email to {to_email}: {str(e)}")
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False, str(e)

    def send_twilio_sms(self, phone_number, message):
        """Send real SMS using Twilio with trial account handling"""
        try:
            # Check if Twilio credentials are configured
            if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
                print("⚠️ Twilio credentials not configured")
                return False, "Twilio not configured"
            
            # Initialize Twilio client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            # Format phone number for Twilio
            formatted_phone = self.format_phone_number(phone_number)
            
            # Truncate message if too long (Twilio limit is 1600 chars)
            sms_message = message[:160]
            sms_message = f"KyU Hostels: {sms_message}"
            
            # Send SMS
            sms = client.messages.create(
                body=sms_message,
                from_=settings.TWILIO_PHONE_NUMBER,
                to=formatted_phone
            )
            
            print(f"✅ SMS sent to {formatted_phone} (SID: {sms.sid})")
            logger.info(f"SMS sent to {formatted_phone}, SID: {sms.sid}")
            return True, sms.sid
            
        except Exception as e:
            error_msg = str(e)
            if "unverified" in error_msg.lower():
                print(f"⚠️ Trial account: Cannot send SMS to {phone_number} - number not verified")
                return False, "Trial account: Please verify this number in Twilio console"
            print(f"❌ Failed to send SMS to {phone_number}: {error_msg}")
            logger.error(f"Failed to send SMS to {phone_number}: {error_msg}")
            return False, error_msg

    def format_phone_number(self, phone):
        """Format phone number to E.164 format for Twilio"""
        # Remove any non-digit characters
        phone = ''.join(filter(str.isdigit, phone))
        
        # Check if it's a Kenyan number
        if phone.startswith('0'):
            phone = '254' + phone[1:]
        elif phone.startswith('7'):
            phone = '254' + phone
        elif not phone.startswith('254'):
            phone = '254' + phone
        
        return f"+{phone}"

    def post(self, request):
        # Print incoming request for debugging
        print("\n" + "="*60)
        print("📢 SEND NOTIFICATION REQUEST RECEIVED")
        print("="*60)
        print(f"Request data: {request.data}")
        print(f"Request user: {request.user.email}")
        print("="*60)
        
        data = request.data
        title = data.get('title', 'Notification from Kirinyaga Hostels')
        message = data.get('message', '')
        channel = data.get('channel', 'email')
        user_type = data.get('user_type', 'all')
        link = data.get('link', '')
        
        print(f"👤 Admin: {request.user.email}")
        print(f"📝 Title: {title}")
        print(f"📢 Channel: {channel}")
        print(f"👥 User Type: {user_type}")
        print(f"📏 Message length: {len(message)} characters")
        print(f"📧 Email Backend: {settings.EMAIL_BACKEND}")
        print(f"📧 Email Host: {settings.EMAIL_HOST}")
        print(f"📧 Email User: {settings.EMAIL_HOST_USER}")
        print("="*60)
        
        # Validate required fields
        if not message:
            return Response({'error': 'Message is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get recipients based on user_type
        users = []
        
        if user_type == 'all':
            users = User.objects.filter(is_active=True)
            print(f"📊 Found {users.count()} total active users")
        elif user_type == 'students':
            users = User.objects.filter(is_active=True, role='student')
            print(f"📊 Found {users.count()} active students")
        elif user_type == 'owners':
            users = User.objects.filter(is_active=True, role='owner')
            print(f"📊 Found {users.count()} active owners")
        elif user_type == 'specific':
            user_ids = data.get('user_ids', [])
            if not user_ids:
                return Response({'error': 'User IDs are required for specific recipients'}, 
                              status=status.HTTP_400_BAD_REQUEST)
            users = User.objects.filter(id__in=user_ids, is_active=True)
            print(f"📊 Found {users.count()} specific users from {len(user_ids)} IDs")
        elif user_type == 'single':
            email = data.get('email')
            phone = data.get('phone')
            if email:
                users = User.objects.filter(email=email, is_active=True)
                print(f"📊 Found {users.count()} users with email {email}")
            elif phone:
                users = User.objects.filter(phone_number__icontains=phone, is_active=True)
                print(f"📊 Found {users.count()} users with phone {phone}")
            else:
                return Response({'error': 'Email or phone number is required for single user'}, 
                              status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': f'Invalid user_type: {user_type}'}, 
                          status=status.HTTP_400_BAD_REQUEST)
        
        if not users.exists():
            return Response({'error': 'No recipients found matching the criteria'}, 
                          status=status.HTTP_404_NOT_FOUND)
        
        email_sent = 0
        sms_sent = 0
        notifications_created = 0
        email_errors = []
        sms_errors = []
        
        # Prepare SMS message (shorter for SMS)
        sms_message = message[:150] if len(message) > 150 else message
        if link:
            sms_message += f"\n🔗 {link}"
        
        print("\n📨 Sending notifications...")
        print("-"*40)
        
        # Create notifications for each user
        for user in users:
            try:
                # Create in-app notification
                Notification.objects.create(
                    user=user,
                    title=title,
                    message=message,
                    link=link,
                    is_read=False
                )
                notifications_created += 1
                print(f"  ✓ In-app notification created for {user.email}")
                
                # Send email if channel includes email
                if channel in ['email', 'both'] and user.email:
                    success, result = self.send_email_html(user.email, title, message, link)
                    if success:
                        email_sent += 1
                        print(f"  ✓ Email sent to {user.email}")
                    else:
                        email_errors.append(f"{user.email}: {result}")
                        print(f"  ✗ Email failed for {user.email}: {result}")
                
                # Send SMS if channel includes sms
                if channel in ['sms', 'both']:
                    # Get user's phone number
                    phone_number = None
                    if hasattr(user, 'phone_number') and user.phone_number:
                        phone_number = user.phone_number
                    elif hasattr(user, 'phone') and user.phone:
                        phone_number = user.phone
                    
                    if phone_number:
                        success, result = self.send_twilio_sms(str(phone_number), sms_message)
                        if success:
                            sms_sent += 1
                            print(f"  ✓ SMS sent to {phone_number}")
                        else:
                            sms_errors.append(f"{phone_number}: {result}")
                            print(f"  ✗ SMS failed for {phone_number}: {result}")
                    else:
                        print(f"  ⚠️ No phone number for {user.email}")
                        
            except Exception as e:
                print(f"  ❌ Error processing user {user.email}: {str(e)}")
                logger.error(f"Error processing user {user.email}: {str(e)}")
        
        # Print summary
        print("\n" + "="*60)
        print("📊 SEND NOTIFICATION SUMMARY")
        print("="*60)
        print(f"✅ In-app notifications created: {notifications_created}")
        print(f"📧 Emails sent: {email_sent}")
        print(f"📱 SMS sent: {sms_sent}")
        print(f"👥 Total recipients: {users.count()}")
        if email_errors:
            print(f"⚠️ Email errors: {len(email_errors)}")
            for err in email_errors[:3]:
                print(f"   - {err}")
        if sms_errors:
            print(f"⚠️ SMS errors: {len(sms_errors)}")
            for err in sms_errors[:3]:
                print(f"   - {err}")
        print("="*60)
        
        response_data = {
            'status': 'success',
            'message': 'Notification processed successfully',
            'notifications_created': notifications_created,
            'email_sent': email_sent,
            'sms_sent': sms_sent,
            'sent_to': users.count(),
            'recipients_found': users.count()
        }
        
        if email_errors:
            response_data['email_errors'] = email_errors[:5]
        if sms_errors:
            response_data['sms_errors'] = sms_errors[:5]
        
        return Response(response_data, status=status.HTTP_200_OK)