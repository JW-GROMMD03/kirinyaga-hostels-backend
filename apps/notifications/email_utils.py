from django.core.mail import send_mail
from django.conf import settings

def send_simple_email(to_email, subject, message):
    """
    Simple email sending function - guaranteed to work
    """
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
        print(f"✅ Email sent to {to_email}")
        return True, "Email sent"
    except Exception as e:
        print(f"❌ Email failed to {to_email}: {e}")
        return False, str(e)