"""API client for retrieving product data."""

import requests
from typing import List, Dict, Any
from ..config import config
from ..utils.logger import setup_logger
from ..utils.exceptions import APIError, APIPaginationError

logger = setup_logger(__name__)


class APIClient:
    """Client for interacting with the products API."""

    def __init__(self, api_config=None):
        """Initialize the API client with configuration."""
        self.api_config = api_config or config.api
        self.pagination_config = config.pagination
        logger.info(f"APIClient initialized for {self.api_config.url}")

    def get_all_products(self) -> List[Dict[str, Any]]:
        """
        Retrieve all products from the API using pagination.

        Returns:
            List of product dictionaries.

        Raises:
            APIError: If there's an issue with the API request or response.
        """
        all_products = []
        seen_ids: set = set()
        skip = 0
        limit = self.pagination_config.limit

        logger.info(f"Starting to fetch all products with limit={limit}")

        while True:
            try:
                params = {
                    "limit": limit,
                    "skip": skip
                }
                logger.debug(f"Fetching products with skip={skip}, limit={limit}")
                response = requests.get(
                    self.api_config.url,
                    params=params,
                    timeout=self.api_config.timeout
                )
                response.raise_for_status()

                data = response.json()

                # Handle different possible response structures
                if isinstance(data, dict) and "products" in data:
                    products = data.get("products", [])
                    total = data.get("total", 0)
                elif isinstance(data, list):
                    products = data
                    total = len(data)
                else:
                    raise APIError(f"Unexpected response format: {type(data)}")

                if not products:
                    logger.info("No more products returned from API")
                    break

                # Guard against an API that keeps returning the same page
                # (e.g. it ignores "skip"): without new records the loop
                # would otherwise never terminate.
                page_ids = {p.get("id") for p in products if isinstance(p, dict)}
                if page_ids and page_ids.issubset(seen_ids):
                    raise APIPaginationError(
                        "Pagination stalled: the page at skip="
                        f"{skip} returned no new records"
                    )
                seen_ids.update(page_ids)

                all_products.extend(products)
                logger.debug(f"Fetched {len(products)} products (total so far: {len(all_products)})")

                # Check if we've retrieved all products
                if total and len(all_products) >= total:
                    logger.info(f"Retrieved all {total} products")
                    break
                elif len(products) < limit:
                    logger.info(f"Last page reached with {len(products)} products")
                    break

                skip += limit

            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error: {e}")
                raise APIError(f"Failed to connect to API: {e}")
            except requests.exceptions.Timeout as e:
                logger.error(f"Timeout error: {e}")
                raise APIError(f"API request timed out: {e}")
            except requests.exceptions.HTTPError as e:
                logger.error(f"HTTP error: {e}")
                raise APIError(f"API returned HTTP error: {e}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                raise APIError(f"API request failed: {e}")
            except ValueError as e:
                logger.error(f"JSON parsing error: {e}")
                raise APIError(f"Failed to parse API response: {e}")

        logger.info(f"Completed fetching {len(all_products)} total products")
        return all_products