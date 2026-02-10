from django.core.management.base import BaseCommand
from finance.models import ChargeType


class Command(BaseCommand):
    help = 'Create initial charge types for the system'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            'Creating charge types...'
        ))

        charge_types = [
            {
                'name': 'Rent',
                'description': 'Monthly rent payment',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Water Bill',
                'description': 'Water utility charges',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Electricity Bill',
                'description': 'Electricity utility charges',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Gas Bill',
                'description': 'Gas utility charges',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Internet Bill',
                'description': 'Internet service charges',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Parking Fee',
                'description': 'Parking space rental',
                'frequency': 'recurring',
                'is_system_charge': False,
                'is_active': True,
            },
            {
                'name': 'Maintenance Fee',
                'description': 'General maintenance charges',
                'frequency': 'one_time',
                'is_system_charge': False,
                'is_active': True,
            },
            {
                'name': 'Late Fee',
                'description': 'Late payment penalty',
                'frequency': 'one_time',
                'is_system_charge': False,
                'is_active': True,
            },
            {
                'name': 'Security Deposit',
                'description': 'Security deposit for property',
                'frequency': 'one_time',
                'is_system_charge': False,
                'is_active': True,
            },
            {
                'name': 'Cleaning Fee',
                'description': 'Move-out or deep cleaning charges',
                'frequency': 'one_time',
                'is_system_charge': False,
                'is_active': True,
            },
            {
                'name': 'Garbage Collection',
                'description': 'Garbage collection service',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Sewer Bill',
                'description': 'Sewer service charges',
                'frequency': 'recurring',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'HVAC Service',
                'description': 'Heating, ventilation, and air conditioning charges',
                'frequency': 'usage_based',
                'is_system_charge': True,
                'is_active': True,
            },
            {
                'name': 'Other',
                'description': 'Miscellaneous charges',
                'frequency': 'one_time',
                'is_system_charge': False,
                'is_active': True,
            },
        ]

        created_count = 0
        existing_count = 0

        for charge_type_data in charge_types:
            charge_type, created = ChargeType.objects.get_or_create(
                name=charge_type_data['name'],
                defaults=charge_type_data
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  [+] Created: {charge_type.name}'
                ))
            else:
                existing_count += 1
                # Update existing charge types
                updated = False
                for key, value in charge_type_data.items():
                    if key != 'name' and getattr(charge_type, key) != value:
                        setattr(charge_type, key, value)
                        updated = True

                if updated:
                    charge_type.save()
                    self.stdout.write(self.style.WARNING(
                        f'  [*] Updated: {charge_type.name}'
                    ))
                else:
                    self.stdout.write(
                        f'  - Exists: {charge_type.name}'
                    )

        self.stdout.write(self.style.SUCCESS(
            f'\n[SUCCESS] Successfully processed charge types!'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'   Created: {created_count}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'   Existing: {existing_count}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'   Total: {ChargeType.objects.count()}'
        ))

