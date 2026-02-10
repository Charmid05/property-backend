from django.core.management.base import BaseCommand
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from finance.models import BillingPeriod
from datetime import date


class Command(BaseCommand):
    help = 'Create initial billing periods for the next 12 months'

    def add_arguments(self, parser):
        parser.add_argument(
            '--months',
            type=int,
            default=12,
            help='Number of months to create billing periods for (default: 12)',
        )

    def handle(self, *args, **options):
        months = options['months']
        today = date.today()
        created_count = 0
        updated_count = 0

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'Creating billing periods for the next {months} months...'
        ))

        for i in range(months):
            start_date = today + relativedelta(months=i, day=1)
            end_date = start_date + relativedelta(months=1, days=-1)
            due_date = start_date + relativedelta(days=5)  # Due on 5th of month

            period_name = start_date.strftime('%B %Y')

            # Get or create billing period
            period, created = BillingPeriod.objects.get_or_create(
                start_date=start_date,
                defaults={
                    'name': period_name,
                    'period_type': 'monthly',
                    'end_date': end_date,
                    'due_date': due_date,
                    'is_active': True,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  [+] Created: {period_name} ({start_date} to {end_date})'
                ))
            else:
                # Update existing period if needed
                updated = False
                if period.name != period_name:
                    period.name = period_name
                    updated = True
                if period.end_date != end_date:
                    period.end_date = end_date
                    updated = True
                if period.due_date != due_date:
                    period.due_date = due_date
                    updated = True

                if updated:
                    period.save()
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(
                        f'  [*] Updated: {period_name}'
                    ))
                else:
                    self.stdout.write(
                        f'  - Exists: {period_name}'
                    )

        self.stdout.write(self.style.SUCCESS(
            f'\n[SUCCESS] Successfully processed billing periods!'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'   Created: {created_count}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'   Updated: {updated_count}'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'   Total: {BillingPeriod.objects.count()}'
        ))

