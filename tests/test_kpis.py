"""Tests for KPI calculations."""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pandas as pd
from automated_business_reporting_engine.analytics.kpis import KPIEngine


class TestKPIEngine(unittest.TestCase):
    """Test suite for KPIEngine."""

    def setUp(self):
        """Set up test data."""
        # Create a sample DataFrame similar to what processor would produce
        self.test_data = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'title': ['Product 1', 'Product 2', 'Product 3', 'Product 4', 'Product 5'],
            'price': [10.0, 20.0, 15.0, 30.0, 25.0],
            'category': ['Electronics', 'Books', 'Electronics', 'Clothing', 'Books'],
            'rating': [4.5, 3.8, 4.2, 4.0, 4.7],
            'stock': [100, 0, 5, 50, 200],  # includes out_of_stock (0) and low (5)
            'discountPercentage': [10.0, 5.0, 15.0, 20.0, 0.0],
            'brand': ['BrandA', 'BrandB', 'BrandA', 'BrandC', 'BrandB'],
            'availabilityStatus': ['in_stock', 'out_of_stock', 'in_stock', 'in_stock', 'in_stock'],
            'stock_status': ['medium', 'out_of_stock', 'low', 'medium', 'high'],
            'inventory_value': [1000.0, 0.0, 75.0, 1500.0, 5000.0]  # price * stock
        })

    def test_kpi_engine_initialization(self):
        """Test that KPIEngine initializes correctly."""
        engine = KPIEngine(self.test_data)
        self.assertIsInstance(engine, KPIEngine)
        pd.testing.assert_frame_equal(engine.df, self.test_data)

    def test_calculate_all_returns_dict(self):
        """Test that calculate_all returns a properly structured dict."""
        engine = KPIEngine(self.test_data)
        result = engine.calculate_all()
        
        # Check top-level keys
        self.assertIn('general', result)
        self.assertIn('category', result)
        self.assertIn('products', result)
        
        # Check that category returns DataFrame
        self.assertIsInstance(result['category'], pd.DataFrame)
        
        # Check that products returns dict of DataFrames
        self.assertIsInstance(result['products'], dict)
        for key, df in result['products'].items():
            self.assertIsInstance(df, pd.DataFrame)

    def test_general_kpis(self):
        """Test general KPI calculations."""
        engine = KPIEngine(self.test_data)
        general = engine._general_kpis()
        
        # Check values
        self.assertEqual(general['total_products'], 5)
        self.assertAlmostEqual(general['average_price'], 20.0, places=2)  # (10+20+15+30+25)/5
        self.assertEqual(general['median_price'], 20.0)  # sorted: 10,15,20,25,30 -> median 20
        self.assertEqual(general['total_inventory_units'], 355)  # 100+0+5+50+200
        self.assertAlmostEqual(general['average_stock_per_product'], 71.0, places=2)  # 355/5
        self.assertAlmostEqual(general['total_inventory_value'], 7575.0, places=2)  # sum of inventory_value column
        self.assertAlmostEqual(general['average_rating'], 4.24, places=2)  # (4.5+3.8+4.2+4.0+4.7)/5
        self.assertAlmostEqual(general['average_discount'], 10.0, places=2)  # (10+5+15+20+0)/5
        self.assertEqual(general['low_stock_count'], 1)  # only product with stock_status == 'low' (id=3)

    def test_category_kpis(self):
        """Test category-level KPI calculations."""
        engine = KPIEngine(self.test_data)
        category_df = engine._category_kpis()
        
        # Should have 3 categories: Books, Clothing, Electronics
        self.assertEqual(len(category_df), 3)
        self.assertIn('category', category_df.columns)
        self.assertIn('product_count', category_df.columns)
        self.assertIn('average_price', category_df.columns)
        self.assertIn('total_stock', category_df.columns)
        self.assertIn('inventory_value', category_df.columns)
        
        # Check Electronics category (2 products: id=1 and id=3)
        electronics = category_df[category_df['category'] == 'Electronics'].iloc[0]
        self.assertEqual(electronics['product_count'], 2)
        self.assertAlmostEqual(electronics['average_price'], 12.5, places=2)  # (10+15)/2
        self.assertEqual(electronics['total_stock'], 105)  # 100+5
        self.assertAlmostEqual(electronics['inventory_value'], 1075.0, places=2)  # 1000+75
        
        # Check Books category (2 products: id=2 and id=5)
        books = category_df[category_df['category'] == 'Books'].iloc[0]
        self.assertEqual(books['product_count'], 2)
        self.assertAlmostEqual(books['average_price'], 22.5, places=2)  # (20+25)/2
        self.assertEqual(books['total_stock'], 200)  # 0+200
        self.assertAlmostEqual(books['inventory_value'], 5000.0, places=2)  # 0+5000

    def test_product_analysis(self):
        """Test product analysis (top products)."""
        engine = KPIEngine(self.test_data)
        product_analysis = engine._product_analysis()
        
        # Check each analysis type exists
        expected_keys = ['top_by_inventory_value', 'top_by_price', 'top_by_rating', 
                        'lowest_stock', 'top_discounted']
        for key in expected_keys:
            self.assertIn(key, product_analysis)
            self.assertIsInstance(product_analysis[key], pd.DataFrame)
        
        # Check top_by_inventory_value (should be id=5 first with 5000)
        top_value = product_analysis['top_by_inventory_value']
        self.assertEqual(len(top_value), 5)  # all 5 products since we ask for top 10 but only have 5
        self.assertEqual(top_value.iloc[0]['id'], 5)  # highest inventory_value
        
        # Check top_by_price (should be id=4 first with 30.0)
        top_price = product_analysis['top_by_price']
        self.assertEqual(top_price.iloc[0]['id'], 4)  # highest price
        
        # Check top_by_rating (should be id=5 first with 4.7)
        top_rating = product_analysis['top_by_rating']
        self.assertEqual(top_rating.iloc[0]['id'], 5)  # highest rating
        
        # Check lowest_stock (should be id=2 first with stock 0)
        lowest_stock = product_analysis['lowest_stock']
        self.assertEqual(lowest_stock.iloc[0]['id'], 2)  # lowest stock
        
        # Check top_discounted (should be id=4 first with 20.0 discount)
        top_discounted = product_analysis['top_discounted']
        self.assertEqual(top_discounted.iloc[0]['id'], 4)  # highest discount


if __name__ == '__main__':
    unittest.main()