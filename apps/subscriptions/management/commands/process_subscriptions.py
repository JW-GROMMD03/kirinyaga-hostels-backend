from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from datetime import timedelta
from apps.subscriptions.models import OwnerSubscription, SubscriptionLog


class Command(BaseCommand):
    help = 'Process subscriptions: send expiry notifications and clean up expired ones'

    def handle(self, *args, **options):
        now = timezone.now()
        
        # ========== 1. SEND EXPIRY NOTIFICATIONS (7 days before) ==========
        expiring_soon = OwnerSubscription.objects.filter(
            is_active=True,
            end_date__gte=now,
            end_date__lte=now + timedelta(days=7)
        )
        
        notified_count = 0
        for sub in expiring_soon:
            days_left = (sub.end_date - now).days
            self.send_expiry_warning(sub, days_left)
            notified_count += 1
        
        # ========== 2. CLEAN UP EXPIRED SUBSCRIPTIONS ==========
        expired_subs = OwnerSubscription.objects.filter(
            is_active=True,
            end_date__lt=now
        )
        
        expired_count = 0
        for sub in expired_subs:
            sub.is_active = False
            sub.save()
            
            # Log expiration
            SubscriptionLog.objects.create(
                subscription=sub,
                action='expired',
                details={'reason': 'Subscription period ended automatically'}
            )
            
            # Send expiration notice
            self.send_expired_notice(sub)
            expired_count += 1
        
        # ========== 3. OUTPUT SUMMARY ==========
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Processed {notified_count} expiry notifications'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'✅ Deactivated {expired_count} expired subscriptions'
        ))
    
    def send_expiry_warning(self, subscription, days_left):
        """Send warning email for subscription expiring soon"""
        if not subscription.owner.email:
            return
        
        subject = f"⚠️ Subscription Expiring in {days_left} Days"
        message = f"""
Hello {subscription.owner.full_name},

Your {subscription.plan.display_name if subscription.plan else 'Premium'} subscription will expire in {days_left} days.

📅 Expiry Date: {subscription.end_date.strftime('%Y-%m-%d')}

To avoid service interruption, please renew now:

🔗 https://kirinyaga-hostels-frontend.onrender.com/owner/subscription-plans.html

Regards,
Kirinyaga Hostels Team
"""
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [subscription.owner.email], fail_silently=True)
            self.stdout.write(f"  📧 Sent expiry warning to {subscription.owner.email} ({days_left} days left)")
        except Exception as e:
            self.stdout.write(f"  ❌ Failed to send email: {e}")
    
    def send_expired_notice(self, subscription):
        """Send notice that subscription has expired"""
        if not subscription.owner.email:
            return
        
        subject = "❌ Subscription Expired - Action Required"
        message = f"""
Hello {subscription.owner.full_name},

Your {subscription.plan.display_name if subscription.plan else 'Premium'} subscription has expired.

⚠️ Your hostels are now in read-only mode. You cannot add or edit hostels.

To restore full access, please renew now:

🔗 https://kirinyaga-hostels-frontend.onrender.com/owner/subscription-plans.html

Regards,
Kirinyaga Hostels Team
"""
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [subscription.owner.email], fail_silently=True)
            self.stdout.write(f"  📧 Sent expiration notice to {subscription.owner.email}")
        except Exception as e:
            self.stdout.write(f"  ❌ Failed to send email: {e}")