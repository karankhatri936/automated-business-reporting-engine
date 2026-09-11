"""KPI engine — reusable business analytics calculations."""

from typing import Dict, Any
import pandas as pd
from ..utils.logger import setup_logger

logger = setup_logger(__name__)


class KPIEngine:
    """Calculates business KPIs from a cleaned product DataFrame."""

    def __init__(self, df: pd.DataFrame):
        """
        Initialize the KPI engine.

        Args:
            df: Cleaned product DataFrame with inventory_value column.
        """
        self.df = df
        self._kpis: Dict[str, Any] = {}

    def calculate_all(self) -> Dict[str, Any]:
        """
        Calculate every KPI and return a structured dict.

        Returns:
            Nested dict with keys: general, category, products.
        """
        logger.info("Calculating KPIs")
        self._kpis = {
            "general": self._general_kpis(),
            "category": self._category_kpis(),
            "products": self._product_analysis(),
        }
        return self._kpis

    # ── General KPIs ──────────────────────────────────────────────

    def _general_kpis(self) -> Dict[str, Any]:
        return {
            "total_products": len(self.df),
            "average_price": round(float(self.df["price"].mean()), 2),
            "median_price": round(float(self.df["price"].median()), 2),
            "total_inventory_units": int(self.df["stock"].sum()),
            "average_stock_per_product": round(float(self.df["stock"].mean()), 2),
            "total_inventory_value": round(float(self.df["inventory_value"].sum()), 2),
            "average_rating": round(float(self.df["rating"].mean()), 2),
            "average_discount": round(float(self.df["discountPercentage"].mean()), 2),
            "low_stock_count": int((self.df["stock_status"] == "low").sum()),
        }

    # ── Category KPIs ─────────────────────────────────────────────

    def _category_kpis(self) -> pd.DataFrame:
        grouped = self.df.groupby("category").agg(
            product_count=("id", "count"),
            average_price=("price", "mean"),
            average_rating=("rating", "mean"),
            total_stock=("stock", "sum"),
            inventory_value=("inventory_value", "sum"),
            average_discount=("discountPercentage", "mean"),
        ).reset_index()

        for col in ["average_price", "average_rating", "inventory_value", "average_discount"]:
            grouped[col] = grouped[col].round(2)

        grouped["total_stock"] = grouped["total_stock"].astype(int)
        grouped["product_count"] = grouped["product_count"].astype(int)

        return grouped

    # ── Product Analysis ──────────────────────────────────────────

    def _product_analysis(self) -> Dict[str, pd.DataFrame]:
        return {
            "top_by_inventory_value": self.df.nlargest(10, "inventory_value")[
                ["id", "title", "price", "stock", "inventory_value", "category"]
            ],
            "top_by_price": self.df.nlargest(10, "price")[
                ["id", "title", "price", "category", "inventory_value"]
            ],
            "top_by_rating": self.df.nlargest(10, "rating")[
                ["id", "title", "rating", "category", "inventory_value"]
            ],
            "lowest_stock": self.df.nsmallest(10, "stock")[
                ["id", "title", "stock", "category", "inventory_value"]
            ],
            "top_discounted": self.df.nlargest(10, "discountPercentage")[
                ["id", "title", "discountPercentage", "category", "inventory_value"]
            ],
        }
