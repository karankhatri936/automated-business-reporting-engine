"""Tests for data processing utilities."""

import unittest

import pandas as pd
from automated_business_reporting_engine.data.processor import (
    clean_product_data,
    calculate_inventory_value,
    add_derived_fields,
    create_dataframe
)


class TestDataProcessor(unittest.TestCase):
    """Test suite for data processing."""

    def setUp(self):
        """Set up test data."""
        self.sample_products = [
            {
                "id": 1,
                "title": "Test Product 1",
                "price": 10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "in_stock"
            },
            {
                "id": 2,
                "title": "Test Product 2",
                "price": 20.0,
                "category": "Books",
                "rating": 3.8,
                "stock": 50,
                "discountPercentage": 5.0,
                "brand": "AnotherBrand",
                "availabilityStatus": "out_of_stock"
            }
        ]

    def test_clean_product_data(self):
        """Test that data cleaning works correctly."""
        # Add some messy data
        messy_products = [
            {
                "id": "1",  # string instead of int
                "title": "  Test Product 1  ",  # extra whitespace
                "price": 10.0,
                "category": " Electronics ",  # extra whitespace
                "rating": 4.5,
                "stock": 100,
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": " IN_STOCK "
            }
        ]

        cleaned = clean_product_data(messy_products)

        self.assertEqual(len(cleaned), 1)
        product = cleaned[0]
        self.assertEqual(product["id"], 1)  # converted to int
        self.assertEqual(product["title"], "Test Product 1")  # trimmed
        self.assertEqual(product["category"], "Electronics")  # trimmed
        self.assertEqual(product["availabilityStatus"], "in_stock")  # lowercased and trimmed

    def test_calculate_inventory_value(self):
        """Test inventory value calculation."""
        self.assertEqual(calculate_inventory_value(10.0, 5), 50.0)
        self.assertEqual(calculate_inventory_value(0.0, 100), 0.0)
        self.assertEqual(calculate_inventory_value(15.5, 0), 0.0)

    def test_add_derived_fields(self):
        """Test that derived fields are added correctly."""
        products = [
            {
                "id": 1,
                "title": "Test Product",
                "price": 10.0,
                "category": "Electronics",
                "rating": 4.5,
                "stock": 5,  # low stock
                "discountPercentage": 10.0,
                "brand": "TestBrand",
                "availabilityStatus": "in_stock"
            },
            {
                "id": 2,
                "title": "Test Product 2",
                "price": 20.0,
                "category": "Books",
                "rating": 3.8,
                "stock": 0,  # out of stock
                "discountPercentage": 5.0,
                "brand": "AnotherBrand",
                "availabilityStatus": "out_of_stock"
            }
        ]

        processed = add_derived_fields(products)

        # Check first product (low stock)
        self.assertEqual(processed[0]["inventory_value"], 50.0)  # 10 * 5
        self.assertEqual(processed[0]["stock_status"], "low")

        # Check second product (out of stock)
        self.assertEqual(processed[1]["inventory_value"], 0.0)  # 20 * 0
        self.assertEqual(processed[1]["stock_status"], "out_of_stock")

    def test_create_dataframe(self):
        """Test DataFrame creation."""
        df = create_dataframe(self.sample_products)

        self.assertEqual(len(df), 2)
        self.assertIn("id", df.columns)
        self.assertIn("title", df.columns)
        self.assertIn("inventory_value", df.columns)

        # Check inventory_value calculation
        self.assertEqual(df.iloc[0]["inventory_value"], 1000.0)  # 10.0 * 100
        self.assertEqual(df.iloc[1]["inventory_value"], 1000.0)  # 20.0 * 50

        # Check data types
        self.assertEqual(df["id"].dtype, "int64")
        self.assertEqual(df["price"].dtype, "float64")
        self.assertEqual(df["stock"].dtype, "int64")


if __name__ == "__main__":
    unittest.main()