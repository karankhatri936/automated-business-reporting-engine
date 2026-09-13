"""Tests for data validation utilities."""

import unittest

from automated_business_reporting_engine.data.validator import validate_product_data
from automated_business_reporting_engine.utils.exceptions import DataValidationError


class TestDataValidation(unittest.TestCase):
    """Test suite for data validation."""

    def test_valid_products(self):
        """Test that valid products are accepted."""
        valid_products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": 10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "In Stock"
            }
        ]

        validate_product_data(valid_products)  # Should not raise
        self.assertEqual(len(valid_products), 1)

    def test_missing_field(self):
        """Test that missing required fields raise DataValidationError."""
        invalid_products = [
            {
                "id": 1,
                "title": "Test Product",
                # missing price
                "category": "Electronics",
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "In Stock"
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)

    def test_negative_price(self):
        """Test that negative price is detected."""
        invalid_products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": -10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "In Stock"
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)

    def test_negative_stock(self):
        """Test that negative stock is detected."""
        invalid_products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": 10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": -5,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "In Stock"
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)

    def test_rating_out_of_range(self):
        """Test that rating > 5 is detected."""
        invalid_products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": 10.0,
                "category": "Electronics",
                "rating": 10.0,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "In Stock"
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)

    def test_discount_out_of_range(self):
        """Test that discount > 100 is detected."""
        invalid_products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": 10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 150.0,
                "brand": "TestBrand",
                "availabilityStatus": "In Stock"
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)

    def test_invalid_availability_status(self):
        """Test that invalid availability status is detected."""
        invalid_products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": 10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "unknown_status"
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)

    def test_missing_values(self):
        """Test that None values are detected."""
        invalid_products = [
            {
                "id": None,
                "title": None,
                "price": None,
                "category": None,
                "rating": None,
                "stock": None,
                "discountPercentage": None,
                "brand": None,
                "availabilityStatus": None
            }
        ]

        with self.assertRaises(DataValidationError):
            validate_product_data(invalid_products)


if __name__ == "__main__":
    unittest.main()