import os
import unittest
import datetime
import requests
from unittest.mock import Mock, patch

from sqlalchemy.exc import SQLAlchemyError

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
from application.models import Group, Member, Payment, User
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
        self.assertEqual(response.json, {"status": "ok", "database": "ok"})

    def test_health_endpoint_reports_database_failure(self):
        with self.app.app_context():
            with patch.object(
                db.engine, "connect", side_effect=SQLAlchemyError("database down")
            ):
                response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json,
            {"status": "unavailable", "database": "unavailable"},
        )

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

    def add_subscription(self, expiry=None, wallet=100):
        owner = User(chat_id="10001", wallet=0)
        subscriber = User(chat_id="10002", wallet=wallet)
        group = Group(
            chat_id="-100555001",
            admin_id=owner.chat_id,
            cost=20,
            profit=0,
        )
        db.session.add_all((owner, subscriber, group))
        if expiry is not None:
            db.session.add(
                Member(
                    chat_id=subscriber.chat_id,
                    group_chat_id=group.chat_id,
                    expiry=str(expiry),
                )
            )
        db.session.commit()
        return owner, subscriber, group

    def remove_subscription_records(self):
        db.session.query(Member).filter_by(chat_id="10002").delete()
        db.session.query(Group).filter_by(chat_id="-100555001").delete()
        db.session.query(User).filter(
            User.chat_id.in_(("10001", "10002"))
        ).delete(synchronize_session=False)
        db.session.commit()

    def remove_payment_records(self):
        db.session.query(Payment).filter(
            Payment.user_chat_id == "987654"
        ).delete(synchronize_session=False)
        db.session.commit()

    @patch.object(routes.bot, "unban_chat_member")
    @patch.object(routes, "profit")
    def test_subscription_debits_user_and_credits_owner(self, profit, unban):
        with self.app.app_context():
            owner, subscriber, group = self.add_subscription()
            try:
                result = routes.subscribe_user(
                    subscriber.chat_id, group.chat_id
                )

                self.assertEqual(result, 1)
                self.assertEqual(subscriber.wallet, 80)
                self.assertEqual(owner.wallet, 2)
                self.assertEqual(group.profit, 2)
                unban.assert_called_once()
                profit.assert_called_once_with(18)
            finally:
                self.remove_subscription_records()

    @patch.object(routes.bot, "unban_chat_member")
    @patch.object(routes, "profit")
    def test_insufficient_balance_does_not_charge(self, profit, unban):
        with self.app.app_context():
            owner, subscriber, group = self.add_subscription(wallet=10)
            try:
                result = routes.subscribe_user(
                    subscriber.chat_id, group.chat_id
                )

                self.assertEqual(result, 2)
                self.assertEqual(subscriber.wallet, 10)
                self.assertEqual(owner.wallet, 0)
                profit.assert_not_called()
            finally:
                self.remove_subscription_records()

    @patch.object(routes.bot, "send_message")
    @patch.object(routes.bot, "get_chat", return_value=Mock(title="Test group"))
    @patch.object(routes, "profit")
    def test_daily_task_renews_expiry_and_charges_once(
        self, profit, get_chat, send_message
    ):
        today = datetime.date.today()
        with self.app.app_context():
            owner, subscriber, group = self.add_subscription(expiry=today)
            try:
                response = self.client.post(
                    "/triggerdailytasks",
                    headers={"Authorization": "Bearer test-daily-token"},
                )

                member = db.session.query(Member).filter_by(
                    chat_id=subscriber.chat_id
                ).one()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    member.expiry,
                    str(today + datetime.timedelta(days=30)),
                )
                self.assertEqual(subscriber.wallet, 80)
                self.assertEqual(owner.wallet, 2)

                second_response = self.client.post(
                    "/triggerdailytasks",
                    headers={"Authorization": "Bearer test-daily-token"},
                )

                self.assertEqual(second_response.status_code, 200)
                self.assertEqual(subscriber.wallet, 80)
                self.assertEqual(owner.wallet, 2)
                get_chat.assert_called_once()
                profit.assert_called_once_with(18)
            finally:
                self.remove_subscription_records()

    @patch.object(routes.bot, "ban_chat_member")
    def test_unsubscribe_removes_membership(self, ban):
        with self.app.app_context():
            _, subscriber, group = self.add_subscription(expiry="2099-01-01")
            try:
                result = routes.unsubscribe_user(
                    subscriber.chat_id, group.chat_id
                )

                self.assertTrue(result)
                self.assertIsNone(
                    db.session.query(Member).filter_by(
                        chat_id=subscriber.chat_id,
                        group_chat_id=group.chat_id,
                    ).first()
                )
                ban.assert_called_once()
            finally:
                self.remove_subscription_records()

    @patch.object(routes.bot, "send_message")
    @patch.object(routes.client.charge, "retrieve")
    @patch.object(routes.Webhook, "construct_event")
    def test_confirmed_mock_payment_credits_user(
        self, construct_event, retrieve_charge, send_message
    ):
        event = Mock(type="charge:confirmed")
        event.data.code = "mock-charge"
        construct_event.return_value = event
        charge = Mock(
            description="Deposit-987654",
            metadata={"payment_reference": "test-payment-reference"},
        )
        charge.payments = [Mock(net=Mock(local=Mock(amount="12.50")))]
        retrieve_charge.return_value = charge

        with self.app.app_context():
            user = User(chat_id="987654", wallet=0)
            payment = Payment(
                idempotency_key="test-payment-reference",
                charge_code="mock-charge",
                user_chat_id=user.chat_id,
                status="pending",
            )
            db.session.add(user)
            db.session.add(payment)
            db.session.commit()

            try:
                headers = {"X-CC-Webhook-Signature": "mock-signature"}
                response = self.client.post(
                    "/coinbase-webhook", data="{}", headers=headers
                )
                duplicate = self.client.post(
                    "/coinbase-webhook", data="{}", headers=headers
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(duplicate.status_code, 200)
                self.assertEqual(db.session.get(User, "987654").wallet, 12.5)
                self.assertEqual(
                    db.session.get(Payment, payment.id).status, "processed"
                )
                self.assertEqual(db.session.get(Payment, payment.id).amount, 12.5)
                retrieve_charge.assert_called_once_with("mock-charge")
                send_message.assert_called_once()
            finally:
                self.remove_payment_records()
                db.session.delete(db.session.get(User, "987654"))
                db.session.commit()

    @patch.object(routes.bot, "send_message")
    @patch.object(routes.client.charge, "retrieve")
    @patch.object(routes.Webhook, "construct_event")
    def test_webhook_correlates_charge_by_payment_metadata(
        self, construct_event, retrieve_charge, send_message
    ):
        event = Mock(type="charge:confirmed")
        event.data.code = "recovered-charge"
        construct_event.return_value = event
        charge = Mock(metadata={"payment_reference": "uncertain-payment"})
        charge.payments = [Mock(net=Mock(local=Mock(amount="7.25")))]
        retrieve_charge.return_value = charge

        with self.app.app_context():
            user = User(chat_id="987654", wallet=0)
            payment = Payment(
                idempotency_key="uncertain-payment",
                user_chat_id=user.chat_id,
                status="pending",
            )
            db.session.add_all((user, payment))
            db.session.commit()
            payment_id = payment.id

            try:
                response = self.client.post(
                    "/coinbase-webhook",
                    data="{}",
                    headers={"X-CC-Webhook-Signature": "mock-signature"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(db.session.get(User, "987654").wallet, 7.25)
                self.assertEqual(
                    db.session.get(Payment, payment_id).charge_code,
                    "recovered-charge",
                )
                self.assertEqual(
                    db.session.get(Payment, payment_id).status, "processed"
                )
                send_message.assert_called_once()
            finally:
                self.remove_payment_records()
                db.session.delete(db.session.get(User, "987654"))
                db.session.commit()

class CreateDepositChargeTests(unittest.TestCase):
    @patch("application.payments_api.requests.post")
    def test_creates_charge_with_json_and_returns_hosted_url(self, post):
        response = Mock()
        response.status_code = 201
        response.json.return_value = {
            "data": {
                "code": "mock-charge",
                "hosted_url": "https://commerce.example/charge",
            }
        }
        post.return_value = response

        result = payments_api.create_deposit_charge(123, "attempt-123")

        self.assertEqual(
            result, ("mock-charge", "https://commerce.example/charge")
        )
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.commerce.coinbase.com/charges")
        self.assertEqual(kwargs["json"]["description"], "Deposit-123")
        self.assertEqual(
            kwargs["json"]["metadata"],
            {"payment_reference": "attempt-123", "user_chat_id": "123"},
        )
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["timeout"], 15)

    @patch("application.payments_api.requests.post")
    def test_raises_for_unauthorized_api_key(self, post):
        response = Mock(status_code=401)
        response.raise_for_status.side_effect = requests.HTTPError("unauthorized")
        post.return_value = response

        with self.assertRaisesRegex(requests.HTTPError, "unauthorized"):
            payments_api.create_deposit_charge(123, "attempt-unauthorized")

    @patch("application.payments_api.requests.post")
    def test_raises_for_other_http_errors(self, post):
        response = Mock(status_code=500)
        response.raise_for_status.side_effect = RuntimeError("server error")
        post.return_value = response

        with self.assertRaisesRegex(RuntimeError, "server error"):
            payments_api.create_deposit_charge(123, "attempt-server-error")


if __name__ == "__main__":
    unittest.main()
