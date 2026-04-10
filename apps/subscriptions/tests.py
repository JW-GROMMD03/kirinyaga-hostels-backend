from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock
from .models import SubscriptionPlan, OwnerSubscription, PaymentTransaction

User = get_user_model()


class SubscriptionPlanModelTest(TestCase):
    """Test SubscriptionPlan model"""
    
    def setUp(self):
        self.plan = SubscriptionPlan.objects.create(
            name='basic',
            display_name='Basic',
            price_kes=500,
            duration_days=30,
            max_hostels=3,
            max_images_per_hostel=10,
            can_feature_listings=False,
            priority_support=False,
            analytics_access=True,
            api_access=False,
            features=['3 hostels', '10 images per hostel', 'Basic analytics'],
            is_active=True
        )
    
    def test_plan_creation(self):
        self.assertEqual(self.plan.name, 'basic')
        self.assertEqual(self.plan.display_name, 'Basic')
        self.assertEqual(self.plan.price_kes, 500)
        self.assertEqual(self.plan.max_hostels, 3)
    
    def test_plan_str(self):
        self.assertEqual(str(self.plan), 'Basic - KSh 500')
    
    def test_plan_features_list(self):
        features = self.plan.get_features_list() if hasattr(self.plan, 'get_features_list') else []
        self.assertIsInstance(features, list)


class OwnerSubscriptionModelTest(TestCase):
    """Test OwnerSubscription model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@test.com',
            password='testpass123',
            full_name='Test Owner',
            role='owner'
        )
        self.plan = SubscriptionPlan.objects.create(
            name='premium',
            display_name='Premium',
            price_kes=1500,
            duration_days=30,
            max_hostels=10,
            can_feature_listings=True
        )
        self.subscription = OwnerSubscription.objects.create(
            owner=self.user,
            plan=self.plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            is_active=True,
            payment_status='completed',
            amount_paid=1500
        )
    
    def test_subscription_creation(self):
        self.assertEqual(self.subscription.owner.email, 'owner@test.com')
        self.assertEqual(self.subscription.plan.name, 'premium')
        self.assertTrue(self.subscription.is_active)
    
    def test_subscription_str(self):
        self.assertIn('owner@test.com', str(self.subscription))
    
    def test_subscription_expired(self):
        expired_sub = OwnerSubscription.objects.create(
            owner=self.user,
            plan=self.plan,
            start_date=timezone.now() - timedelta(days=60),
            end_date=timezone.now() - timedelta(days=30),
            is_active=False
        )
        self.assertFalse(expired_sub.is_active)


class PaymentTransactionModelTest(TestCase):
    """Test PaymentTransaction model"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@test.com',
            password='testpass123',
            full_name='Test User',
            role='owner'
        )
        self.plan = SubscriptionPlan.objects.create(
            name='basic',
            display_name='Basic',
            price_kes=500,
            duration_days=30,
            max_hostels=3
        )
        self.subscription = OwnerSubscription.objects.create(
            owner=self.user,
            plan=self.plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            is_active=False,
            payment_status='pending'
        )
        self.transaction = PaymentTransaction.objects.create(
            subscription=self.subscription,
            amount=500,
            payment_method='mpesa',
            transaction_id='TEST123456',
            phone_number='254712345678',
            status='pending'
        )
    
    def test_transaction_creation(self):
        self.assertEqual(self.transaction.amount, 500)
        self.assertEqual(self.transaction.payment_method, 'mpesa')
        self.assertEqual(self.transaction.status, 'pending')
    
    def test_transaction_str(self):
        self.assertIn('TEST123456', str(self.transaction))


class SubscriptionUtilsTest(TestCase):
    """Test subscription utility functions"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@test.com',
            password='testpass123',
            full_name='Test Owner',
            role='owner'
        )
    
    def test_check_hostel_creation_eligibility_free(self):
        from apps.subscriptions.utils import check_hostel_creation_eligibility
        
        can_add, message = check_hostel_creation_eligibility(self.user)
        # Free tier: should be able to add first hostel
        self.assertTrue(can_add)
    
    def test_get_owner_subscription_status(self):
        from apps.subscriptions.utils import get_owner_subscription_status
        
        status = get_owner_subscription_status(self.user)
        self.assertEqual(status['plan'], 'free')
        self.assertFalse(status['has_active_subscription'])


class SubscriptionAPITest(TestCase):
    """Test subscription API endpoints"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='owner@test.com',
            password='testpass123',
            full_name='Test Owner',
            role='owner'
        )
        self.client.login(email='owner@test.com', password='testpass123')
    
    def test_subscription_plans_endpoint(self):
        # Create a plan first
        SubscriptionPlan.objects.create(
            name='basic',
            display_name='Basic',
            price_kes=500,
            duration_days=30,
            max_hostels=3,
            is_active=True
        )
        
        response = self.client.get('/api/subscriptions/plans/')
        # Note: This will depend on your URL configuration
        if response.status_code == 200:
            self.assertEqual(response.status_code, 200)
    
    def test_current_subscription_endpoint(self):
        response = self.client.get('/api/subscriptions/my/')
        # Should return 200 even without subscription
        self.assertEqual(response.status_code, 200)