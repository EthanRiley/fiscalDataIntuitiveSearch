from flask import Flask
from app.config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Register blueprints ──────────────────────────────────
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    from app.routes.agent import agent_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(agent_bp, url_prefix="/agent")

    return app
