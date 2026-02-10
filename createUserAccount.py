# Create this file at: billing/management/commands/create_user_accounts.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from finance.models import UserAccount

User = get_user_model()


class Command(BaseCommand):
    help = 'Create UserAccount for existing users who don\'t have one'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating accounts',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Find users without accounts
        users_without_accounts = User.objects.filter(account__isnull=True)

        if not users_without_accounts.exists():
            self.stdout.write(
                self.style.SUCCESS('All users already have accounts.')
            )
            return

        count = users_without_accounts.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would create {count} user accounts for:'
                )
            )
            for user in users_without_accounts:
                self.stdout.write(f'  - {user.username} ({user.email})')
        else:
            self.stdout.write(f'Creating {count} user accounts...')

            created_count = 0
            for user in users_without_accounts:
                try:
                    UserAccount.objects.create(user=user)
                    created_count += 1
                    self.stdout.write(
                        f'  ✓ Created account for {user.username}')
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f'  ✗ Failed to create account for {user.username}: {e}'
                        )
                    )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created {created_count} user accounts.'
                )
            )
