"""Tests for the API client (all HTTP traffic is mocked - no real API calls)."""

import unittest
from unittest.mock import patch, MagicMock

import requests

from automated_business_reporting_engine.api.client import APIClient
from automated_business_reporting_engine.config import config
from automated_business_reporting_engine.utils.exceptions import (
    APIError,
    APIPaginationError,
)


class TestAPIClient(unittest.TestCase):
    """Test suite for APIClient."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = APIClient()

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_successful_request(self, mock_get):
        """Test a successful API request returns products."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "products": [
                {"id": 1, "title": "Product 1", "price": 10.0, "category": "Electronics"},
                {"id": 2, "title": "Product 2", "price": 20.0, "category": "Books"}
            ],
            "total": 2,
            "skip": 0,
            "limit": 10
        }
        mock_get.return_value = mock_response

        products = self.client.get_all_products()

        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["id"], 1)
        self.assertEqual(products[0]["title"], "Product 1")
        self.assertEqual(products[1]["id"], 2)
        self.assertEqual(products[1]["title"], "Product 2")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertIn("params", call_kwargs)
        self.assertEqual(call_kwargs["params"]["limit"], config.pagination.limit)
        self.assertEqual(call_kwargs["params"]["skip"], 0)

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_pagination_multiple_pages(self, mock_get):
        """Test pagination fetches multiple pages until all products retrieved."""
        # Create a client with a smaller limit so pagination actually occurs
        client = APIClient()
        original_limit = client.pagination_config.limit
        client.pagination_config.limit = 2

        try:
            mock_response1 = MagicMock()
            mock_response1.raise_for_status.return_value = None
            mock_response1.json.return_value = {
                "products": [
                    {"id": 1, "title": "Product 1"},
                    {"id": 2, "title": "Product 2"}
                ],
                "total": 4,
                "skip": 0,
                "limit": 2
            }

            mock_response2 = MagicMock()
            mock_response2.raise_for_status.return_value = None
            mock_response2.json.return_value = {
                "products": [
                    {"id": 3, "title": "Product 3"},
                    {"id": 4, "title": "Product 4"}
                ],
                "total": 4,
                "skip": 2,
                "limit": 2
            }

            mock_get.side_effect = [mock_response1, mock_response2]

            products = client.get_all_products()

            self.assertEqual(len(products), 4)
            product_ids = [p["id"] for p in products]
            self.assertEqual(len(product_ids), len(set(product_ids)))
            self.assertIn(1, product_ids)
            self.assertIn(2, product_ids)
            self.assertIn(3, product_ids)
            self.assertIn(4, product_ids)

            self.assertEqual(mock_get.call_count, 2)
        finally:
            client.pagination_config.limit = original_limit

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_api_error_http(self, mock_get):
        """Test HTTP error raises APIError."""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404 Not Found"
        )

        mock_get.return_value = mock_response

        with self.assertRaises(APIError):
            self.client.get_all_products()

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_connection_error(self, mock_get):
        """Test connection error raises APIError."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")


        with self.assertRaises(APIError):
            self.client.get_all_products()

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_timeout_error(self, mock_get):
        """Test timeout error raises APIError."""
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")


        with self.assertRaises(APIError):
            self.client.get_all_products()

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_json_parsing_error(self, mock_get):
        """Test JSON parsing error raises APIError."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_get.return_value = mock_response

        with self.assertRaises(APIError):
            self.client.get_all_products()

    @patch('automated_business_reporting_engine.api.client.requests.get')
    def test_pagination_stall_raises(self, mock_get):
        """A page that returns no new records must raise APIPaginationError."""
        client = APIClient()
        client.pagination_config.limit = 2

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "products": [{"id": 1}, {"id": 2}],
            "total": 99,  # Inconsistent total keeps the loop "wanting" more.
            "skip": 0,
            "limit": 2,
        }
        mock_get.return_value = mock_response

        with self.assertRaises(APIPaginationError):
            client.get_all_products()
        self.assertEqual(mock_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
