from django.core.cache import cache
from django.utils import timezone
from .models import Stock
import logging

logger = logging.getLogger(__name__)


def update_all_stocks():
    """Update market data for all stocks."""
    stocks = Stock.objects.all()
    updated_count = 0

    for stock in stocks:
        try:
            if stock.needs_update():
                if stock.update_market_data():
                    updated_count += 1
                    logger.info(f"Updated market data for {stock.symbol}")
                else:
                    logger.warning(f"Failed to update market data for {stock.symbol}")
        except Exception as e:
            logger.error(f"Error updating {stock.symbol}: {str(e)}")

    return updated_count