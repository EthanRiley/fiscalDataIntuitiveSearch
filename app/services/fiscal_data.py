"""Thin wrapper around the Fiscal Data Treasury API."""

import requests


class FiscalDataClient:
    # Common endpoints — extend as needed
    DATASET_CATALOG = [
        {
            "id": "debt_to_penny",
            "name": "Debt to the Penny",
            "endpoint": "v2/accounting/od/debt_to_penny",
            "description": "Daily total public debt outstanding.",
        },
        {
            "id": "avg_interest_rates",
            "name": "Average Interest Rates on Treasury Securities",
            "endpoint": "v2/accounting/od/avg_interest_rates",
            "description": "Monthly average interest rates on outstanding Treasury securities.",
        },
        {
            "id": "mts_table_5",
            "name": "Monthly Treasury Statement – Table 5",
            "endpoint": "v1/accounting/mts/mts_table_5",
            "description": "Budget results by month.",
        },
        {
            "id": "dts_table_1",
            "name": "Daily Treasury Statement – Table 1",
            "endpoint": "v1/accounting/dts/dts_table_1",
            "description": "Operating cash balance of the Federal Government.",
        },
        {
            "id": "treasury_offset",
            "name": "Treasury Offset Program",
            "endpoint": "v2/accounting/od/treasury_offset_program",
            "description": "Collections through the Treasury Offset Program.",
        },
    ]

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def fetch(self, endpoint: str, params: dict | None = None) -> tuple[dict | None, str | None]:
        """
        Query a Fiscal Data endpoint.

        Returns (data_dict, None) on success or (None, error_message) on failure.
        """
        url = f"{self.base_url}/{endpoint}"
        params = params or {}
        params.setdefault("page[size]", "100")

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json(), None
        except requests.RequestException as exc:
            return None, str(exc)
