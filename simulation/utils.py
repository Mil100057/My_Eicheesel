import requests
from decimal import Decimal
from datetime import datetime
import logging
from typing import Optional, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)


class StockAPIClient:
    def __init__(self):
        self.api_key = settings.ALPHA_VANTAGE_API_KEY
        self.base_url = "https://www.alphavantage.co/query"

    def get_stock_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time quote for a stock."""
        try:
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol,
                "apikey": self.api_key
            }

            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Global Quote" in data and data["Global Quote"]:
                quote = data["Global Quote"]
                return {
                    "price": Decimal(quote["05. price"]),
                    "change": Decimal(quote["09. change"]),
                    "change_percent": Decimal(quote["10. change percent"].strip('%')),
                    "volume": int(quote["06. volume"]),
                    "latest_trading_day": datetime.strptime(quote["07. latest trading day"], "%Y-%m-%d").date(),
                }
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for symbol {symbol}: {str(e)}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing API response for symbol {symbol}: {str(e)}")
            return None

    def get_daily_prices(self, symbol: str, outputsize: str = "compact") -> Optional[Dict[str, Dict[str, Decimal]]]:
        """Get daily price history for a stock."""
        try:
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": outputsize,  # compact = 100 derniers jours, full = tout l'historique
                "apikey": self.api_key
            }

            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            data = response.json()

            if "Time Series (Daily)" in data:
                daily_prices = {}
                for date, prices in data["Time Series (Daily)"].items():
                    daily_prices[date] = {
                        "open": Decimal(prices["1. open"]),
                        "high": Decimal(prices["2. high"]),
                        "low": Decimal(prices["3. low"]),
                        "close": Decimal(prices["4. close"]),
                        "volume": int(prices["5. volume"])
                    }
                return daily_prices
            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed for symbol {symbol}: {str(e)}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Error parsing API response for symbol {symbol}: {str(e)}")
            return None