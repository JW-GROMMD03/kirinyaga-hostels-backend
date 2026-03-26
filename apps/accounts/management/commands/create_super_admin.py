from django.core.management.base import BaseCommand
from apps.accounts.models import User

class Command(BaseCommand):
    help = 'Create super admin account'
    
    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Admin email')
        parser.add_argument('--password', type=str, help='Admin password')
        parser.add_argument('--name', type=str, help='Admin full name')
    
    def handle(self, *args, **options):
        email = options.get('email') or input("Enter super admin email: ")
        name = options.get('name') or input("Enter full name: ")
        password = options.get('password') or input("Enter password: ")
        
        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.ERROR('User already exists'))
            return
        
        user = User.objects.create_superuser(
            email=email,
            password=password,
            full_name=name
        )
        
        self.stdout.write(self.style.SUCCESS(f'Super admin created: {user.email}'))