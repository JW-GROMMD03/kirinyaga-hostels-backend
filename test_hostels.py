import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from apps.hostels.models import Hostel
from apps.accounts.models import User

def test_hostels():
    print("\n=== TESTING HOSTELS DATABASE ===\n")
    
    # Check all hostels
    all_hostels = Hostel.objects.all()
    print(f"Total hostels in database: {all_hostels.count()}")
    
    for hostel in all_hostels:
        print(f"\nHostel ID: {hostel.id}")
        print(f"Name: {hostel.name}")
        print(f"Owner: {hostel.owner.email}")
        print(f"Owner ID: {hostel.owner.id}")
        print(f"Approved: {hostel.is_approved}")
        print(f"Images count: {hostel.images.count()}")
    
    # Check owners
    owners = User.objects.filter(role='owner')
    print(f"\nTotal owners: {owners.count()}")
    
    for owner in owners:
        owner_hostels = Hostel.objects.filter(owner=owner)
        print(f"\nOwner: {owner.email} (ID: {owner.id})")
        print(f"Hostels: {owner_hostels.count()}")
        for h in owner_hostels:
            print(f"  - {h.name}")

if __name__ == '__main__':
    test_hostels()