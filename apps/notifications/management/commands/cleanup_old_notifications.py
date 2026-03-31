from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from apps.notifications.models import Notification
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete notifications older than 7 days'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to keep notifications (default: 7)'
        )

    def handle(self, *args, **options):
        days = options['days']
        cutoff_date = timezone.now() - timedelta(days=days)
        
        self.stdout.write(f"Deleting notifications older than {days} days...")
        self.stdout.write(f"Cutoff date: {cutoff_date}")
        
        # Count before deletion
        count_before = Notification.objects.filter(created_at__lt=cutoff_date).count()
        
        if count_before == 0:
            self.stdout.write(self.style.SUCCESS("No old notifications to delete."))
            return
        
        # Perform deletion
        deleted_count, _ = Notification.objects.filter(created_at__lt=cutoff_date).delete()
        
        self.stdout.write(
            self.style.SUCCESS(f"Successfully deleted {deleted_count} notifications older than {days} days")
        )
        
        logger.info(f"Cleanup command: Deleted {deleted_count} old notifications")