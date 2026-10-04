import os
import math
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

database_url = os.getenv("DATABASE_URL", "sqlite:///membership.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)

class Config:
    """Flask settings sourced from the process environment."""

    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "")
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL", "").rstrip("/")
    TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")

    @classmethod
    def validate(cls):
        public_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
        required = {
            "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN"),
            "TELEGRAM_BOT_USERNAME": os.getenv("TELEGRAM_BOT_USERNAME"),
            "FLASK_SECRET_KEY": cls.SECRET_KEY,
            "PLATFORM_SHARE": os.getenv("PLATFORM_SHARE"),
            "MIN_WITHDRAWAL_USD": os.getenv("MIN_WITHDRAWAL_USD"),
            "ADMIN_CHAT_ID": os.getenv("ADMIN_CHAT_ID"),
            "COINBASE_API_KEY": os.getenv("COINBASE_API_KEY"),
            "COINBASE_WEBHOOK_SECRET": os.getenv("COINBASE_WEBHOOK_SECRET"),
            "TELEGRAM_WEBHOOK_SECRET": cls.TELEGRAM_WEBHOOK_SECRET,
            "DAILY_TASKS_TOKEN": os.getenv("DAILY_TASKS_TOKEN"),
            "PAYMENT_REDIRECT_URL": os.getenv("PAYMENT_REDIRECT_URL")
            or (f"{public_url}/payment-success" if public_url else None),
            "PAYMENT_CANCEL_URL": os.getenv("PAYMENT_CANCEL_URL")
            or (f"{public_url}/payment-cancel" if public_url else None),
            "STORAGE_CHAT_ID": os.getenv("STORAGE_CHAT_ID"),
            "PERMISSIONS_PHOTO_ID": os.getenv("PERMISSIONS_PHOTO_ID"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(
                "Missing required environment variables: " + ", ".join(missing)
            )
        try:
            share = float(required["PLATFORM_SHARE"])
            minimum = float(required["MIN_WITHDRAWAL_USD"])
        except ValueError as exc:
            raise RuntimeError(
                "PLATFORM_SHARE and MIN_WITHDRAWAL_USD must be numbers"
            ) from exc
        if not math.isfinite(share):
            raise RuntimeError("PLATFORM_SHARE must be finite")
        if not 0 <= share <= 1:
            raise RuntimeError("PLATFORM_SHARE must be between 0 and 1")
        if not math.isfinite(minimum) or minimum < 0:
            raise RuntimeError(
                "MIN_WITHDRAWAL_USD must be finite and nonnegative"
            )
        for name in ("ADMIN_CHAT_ID", "STORAGE_CHAT_ID", "PERMISSIONS_PHOTO_ID"):
            try:
                value = int(required[name])
            except ValueError as exc:
                raise RuntimeError(f"{name} must be an integer") from exc
            if value == 0:
                raise RuntimeError(f"{name} cannot be zero")

        webhook_secret = cls.TELEGRAM_WEBHOOK_SECRET
        if (
            not 1 <= len(webhook_secret) <= 256
            or any(
                char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for char in webhook_secret
            )
        ):
            raise RuntimeError(
                "TELEGRAM_WEBHOOK_SECRET must be 1-256 letters, digits, '_' or '-'"
            )

        if cls.TELEGRAM_WEBHOOK_URL:
            parsed_url = urlparse(cls.TELEGRAM_WEBHOOK_URL)
            if parsed_url.scheme != "https" or not parsed_url.netloc:
                raise RuntimeError("TELEGRAM_WEBHOOK_URL must be an HTTPS URL")
