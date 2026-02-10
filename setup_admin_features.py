#!/usr/bin/env python
"""
Setup script to initialize admin features and data for Property Management System
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a_core.settings')
django.setup()

from django.core.management import call_command
from django.core.management.color import color_style

style = color_style()


def print_header(text):
    """Print a styled header"""
    print("\n" + "=" * 70)
    print(style.MIGRATE_HEADING(f"  {text}"))
    print("=" * 70 + "\n")


def main():
    """Main setup function"""
    print_header("Property Management System - Admin Features Setup")

    try:
        # Step 1: Run migrations
        print_header("Step 1: Running Database Migrations")
        call_command('migrate', verbosity=1)

        # Step 2: Create billing periods
        print_header("Step 2: Creating Billing Periods")
        call_command('create_billing_periods', months=12, verbosity=1)

        # Step 3: Create charge types
        print_header("Step 3: Creating Charge Types")
        call_command('create_charge_types', verbosity=1)

        # Success message
        print_header("[SUCCESS] Setup Complete!")
        print(style.SUCCESS("\nAll admin features have been successfully set up!"))
        print(style.SUCCESS("\nYour backend is now ready to support:"))
        print("  [+] Maintenance Requests")
        print("  [+] Billing Periods")
        print("  [+] Charge Types")
        print("  [+] Invoice Management")
        print("  [+] Payment Processing")
        print("  [+] Receipt Generation")
        print("\n" + "=" * 70 + "\n")

    except Exception as e:
        print(style.ERROR(f"\n[ERROR] Error during setup: {str(e)}"))
        sys.exit(1)


if __name__ == '__main__':
    main()

