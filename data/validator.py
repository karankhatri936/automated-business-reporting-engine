"""Data validation utilities for the reporting engine."""

from typing import List, Dict, Any
from ..utils.exceptions import DataValidationError


def validate_product_data(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate product data for missing fields, invalid types, and bad values.

    Checks for:
    - Missing required fields
    - Invalid types
    - Missing values (None or empty string)
    - Negative price/stock
    - Invalid numeric ranges
    - Malformed records

    Args:
        products: List of product dictionaries from API

    Returns:
        Validated product list (unchanged if valid)

    Raises:
        DataValidationError: If invalid data is found
    """
    # ``brand`` is intentionally NOT required: the live API omits it for a
    # large share of products and the processor defaults it to "Unknown".
    required_fields = [
        "id", "title", "price", "category", "rating",
        "stock", "discountPercentage", "availabilityStatus"
    ]

    numeric_fields = ["price", "rating", "stock", "discountPercentage"]

    # Matched case-insensitively against the API's actual value domain
    # ("In Stock", "Low Stock", "Out of Stock").
    valid_statuses = {"in stock", "low stock", "out of stock", "preorder"}

    invalid_entries = []

    for i, product in enumerate(products):
        errors = []

        # Check for missing fields
        for field in required_fields:
            if field not in product:
                errors.append(f"Missing field: {field}")
                continue

            value = product[field]

            # Check for missing values
            if value is None:
                errors.append(f"Missing value for field: {field}")
                continue

            if isinstance(value, str) and value.strip() == "":
                errors.append(f"Empty value for field: {field}")
                continue

        # If field is present, check types and values
        if "id" in product and product["id"] is not None:
            if not isinstance(product["id"], int):
                errors.append(f"Invalid type for id: expected int, got {type(product['id']).__name__}")

        if "title" in product and product["title"] is not None:
            if not isinstance(product["title"], str):
                errors.append(f"Invalid type for title: expected str, got {type(product['title']).__name__}")

        if "price" in product and product["price"] is not None:
            if not isinstance(product["price"], (int, float)):
                errors.append(f"Invalid type for price: expected numeric, got {type(product['price']).__name__}")
            elif product["price"] < 0:
                errors.append("Negative price value")

        if "category" in product and product["category"] is not None:
            if not isinstance(product["category"], str):
                errors.append(f"Invalid type for category: expected str, got {type(product['category']).__name__}")

        if "rating" in product and product["rating"] is not None:
            if not isinstance(product["rating"], (int, float)):
                errors.append(f"Invalid type for rating: expected numeric, got {type(product['rating']).__name__}")
            elif product["rating"] < 0 or product["rating"] > 5:
                errors.append("Rating out of valid range (0-5)")

        if "stock" in product and product["stock"] is not None:
            if not isinstance(product["stock"], int):
                errors.append(f"Invalid type for stock: expected int, got {type(product['stock']).__name__}")
            elif product["stock"] < 0:
                errors.append("Negative stock value")

        if "discountPercentage" in product and product["discountPercentage"] is not None:
            if not isinstance(product["discountPercentage"], (int, float)):
                errors.append(f"Invalid type for discountPercentage: expected numeric, got {type(product['discountPercentage']).__name__}")
            elif product["discountPercentage"] < 0 or product["discountPercentage"] > 100:
                errors.append("Discount percentage out of valid range (0-100)")

        if "brand" in product and product["brand"] is not None:
            if not isinstance(product["brand"], str):
                errors.append(f"Invalid type for brand: expected str, got {type(product['brand']).__name__}")

        if "availabilityStatus" in product and product["availabilityStatus"] is not None:
            if not isinstance(product["availabilityStatus"], str):
                errors.append(f"Invalid type for availabilityStatus: expected str, got {type(product['availabilityStatus']).__name__}")
            elif product["availabilityStatus"].strip().lower() not in valid_statuses:
                errors.append(
                    f"Invalid availability status: {product['availabilityStatus']}. "
                    f"Valid values (case-insensitive): {sorted(valid_statuses)}"
                )

        if errors:
            invalid_entries.append((i, errors))

    if invalid_entries:
        error_details = "; ".join(
            f"Entry {i}: {', '.join(errors)}"
            for i, errors in invalid_entries
        )
        raise DataValidationError(f"Data validation failed: {error_details}")

    return products