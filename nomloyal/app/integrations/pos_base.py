"""POS connector interface.

A connector turns another POS system's data into rows in NomLoyal's sales CSV format
(see app.services.import_service.TEMPLATES['sales']); the import service then validates, de-duplicates,
reconciles and imports them exactly like a CSV file. See docs/POS_CONNECTOR_GUIDE.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class POSConnector(ABC):
    name: str = "connector"
    description: str = ""

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """(ok, message) - must not change any data."""

    @abstractmethod
    def fetch_sales_rows(self) -> list[dict]:
        """Rows with the keys of the sales import template (one row per sold item)."""
