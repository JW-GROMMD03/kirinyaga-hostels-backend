from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.bookings.models import Booking

class Command(BaseCommand):
    help = 'Expire pending bookings older than 4 hours and release hostels'

    def handle(self, *args, **options):
        expired_bookings = Booking.objects.filter(
            status='pending',
            expires_at__lt=timezone.now()
        )
        
        count = 0
        for booking in expired_bookings:
            booking.status = 'expired'
            booking.save()
            
            # Release the hostel back to available
            if booking.hostel.available is False:
                other_active = Booking.objects.filter(
                    hostel=booking.hostel,
                    status='confirmed'
                ).exclude(id=booking.id).exists()
                if not other_active:
                    booking.hostel.available = True
                    booking.hostel.save()
            
            count += 1
            self.stdout.write(f"Expired booking: {booking.id} - Hostel: {booking.hostel.name}")
        
        self.stdout.write(self.style.SUCCESS(f'Successfully expired {count} bookings and released hostels'))