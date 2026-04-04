from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.notifications.models import Notification

class Command(BaseCommand):
    help = 'Delete notifications older than 3 days'

    def handle(self, *args, **options):
        cutoff_date = timezone.now() - timedelta(days=3)
        
        # Delete notifications older than 3 days
        deleted_count, _ = Notification.objects.filter(
            created_at__lt=cutoff_date,
            is_deleted=False
        ).delete()
        
        # Also delete expired notifications
        expired_count, _ = Notification.objects.filter(
            delete_at__lte=timezone.now(),
            is_deleted=False
        ).delete()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully deleted {deleted_count} old notifications and {expired_count} expired notifications'
            )
        )