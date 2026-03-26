# scripts/create_plans.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.subscriptions.models import SubscriptionPlan

plans = [
    {
        'name': 'Basic',
        'price': 500,
        'duration_days': 30,
        'max_hostels': 1,
        'max_images_per_hostel': 5,
        'is_featured_listing': False,
        'priority_support': False,
        'is_popular': False,
        'description': 'Perfect for starting with one hostel'
    },
    {
        'name': 'Premium',
        'price': 1500,
        'duration_days': 30,
        'max_hostels': 5,
        'max_images_per_hostel': 15,
        'is_featured_listing': True,
        'priority_support': True,
        'is_popular': True,
        'description': 'Most popular for growing businesses'
    },
    {
        'name': 'Enterprise',
        'price': 5000,
        'duration_days': 30,
        'max_hostels': -1,
        'max_images_per_hostel': 50,
        'is_featured_listing': True,
        'priority_support': True,
        'is_popular': False,
        'description': 'Unlimited hostels & premium features'
    }
]

for plan_data in plans:
    plan, created = SubscriptionPlan.objects.get_or_create(
        name=plan_data['name'],
        defaults=plan_data
    )
    if created:
        print(f"Created plan: {plan.name}")
    else:
        print(f"Plan already exists: {plan.name}")