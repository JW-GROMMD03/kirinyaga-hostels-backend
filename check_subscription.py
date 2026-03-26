# check_subscription.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.subscriptions.models import SubscriptionPlan, OwnerSubscription
from django.contrib.auth import get_user_model

User = get_user_model()

def check_subscription():
    print("\n=== CHECKING SUBSCRIPTION DATABASE ===\n")
    
    # Check if plans exist
    plans = SubscriptionPlan.objects.all()
    print(f"📋 Subscription Plans ({plans.count()}):")
    for plan in plans:
        print(f"   - {plan.name}: KSh {plan.price}, Active: {plan.is_active}")
    
    if not plans:
        print("❌ No subscription plans found! Creating default plans...")
        from decimal import Decimal
        SubscriptionPlan.objects.create(
            name="Basic Plan",
            price=Decimal('400.00'),
            duration_days=30,
            max_hostels=4,
            is_active=True
        )
        SubscriptionPlan.objects.create(
            name="Standard Plan",
            price=Decimal('550.00'),
            duration_days=30,
            max_hostels=10,
            is_active=True
        )
        SubscriptionPlan.objects.create(
            name="Premium Plan",
            price=Decimal('700.00'),
            duration_days=30,
            max_hostels=-1,
            is_active=True
        )
        print("✅ Default plans created!")
    
    # Check user
    try:
        user = User.objects.get(email='eugkipkomen75@gmail.com')
        print(f"\n👤 User: {user.email} (Role: {user.role})")
        
        # Check subscription
        try:
            sub = OwnerSubscription.objects.get(owner=user)
            print(f"\n📊 Subscription found:")
            print(f"   ID: {sub.id}")
            print(f"   Plan: {sub.plan.name if sub.plan else 'No plan'}")
            print(f"   Active: {sub.is_active}")
            print(f"   Start: {sub.start_date}")
            print(f"   End: {sub.end_date}")
            
            if sub.end_date:
                days_left = (sub.end_date - django.utils.timezone.now()).days
                print(f"   Days left: {days_left}")
        except OwnerSubscription.DoesNotExist:
            print("\n❌ No subscription found for this user!")
            print("Creating subscription...")
            
            # Create subscription
            plan = SubscriptionPlan.objects.first()
            sub = OwnerSubscription.objects.create(
                owner=user,
                plan=plan,
                start_date=django.utils.timezone.now(),
                end_date=django.utils.timezone.now() + django.utils.timedelta(days=30),
                is_active=True
            )
            print(f"✅ Subscription created: {sub.plan.name}")
            
    except User.DoesNotExist:
        print(f"❌ User not found: eugkipkomen75@gmail.com")

if __name__ == "__main__":
    check_subscription()