"""
API clients for SerpApi (flights) and ExchangeRate-API (currency).
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Data paths
DATA_DIR = Path(__file__).parent.parent / "data"
COL_DATA_PATH = DATA_DIR / "col_data.json"
COUNTRIES_PATH = DATA_DIR / "countries.json"


class SerpApiClient:
    """Client for SerpApi Google Flights."""

    BASE_URL = "https://serpapi.com/search"

    def __init__(self):
        self.api_key = os.getenv("SERPAPI_KEY", "")

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def get_flight_price(
        self,
        origin: str,
        destination: str,
        departure_date: Optional[str] = None,
        return_date: Optional[str] = None
    ) -> Optional[float]:
        """
        Get lowest flight price for route using SerpApi Google Flights.

        Args:
            origin: Origin airport code (e.g., 'TPE')
            destination: Destination airport code (e.g., 'NRT')
            departure_date: Departure date (YYYY-MM-DD), defaults to 30 days out
            return_date: Return date, defaults to 7 days after departure

        Returns:
            Lowest price in TWD or None if unavailable
        """
        if not self.is_configured:
            return None

        # Default dates: 30 days out, 7 day trip
        if not departure_date:
            departure_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        if not return_date:
            dep = datetime.strptime(departure_date, "%Y-%m-%d")
            return_date = (dep + timedelta(days=7)).strftime("%Y-%m-%d")

        try:
            response = requests.get(
                self.BASE_URL,
                params={
                    "engine": "google_flights",
                    "departure_id": origin,
                    "arrival_id": destination,
                    "outbound_date": departure_date,
                    "return_date": return_date,
                    "currency": "TWD",
                    "hl": "en",
                    "api_key": self.api_key
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            # Check for error in response
            if "error" in data:
                print(f"SerpApi error: {data['error']}")
                return None

            # Extract prices from best_flights or other_flights
            prices = []

            # Check best_flights first
            best_flights = data.get("best_flights", [])
            for flight in best_flights:
                price = flight.get("price")
                if price:
                    prices.append(float(price))

            # Also check other_flights
            other_flights = data.get("other_flights", [])
            for flight in other_flights:
                price = flight.get("price")
                if price:
                    prices.append(float(price))

            return min(prices) if prices else None

        except requests.RequestException as e:
            print(f"SerpApi flight search error: {e}")
            return None
        except (ValueError, KeyError) as e:
            print(f"SerpApi response parsing error: {e}")
            return None


class ExchangeRateClient:
    """Client for ExchangeRate-API."""

    BASE_URL = "https://v6.exchangerate-api.com/v6"

    def __init__(self):
        self.api_key = os.getenv("EXCHANGERATE_API_KEY", "")

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def get_rates(self, base_currency: str = "TWD") -> Optional[Dict[str, float]]:
        """
        Get exchange rates with TWD as base.

        Args:
            base_currency: Base currency code

        Returns:
            Dictionary of currency code to rate, or None if unavailable
        """
        if not self.is_configured:
            return None

        try:
            response = requests.get(
                f"{self.BASE_URL}/{self.api_key}/latest/{base_currency}",
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if data.get("result") == "success":
                return data.get("conversion_rates", {})
            return None

        except requests.RequestException as e:
            print(f"ExchangeRate API error: {e}")
            return None

    def get_rate(self, target_currency: str, base_currency: str = "TWD") -> Optional[float]:
        """
        Get single exchange rate.

        Args:
            target_currency: Target currency code
            base_currency: Base currency code

        Returns:
            Exchange rate or None
        """
        rates = self.get_rates(base_currency)
        if rates:
            return rates.get(target_currency)
        return None


def get_col_data() -> Dict[str, Any]:
    """
    Load embedded cost of living data.

    Returns:
        Dictionary with city CoL data
    """
    try:
        with open(COL_DATA_PATH, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading CoL data: {e}")
        return {"cities": {}}


def get_col_for_country(country_name: str) -> Optional[float]:
    """
    Get monthly cost of living for a country's capital city.

    Args:
        country_name: Country name

    Returns:
        Monthly cost in USD or None
    """
    col_data = get_col_data()
    cities = col_data.get("cities", {})

    # Find city matching country
    for city_name, city_data in cities.items():
        if city_data.get("country") == country_name:
            return city_data.get("monthly_cost_usd")

    return None


def load_countries() -> Dict[str, Any]:
    """
    Load country configuration data.

    Returns:
        Country configuration dictionary
    """
    try:
        with open(COUNTRIES_PATH, "r") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading countries data: {e}")
        return {"origin": {}, "destinations": {}}


def get_mock_flight_cost(country_key: str) -> Optional[float]:
    """
    Get mock/baseline flight cost for a country.

    Args:
        country_key: Country key from countries.json

    Returns:
        Mock flight cost in TWD or None
    """
    countries = load_countries()
    destination = countries.get("destinations", {}).get(country_key)
    if destination:
        return destination.get("baseline", {}).get("flight_cost_twd")
    return None


def get_mock_exchange_rate(country_key: str) -> Optional[float]:
    """
    Get mock/baseline exchange rate for a country.

    Args:
        country_key: Country key from countries.json

    Returns:
        Mock exchange rate (TWD to foreign) or None
    """
    countries = load_countries()
    destination = countries.get("destinations", {}).get(country_key)
    if destination:
        return destination.get("baseline", {}).get("exchange_rate")
    return None
