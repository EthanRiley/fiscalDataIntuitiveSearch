from flask import Blueprint, jsonify, request, current_app
from app.services.fiscal_data import FiscalDataClient

api_bp = Blueprint("api", __name__)


@api_bp.route("/datasets")
def list_datasets():
    """Return the catalog of available Fiscal Data endpoints."""
    return jsonify(FiscalDataClient.DATASET_CATALOG)


@api_bp.route("/query")
def query_dataset():
    """
    Proxy a query to the Fiscal Data API.

    Query params:
        endpoint  – e.g. v2/accounting/od/debt_to_penny
        fields    – comma-separated field names (optional)
        sort      – e.g. -record_date (optional)
        page[size]– number of records (optional, default 100)
        filter    – Fiscal Data filter expression (optional)
    """
    client = FiscalDataClient(current_app.config["FISCAL_DATA_BASE_URL"])
    endpoint = request.args.get("endpoint", "")
    params = {k: v for k, v in request.args.items() if k != "endpoint"}
    data, error = client.fetch(endpoint, params)
    if error:
        return jsonify({"error": error}), 502
    return jsonify(data)
