from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from property.models import Property, Unit
from management.models import Office
from decimal import Decimal

User = get_user_model()

class TenantCreationTestCase(APITestCase):
    def setUp(self):
        # Create an admin user to create the tenant
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            username='admin',
            password='Password123!'
        )
        self.client.force_authenticate(user=self.admin_user)

        # Create necessary related models
        self.office = Office.objects.create(
            name="Main Office",
            manager=self.admin_user
        )
        self.property = Property.objects.create(
            name="Test Property",
            address="123 Test St",
            office=self.office
        )
        self.unit = Unit.objects.create(
            property=self.property,
            name="Unit 101",
            abbreviated_name="U101",
            unit_number="U101",
            monthly_rent=Decimal('1000.00'),
            deposit_amount=Decimal('1000.00')
        )

    def test_create_tenant_without_gender(self):
        url = reverse('tenants:tenant-list')
        data = {
            'username': 'newtenant',
            'email': 'tenant@example.com',
            'password': 'Password123!',
            'password2': 'Password123!',
            'first_name': 'New',
            'last_name': 'Tenant',
            'unit': self.unit.id,
            'status': 'pending',
            'lease_start_date': '2026-02-11',
            'phone_number': '+254700000000',
            # 'gender' is intentionally omitted or sent as empty string
            'gender': '',
            'send_welcome_email': False
        }
        
        response = self.client.post(url, data, format='json')
        
        # Check if the creation was successful (previously it would return 500)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.filter(email='tenant@example.com').count(), 1)
        user = User.objects.get(email='tenant@example.com')
        self.assertEqual(user.gender, '') # Allowed now
