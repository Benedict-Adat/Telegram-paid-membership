import os
import unittest
from unittest.mock import Mock, patch

os.environ.update(
    {
        "TELEGRAM_BOT_TOKEN": "123456:TEST",
        "TELEGRAM_BOT_USERNAME": "test_bot",
        "FLASK_SECRET_KEY": "test-secret",
        "TELEGRAM_WEBHOOK_SECRET": "test-telegram-secret",
        "TELEGRAM_WEBHOOK_URL": "",
        "TELEGRAM_WEBHOOK_PATH": "/telegram-webhook",
        "COINBASE_API_KEY": "test-api-key",
        "COINBASE_WEBHOOK_SECRET": "test-coinbase-secret",
        "COINBASE_WEBHOOK_PATH": "/coinbase-webhook",
        "PAYMENT_REDIRECT_URL": "https://example.test/success",
        "PAYMENT_CANCEL_URL": "https://example.test/cancel",
        "ADMIN_CHAT_ID": "123",
        "STORAGE_CHAT_ID": "-100123",
        "PERMISSIONS_PHOTO_ID": "1",
        "PLATFORM_SHARE": "0.1",
        "MIN_WITHDRAWAL_USD": "10",
        "DAILY_TASKS_TOKEN": "test-daily-token",
        "DATABASE_URL": "sqlite://",
    }
)

from application import create_app
from application import db, routes
from application.models import User
from application import payments_api


class ApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_health_endpoint(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})

    def test_payment_redirect_endpoints(self):
        success = self.client.get("/payment-success")
        cancel = self.client.get("/payment-cancel")

        self.assertEqual(success.status_code, 200)
        self.assertIn("Coinbase Commerce", success.json["message"])
        self.assertEqual(cancel.status_code, 200)

    def test_webhooks_and_daily_task_require_authentication(self):
        telegram = self.client.post(
            "/telegram-webhook",
            data="{}",
            content_type="application/json",
        )
        coinbase = self.client.post("/coinbase-webhook", data="{}")
        daily = self.client.post("/triggerdailytasks")

        self.assertEqual(telegram.status_code, 403)
        self.assertEqual(coinbase.status_code, 400)
        self.assertEqual(daily.status_code, 401)

    @patch.object(routes.bot, "set_webhook", return_value=True)
    def test_render_hostname_registers_telegram_webhook(self, set_webhook):
        with patch.dict(
            os.environ, {"RENDER_EXTERNAL_URL": "https://membership.onrender.com"}
        ):
            app = create_app()

        set_webhook.assert_called_once_with(
            url="https://membership.onrender.com/telegram-webhook",
            secret_token="test-telegram-secret",
        )
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    @patch.object(routes.bot, "send_message")
    @patch.object(routes.client.charge, "retrieve")
    @patch.object(routes.Webhook, "construct_event")
    def test_confirmed_mock_payment_credits_user(
        self, construct_event, retrieve_charge, send_message
    ):
        event = Mock(type="charge:confirmed")
        event.data.code = "mock-charge"
        construct_event.return_value = event
        charge = Mock(description="Deposit-987654")
        charge.payments = [Mock(net=Mock(local=Mock(amount="12.50")))]
        retrieve_charge.return_value = charge

        with self.app.app_context():
            user = User(chat_id="987654", wallet=0)
            db.session.add(user)
            db.session.commit()

            response = self.client.post(
                "/coinbase-webhook",
                data="{}",
                headers={"X-CC-Webhook-Signature": "mock-signature"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                db.session.get(User, "987654").wallet,
                12.5,
            )
            db.session.delete(db.session.get(User, "987654"))
            db.session.commit()

class CreateDepositChargeTests(unittest.TestCase):
    @patch("application.payments_api.requests.post")
    def test_creates_charge_with_json_and_returns_hosted_url(self, post):
        response = Mock()
        response.status_code = 201
        response.json.return_value = {
            "data": {"hosted_url": "https://commerce.example/charge"}
        }
        post.return_value = response

        result = payments_api.create_deposit_charge(123)

        self.assertEqual(result, "https://commerce.example/charge")
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.commerce.coinbase.com/charges")
        self.assertEqual(kwargs["json"]["description"], "Deposit-123")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["timeout"], 15)

    @patch("application.payments_api.requests.post")
    def test_returns_false_for_unauthorized_api_key(self, post):
        post.return_value = Mock(status_code=401)

        self.assertFalse(payments_api.create_deposit_charge(123))

    @patch("application.payments_api.requests.post")
    def test_raises_for_other_http_errors(self, post):
        response = Mock(status_code=500)
        response.raise_for_status.side_effect = RuntimeError("server error")
        post.return_value = response

        with self.assertRaisesRegex(RuntimeError, "server error"):
            payments_api.create_deposit_charge(123)


if __name__ == "__main__":
    unittest.main()
