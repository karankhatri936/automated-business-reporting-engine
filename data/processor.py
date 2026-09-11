"""Data processing utilities for transforming raw API data."""

from typing import List, Dict, Any
import pandas as pd

from ..utils.logger import setup_logger

logger = setup_logger(__name__)


def clean_product_data(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Clean raw product data by normalizing fields and handling missing values.

    Args:
        products: List of product dictionaries

    Returns:
        Cleaned product list
    """
    cleaned = []

    for product in products:
        cleaned_product = {}

        # Copy and normalize id
        cleaned_product["id"] = int(product.get("id", 0))

        # Copy and clean title
        title = product.get("title", "")
        cleaned_product["title"] = title.strip() if isinstance(title, str) else str(title)

        # Copy numeric fields with defaults
        cleaned_product["price"] = float(product.get("price", 0.0))
        cleaned_product["category"] = str(product.get("category", "Unknown")).strip()
        cleaned_product["rating"] = float(product.get("rating", 0.0))
        cleaned_product["stock"] = int(product.get("stock", 0))
        cleaned_product["discountPercentage"] = float(product.get("discountPercentage", 0.0))
        cleaned_product["brand"] = str(product.get("brand", "Unknown")).strip()
        cleaned_product["availabilityStatus"] = str(product.get("availabilityStatus", "unknown")).strip().lower()

        cleaned.append(cleaned_product)

    logger.info(f"Cleaned {len(cleaned)} product records")
    return cleaned


def calculate_inventory_value(price: float, stock: int) -> float:
    """
    Calculate inventory value for a product.

    Args:
        price: Product price
        stock: Available stock quantity

    Returns:
        Total inventory value (price * stock)
    """
    return price * stock


def add_derived_fields(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Add derived fields to product records.

    Adds:
    - inventory_value = price * stock
    - stock_status = classification based on stock levels

    Args:
        products: List of cleaned product dictionaries

    Returns:
        Products with additional derived fields
    """
    for product in products:
        price = product.get("price", 0.0)
        stock = product.get("stock", 0)

        # Calculate inventory value
        product["inventory_value"] = calculate_inventory_value(price, stock)

        # Determine stock status
        # Using industry thresholds: low < 10, medium 10-100, high > 100
        if stock == 0:
            product["stock_status"] = "out_of_stock"
        elif stock < 10:
            product["stock_status"] = "low"
        elif stock <= 100:
            product["stock_status"] = "medium"
        else:
            product["stock_status"] = "high"

    logger.info(f"Added derived fields to {len(products)} products")
    return products


def create_dataframe(products: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convert product records to a Pandas DataFrame.

    Args:
        products: List of processed product dictionaries

    Returns:
        DataFrame containing all product data
    """
    if not products:
        logger.warning("No products to create DataFrame from")
        return pd.DataFrame()

    df = pd.DataFrame(products)

    # Ensure correct column types
    df["id"] = df["id"].astype(int)
    df["price"] = df["price"].astype(float)
    df["rating"] = df["rating"].astype(float)
    df["stock"] = df["stock"].astype(int)
    df["discountPercentage"] = df["discountPercentage"].astype(float)

    # Calculate inventory_value if not present
    if "inventory_value" not in df.columns:
        df["inventory_value"] = df["price"] * df["stock"]

    logger.info(f"Created DataFrame with {len(df)} rows and {len(df.columns)} columns")
    return df