from django.contrib import admin
from .models import SubscriptionPlan, OwnerSubscription, PaymentTransaction, SubscriptionLog

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'price_kes', 'max_hostels', 'duration_days', 'is_active']
    list_filter = ['is_active', 'name']
    search_fields = ['display_name', 'description']
    list_editable = ['price_kes', 'max_hostels', 'is_active']


@admin.register(OwnerSubscription)
class OwnerSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['owner', 'plan', 'start_date', 'end_date', 'is_active', 'payment_status']
    list_filter = ['is_active', 'payment_status', 'plan']
    search_fields = ['owner__email', 'owner__full_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id', 'amount', 'payment_method', 'status', 'created_at']
    list_filter = ['status', 'payment_method']
    search_fields = ['transaction_id', 'mpesa_receipt']


@admin.register(SubscriptionLog)
class SubscriptionLogAdmin(admin.ModelAdmin):
    list_display = ['subscription', 'action', 'created_at']
    list_filter = ['action']
    readonly_fields = ['created_at']