from flask import Blueprint, render_template, request, current_app, jsonify, abort
from app.services.agent_service import AgentService
from app.services.fiscal_data import FiscalDataClient
from app.services.data_utils import filter_by_periodicity
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
    """Agent-driven multi-chart page."""
    question = None
    charts = []
    blurb = None
    api_calls = []
    error = None
    session_id = None

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            service = AgentService(current_app.config)
            specs, session_id = service.build_chart_specs(question)

            if specs and "error" in specs[0]:
                error = specs[0]["error"]
            else:
                client = FiscalDataClient(current_app.config["FISCAL_DATA_BASE_URL"])
                summaries = []

                for spec in specs:
                    # ── Visualization fetch ──────────────────────
                    viz_params = {
                        "sort": spec.get("viz_sort", "record_date"),
                        "page[size]": "10000",
                    }
                    if spec.get("viz_filters"):
                        viz_params["filter"] = spec["viz_filters"]

                    viz_data, viz_error = client.fetch(spec["endpoint"], viz_params)

                    api_calls.append({
                        "label": spec.get("title", spec["endpoint"]),
                        "endpoint": spec["endpoint"],
                        "params": viz_params,
                    })

                    if viz_error:
                        continue

                    viz_records = viz_data.get("data", [])

                    # ── Filter viz data by periodicity for analyst ──
                    periodicity = spec.get("periodicity", "year")
                    analysis_records = filter_by_periodicity(
                        viz_records, spec.get("x_column", "record_date"), periodicity
                    )

                    summaries.append({
                        "title": spec.get("title", spec["endpoint"]),
                        "records": analysis_records,
                    })

                    charts.append({
                        "title": spec.get("title", ""),
                        "x_column": spec.get("x_column", ""),
                        "y_column": spec.get("y_column", ""),
                        "records": viz_records,
                    })

                if summaries:
                    blurb = service.build_analysis(question, summaries, session_id)

    return render_template(
        "chat.html",
        question=question,
        charts=charts,
        blurb=blurb,
        api_calls=api_calls,
        error=error,
        session_id=session_id,
    )


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
