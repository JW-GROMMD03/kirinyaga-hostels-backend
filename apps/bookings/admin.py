from django.contrib import admin
from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['id', 'student', 'hostel', 'move_in_date', 'guests', 'status', 'created_at']
    list_filter = ['status', 'move_in_date']
    search_fields = ['student__email', 'hostel__name', 'special_requests']
    readonly_fields = ['id', 'created_at', 'updated_at', 'expires_at']
    date_hierarchy = 'move_in_date'  # changed from 'check_in'
    raw_id_fields = ['student', 'hostel']