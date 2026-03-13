from flask import Blueprint, jsonify, request, current_app, Response, stream_with_context
from app.services.agent_service import AgentService

agent_bp = Blueprint("agent", __name__)


@agent_bp.route("/chat", methods=["POST"])
def chat():
    """
    Accept a user message and return an agent response.

    Body JSON:
        message  – user's natural-language question
        history  – list of prior {role, content} turns (optional)
    """
    body = request.get_json(silent=True) or {}
    message = body.get("message", "")
    history = body.get("history", [])

    if not message:
        return jsonify({"error": "message is required"}), 400

    service = AgentService(current_app.config)
    reply = service.answer(message, history)
    return jsonify(reply)


@agent_bp.route("/chat/stream", methods=["POST"])
def chat_stream():
    """
    SSE streaming variant — returns token-by-token responses.
    """
    body = request.get_json(silent=True) or {}
    message = body.get("message", "")
    history = body.get("history", [])

    if not message:
        return jsonify({"error": "message is required"}), 400

    service = AgentService(current_app.config)

    def generate():
        for chunk in service.answer_stream(message, history):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
    )
