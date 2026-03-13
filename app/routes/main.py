from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Landing page with dataset browser and agent chat widget."""
    return render_template("index.html")


@main_bp.route("/dashboard")
def dashboard():
    """Interactive Plotly dashboard for a selected dataset."""
    return render_template("dashboard.html")
