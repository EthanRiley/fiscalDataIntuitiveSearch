from flask import Blueprint, render_template, request, current_app, jsonify, abort
from app.services.agent_service import AgentService
from app.services.fiscal_data import FiscalDataClient
from app.services import token_logger

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Landing page with dataset browser and agent chat widget."""
    return render_template("index.html")


@main_bp.route("/dashboard")
def dashboard():
    """Interactive Plotly dashboard for a selected dataset."""
    return render_template("dashboard.html")


@main_bp.route("/chat", methods=["GET", "POST"])
def chat():
    """Agent-driven chart + blurb page."""
    question = None
    result = None
    error = None
    session_id = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            service = AgentService(current_app.config)
            spec, session_id = service.build_chart_spec(question)

            if "error" in spec:
                error = spec["error"]
            else:
                client = FiscalDataClient(current_app.config["FISCAL_DATA_BASE_URL"])
                params = {
                    "sort": spec.get("sort", "record_date"),
                    "page[size]": "10000",
                }
                if spec.get("filters"):
                    params["filter"] = spec["filters"]

                data, fetch_error = client.fetch(spec["endpoint"], params)
                if fetch_error:
                    error = fetch_error
                else:
                    records = data.get("data", [])
                    result = {
                        "blurb": spec.get("blurb", ""),
                        "x_column": spec.get("x_column", ""),
                        "y_column": spec.get("y_column", ""),
                        "records": records,
                    }

    return render_template("chat.html", question=question, result=result, error=error, session_id=session_id)


@main_bp.route("/admin")
def admin():
    """Admin page listing all user prompt sessions."""
    sessions = token_logger.get_sessions()
    stats = token_logger.get_stats()
    return render_template("admin/index.html", sessions=sessions, stats=stats)


@main_bp.route("/admin/prompt/<session_id>")
def admin_prompt(session_id):
    """Detail view for a single prompt session."""
    session = token_logger.get_session(session_id)
    if session is None:
        abort(404)
    return render_template("admin/prompt.html", session=session)


@main_bp.route("/admin/stats")
def stats():
    """Token usage stats as JSON."""
    return jsonify(token_logger.get_stats())
