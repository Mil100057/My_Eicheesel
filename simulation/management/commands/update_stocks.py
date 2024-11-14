from django.core.management.base import BaseCommand
from ...tasks import update_all_stocks

class Command(BaseCommand):
    help = 'Update market data for all stocks'

    def handle(self, *args, **options):
        updated_count = update_all_stocks()
        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated {updated_count} stocks')
        )