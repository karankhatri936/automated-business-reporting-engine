"""Tests for Excel and PDF report generation."""

import os
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from automated_business_reporting_engine.analytics.kpis import KPIEngine
from automated_business_reporting_engine.config import OutputConfig
from automated_business_reporting_engine.reports.excel_report import (
    ExcelReportGenerator,
    REPORT_VERSION,
    generate_excel_report,
)
from automated_business_reporting_engine.reports.pdf_report import (
    PDFReportGenerator,
    generate_pdf_report,
)
from automated_business_reporting_engine.utils.exceptions import (
    ExcelReportError,
    PDFReportError,
)


class TestExcelReport(unittest.TestCase):
    """Test suite for Excel report generation."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.excel_dir = Path(cls.temp_dir.name) / "excel"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        """Build a small dataset and compute KPIs the same way production does."""
        self.df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'title': ['Product 1', 'Product 2', 'Product 3', 'Product 4', 'Product 5'],
            'price': [10.0, 20.0, 15.0, 30.0, 25.0],
            'category': ['Electronics', 'Books', 'Electronics', 'Clothing', 'Books'],
            'rating': [4.5, 3.8, 4.2, 4.0, 4.7],
            'stock': [100, 0, 5, 50, 200],
            'discountPercentage': [10.0, 5.0, 15.0, 20.0, 0.0],
            'brand': ['BrandA', 'BrandB', 'BrandA', 'BrandC', 'BrandB'],
            'availabilityStatus': ['in_stock', 'out_of_stock', 'in_stock', 'in_stock', 'in_stock'],
            'stock_status': ['medium', 'out_of_stock', 'low', 'medium', 'high'],
            'inventory_value': [1000.0, 0.0, 75.0, 1500.0, 5000.0],
        })
        self.kpis = KPIEngine(self.df).calculate_all()
        self.metadata = {"api_source": "https://dummyjson.com/products"}
        self.generator = ExcelReportGenerator(OutputConfig(excel_dir=self.excel_dir))

    def test_generate_creates_expected_sheets(self):
        """Workbook is created, opens, and contains the five expected sheets."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        self.assertTrue(path.exists())
        self.assertTrue(path.name.endswith(".xlsx"))
        self.assertTrue(re.match(r"Business_Report_\d{4}-\d{2}-\d{2}\.xlsx", path.name))

        wb = load_workbook(path)  # verifying the workbook opens successfully
        self.assertEqual(
            wb.sheetnames,
            ["Dashboard", "Product Data", "Category Analysis", "Product Analysis", "Report Metadata"],
        )

    def test_dashboard_contains_title_and_kpis(self):
        """Dashboard shows the report title and the real KPI values."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        wb = load_workbook(path)
        ws = wb["Dashboard"]

        self.assertEqual(ws["A1"].value, "Business_Report")

        # Locate the KPI row and confirm the value matches the KPI engine.
        found = False
        for row in ws.iter_rows(min_row=1, max_row=20, max_col=2):
            if row[0].value == "Total Inventory Value":
                self.assertAlmostEqual(
                    row[1].value, self.kpis["general"]["total_inventory_value"], places=2
                )
                found = True
                break
        self.assertTrue(found, "KPI 'Total Inventory Value' missing from Dashboard")

        # The source line references the API URL.
        self.assertIn(self.metadata["api_source"], ws["A3"].value)

    def test_dashboard_contains_charts(self):
        """Dashboard contains pie and bar charts."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        wb = load_workbook(path)
        self.assertGreaterEqual(len(wb["Dashboard"]._charts), 2)

    def test_product_data_is_table_with_freeze_panes(self):
        """Product Data is an Excel table with frozen header row."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        wb = load_workbook(path)
        ws = wb["Product Data"]
        self.assertIn("ProductData", ws.tables)
        self.assertEqual(ws.freeze_panes, "A2")
        # Header + all data rows are present.
        self.assertEqual(ws.max_row, len(self.df) + 1)

    def test_category_analysis_contains_category_rows(self):
        """Category Analysis holds per-category metric rows."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        wb = load_workbook(path)
        ws = wb["Category Analysis"]
        self.assertIn("CategoryAnalysis", ws.tables)
        # Electronics appears in the sheet data.
        categories = {
            ws.cell(row=r, column=1).value
            for r in range(2, ws.max_row + 1)
        }
        self.assertIn("Electronics", categories)

    def test_metadata_sheet_contents(self):
        """Metadata sheet lists API source, generation timestamp and record count."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        wb = load_workbook(path)
        ws = wb["Report Metadata"]
        values = {ws.cell(row=r, column=1).value: ws.cell(row=r, column=2).value
                  for r in range(1, ws.max_row + 1)}
        self.assertEqual(values["API Source"], "https://dummyjson.com/products")
        self.assertEqual(values["Number of Records"], len(self.df))
        self.assertEqual(values["Report Version"], REPORT_VERSION)
        self.assertIn(str(datetime.now().year), values["Generation Timestamp"])

    def test_convenience_function_returns_path(self):
        """Module-level generate_excel_report returns the report path."""
        path = generate_excel_report(
            self.df, self.kpis, self.metadata, output_config=OutputConfig(excel_dir=self.excel_dir)
        )
        self.assertTrue(path.exists())
        self.assertTrue(path.suffix == ".xlsx")

    def test_empty_dataframe_raises(self):
        """Generating from an empty DataFrame raises ExcelReportError."""
        with self.assertRaises(ExcelReportError):
            self.generator.generate(pd.DataFrame(), self.kpis, self.metadata)

    def test_missing_kpis_raises(self):
        """Generating without KPI results raises ExcelReportError."""
        with self.assertRaises(ExcelReportError):
            self.generator.generate(self.df, {}, self.metadata)


class TestPDFReport(unittest.TestCase):
    """Test suite for PDF executive report generation."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.pdf_dir = Path(cls.temp_dir.name) / "pdf"

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def setUp(self):
        self.df = pd.DataFrame({
            'id': [1, 2, 3, 4, 5],
            'title': ['Product 1', 'Product 2', 'Product 3', 'Product 4', 'Product 5'],
            'price': [10.0, 20.0, 15.0, 30.0, 25.0],
            'category': ['Electronics', 'Books', 'Electronics', 'Clothing', 'Books'],
            'rating': [4.5, 3.8, 4.2, 4.0, 4.7],
            'stock': [100, 0, 5, 50, 200],
            'discountPercentage': [10.0, 5.0, 15.0, 20.0, 0.0],
            'brand': ['BrandA', 'BrandB', 'BrandA', 'BrandC', 'BrandB'],
            'availabilityStatus': ['in_stock', 'out_of_stock', 'in_stock', 'in_stock', 'in_stock'],
            'stock_status': ['medium', 'out_of_stock', 'low', 'medium', 'high'],
            'inventory_value': [1000.0, 0.0, 75.0, 1500.0, 5000.0],
        })
        self.kpis = KPIEngine(self.df).calculate_all()
        self.metadata = {"api_source": "https://dummyjson.com/products"}
        self.generator = PDFReportGenerator(OutputConfig(pdf_dir=self.pdf_dir))

    def test_generate_creates_valid_pdf(self):
        """PDF is created with the expected name and valid signature."""
        path = self.generator.generate(self.df, self.kpis, self.metadata)
        self.assertTrue(path.exists())
        self.assertTrue(path.name.endswith(".pdf"))
        self.assertTrue(re.match(r"Business_Report_\d{4}-\d{2}-\d{2}\.pdf", path.name))
        # Minimal validity check: %PDF header and non-zero size.
        with open(path, "rb") as pdf_file:
            header = pdf_file.read(5)
            size = len(pdf_file.read())
        self.assertEqual(header, b"%PDF-")
        self.assertGreater(size, 0)

    def test_observations_derived_from_data(self):
        """Observations reference actual numbers from the same KPI results."""
        observations = self.generator._observations(self.df, self.kpis)
        text = " ".join(observations)
        self.assertEqual(observations[0].count(str(self.kpis["general"]["total_products"])), 1)
        # Total products value appears in the opening observation.
        self.assertIn(str(self.kpis["general"]["total_products"]), text)

    def test_convenience_function_returns_path(self):
        """Module-level generate_pdf_report returns the report path."""
        path = generate_pdf_report(
            self.df, self.kpis, self.metadata, output_config=OutputConfig(pdf_dir=self.pdf_dir)
        )
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".pdf")

    def test_empty_dataframe_raises(self):
        """Generating from an empty DataFrame raises PDFReportError."""
        with self.assertRaises(PDFReportError):
            self.generator.generate(pd.DataFrame(), self.kpis, self.metadata)

    def test_missing_kpis_raises(self):
        """Generating without KPI results raises PDFReportError."""
        with self.assertRaises(PDFReportError):
            self.generator.generate(self.df, {}, self.metadata)


if __name__ == "__main__":
    unittest.main()