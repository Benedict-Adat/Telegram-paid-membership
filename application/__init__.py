import os

from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app():
    """Construct the Flask application and initialize its database."""
    from config import Config

    Config.validate()
    server = Flask(__name__, instance_relative_config=True)
    server.config.from_object(Config)
    os.makedirs(server.instance_path, exist_ok=True)
    db.init_app(server)

    from . import routes

    server.register_blueprint(routes.blueprint)
    server.add_url_rule(
        "/healthz",
        endpoint="health",
        view_func=lambda: jsonify(status="ok"),
        methods=["GET"],
    )
    server.add_url_rule(
        "/payment-success",
        endpoint="payment_success",
        view_func=lambda: jsonify(
            message="Payment confirmation is processed by Coinbase Commerce."
        ),
        methods=["GET"],
    )
    server.add_url_rule(
        "/payment-cancel",
        endpoint="payment_cancel",
        view_func=lambda: jsonify(message="Payment was not completed."),
        methods=["GET"],
    )

    with server.app_context():
        db.create_all()

    webhook_url = Config.TELEGRAM_WEBHOOK_URL
    if not webhook_url:
        render_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        if render_url:
            from .data import telegram_webhook_path

            webhook_url = f"{render_url}{telegram_webhook_path}"

    if webhook_url:
        webhook_set = routes.bot.set_webhook(
            url=webhook_url,
            secret_token=Config.TELEGRAM_WEBHOOK_SECRET,
        )
        if not webhook_set:
            raise RuntimeError("Telegram rejected the configured webhook")

    return server
