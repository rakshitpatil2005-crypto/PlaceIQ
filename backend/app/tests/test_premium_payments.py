from collections.abc import Generator
import hashlib
import hmac
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests
from razorpay.errors import SignatureVerificationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.config import settings
from app.database import Base, get_db
from app.models import (
    PremiumAccessRequest,
    PremiumPaymentAttempt,
    PremiumPaymentOrder,
    PremiumPaymentWebhookEvent,
    PremiumSubscription,
    User,
)
from app.routers.premium_router import router as premium_router
from app.services import premium_payments

VALID_SIGNATURE = "a" * 64


class FakeUtility:
    def verify_payment_signature(self, values):
        if values["razorpay_signature"] != VALID_SIGNATURE:
            raise SignatureVerificationError("sensitive SDK message")

    def verify_webhook_signature(self, raw_body, signature, secret):
        expected = hmac.new(
            secret.encode(),
            raw_body.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SignatureVerificationError("sensitive SDK message")


class FakeOrders:
    def __init__(self):
        self.created = []
        self.listed = []
        self.payment_entities = {}

    def create(self, values, **kwargs):
        self.created.append((values, kwargs))
        return {
            "id": f"order_razorpay_{len(self.created)}",
            "amount": values["amount"],
            "currency": values["currency"],
            "receipt": values["receipt"],
            "status": "created",
        }

    def all(self, values, **kwargs):
        self.listed.append((values, kwargs))
        return {"items": []}

    def payments(self, order_id, **kwargs):
        return {"items": self.payment_entities.get(order_id, [])}


class FakePayments:
    def __init__(self):
        self.entities = {}

    def fetch(self, payment_id, **kwargs):
        if payment_id not in self.entities:
            raise AssertionError(f"Unexpected payment fetch: {payment_id}")
        return self.entities[payment_id]


class FakeClient:
    def __init__(self):
        self.order = FakeOrders()
        self.payment = FakePayments()
        self.utility = FakeUtility()


@pytest.fixture
def payment_app(monkeypatch) -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    with factory() as db:
        learner = User(
            name="Payment learner",
            email="payment-learner@example.test",
            hashed_password="hash",
        )
        other = User(
            name="Other learner",
            email="payment-other@example.test",
            hashed_password="hash",
        )
        db.add_all([learner, other])
        db.commit()
        user_ids = {"learner": learner.id, "other": other.id}

    client = FakeClient()
    monkeypatch.setattr(premium_payments.razorpay, "Client", lambda **kwargs: client)
    monkeypatch.setattr(settings, "PREMIUM_AMOUNT_MINOR", 12345)
    monkeypatch.setattr(settings, "PREMIUM_CURRENCY", "INR")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_public")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "server-only-secret")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "webhook-test-secret")

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(premium_router)
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    headers = {
        key: {
            "Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"
        }
        for key, user_id in user_ids.items()
    }
    yield {
        "client": test_client,
        "headers": headers,
        "factory": factory,
        "user_ids": user_ids,
        "provider": client,
    }
    test_client.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _created_order(payment_app: dict, user: str = "learner") -> dict:
    response = payment_app["client"].post(
        "/premium/payment/orders",
        headers=payment_app["headers"][user],
    )
    assert response.status_code == 201
    return response.json()


def _payment_entity(order: dict, payment_id: str, status: str = "captured") -> dict:
    return {
        "id": payment_id,
        "order_id": order["order_id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "status": status,
    }


def _signed_webhook(payload: dict, event_id: str) -> tuple[str, str]:
    body = json.dumps(payload, separators=(",", ":"))
    signature = hmac.new(
        b"webhook-test-secret",
        body.encode(),
        hashlib.sha256,
    ).hexdigest()
    return body, signature


def test_checkout_disabled_for_missing_price_or_test_credentials(payment_app, monkeypatch):
    client = payment_app["client"]
    headers = payment_app["headers"]["learner"]
    monkeypatch.setattr(settings, "PREMIUM_AMOUNT_MINOR", None)
    plan = client.get("/premium/plan", headers=headers).json()
    assert plan["pricing"]["checkout_enabled"] is False
    assert plan["pricing"]["amount"] is None
    assert client.post("/premium/payment/orders", headers=headers).status_code == 503

    monkeypatch.setattr(settings, "PREMIUM_AMOUNT_MINOR", 12345)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_forbidden")
    assert client.get("/premium/plan", headers=headers).json()["pricing"]["checkout_enabled"] is False
    assert client.post("/premium/payment/orders", headers=headers).status_code == 503

    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_public")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    plan = client.get("/premium/plan", headers=headers)
    assert plan.json()["pricing"]["checkout_enabled"] is True
    assert plan.json()["pricing"]["key_id"] == "rzp_test_public"
    assert plan.json()["pricing"]["amount"] == 12345
    assert client.post("/premium/payment/orders", headers=headers).status_code == 201
    webhook = client.post(
        "/premium/payment/webhook",
        content=b'{"event":"payment.captured"}',
        headers={
            "x-razorpay-signature": "unused-without-webhook-secret",
            "x-razorpay-event-id": "evt-without-secret",
        },
    )
    assert webhook.status_code == 503
    assert webhook.json()["detail"] == "Razorpay webhook is not configured."


def test_order_uses_only_server_configuration_and_prevents_duplicate_payable_orders(payment_app):
    manipulated = payment_app["client"].post(
        "/premium/payment/orders",
        headers=payment_app["headers"]["learner"],
        json={
            "amount": 1,
            "currency": "USD",
            "user_id": payment_app["user_ids"]["other"],
            "plan": "free",
            "entitlement": "active",
        },
    )
    assert manipulated.status_code == 201
    first = manipulated.json()
    repeated = _created_order(payment_app)

    assert first["amount"] == 12345
    assert first["currency"] == "INR"
    assert first["key_id"] == "rzp_test_public"
    assert "server-only-secret" not in json.dumps(first)
    assert repeated["order_id"] == first["order_id"]
    assert len(payment_app["provider"].order.created) == 1
    sent, options = payment_app["provider"].order.created[0]
    assert sent["amount"] == 12345
    assert sent["currency"] == "INR"
    assert sent["receipt"].startswith("piq_")
    assert options == {"timeout": 10}


def test_verification_rejects_client_supplied_price_or_entitlement_fields(payment_app):
    order = _created_order(payment_app)
    response = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["learner"],
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_extra_fields",
            "razorpay_signature": VALID_SIGNATURE,
            "amount": 1,
            "currency": "USD",
            "entitlement": "active",
        },
    )
    assert response.status_code == 422


def test_order_and_verification_require_auth_and_enforce_ownership(payment_app):
    assert payment_app["client"].post("/premium/payment/orders").status_code == 401
    order = _created_order(payment_app)
    response = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["other"],
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_private",
            "razorpay_signature": VALID_SIGNATURE,
        },
    )
    assert response.status_code == 404


def test_invalid_signature_and_payment_mismatch_never_activate(payment_app):
    order = _created_order(payment_app)
    headers = payment_app["headers"]["learner"]
    bad_signature = payment_app["client"].post(
        "/premium/payment/verify",
        headers=headers,
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": "b" * 64,
        },
    )
    assert bad_signature.status_code == 400
    assert bad_signature.json()["detail"] == "Payment signature is invalid."

    payment_app["provider"].payment.entities["pay_1"] = {
        **_payment_entity(order, "pay_1"),
        "amount": order["amount"] + 1,
    }
    mismatch = payment_app["client"].post(
        "/premium/payment/verify",
        headers=headers,
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_1",
            "razorpay_signature": VALID_SIGNATURE,
        },
    )
    assert mismatch.status_code == 409
    with payment_app["factory"]() as db:
        assert db.query(PremiumSubscription).count() == 0
        assert db.query(PremiumPaymentAttempt).count() == 0
        assert db.query(PremiumPaymentOrder).filter_by(id=order["payment_order_id"]).one().status == "created"


def test_authorized_payment_is_pending_and_captured_payment_is_idempotently_activated(payment_app):
    order = _created_order(payment_app)
    payment_id = "pay_capture"
    payment_app["provider"].payment.entities[payment_id] = _payment_entity(
        order,
        payment_id,
        "authorized",
    )
    payload = {
        "razorpay_order_id": order["order_id"],
        "razorpay_payment_id": payment_id,
        "razorpay_signature": VALID_SIGNATURE,
    }
    first = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["learner"],
        json=payload,
    )
    assert first.status_code == 200
    assert first.json()["status"] == "pending"
    assert first.json()["entitlement_active"] is False

    payment_app["provider"].payment.entities[payment_id]["status"] = "captured"
    captured = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["learner"],
        json=payload,
    )
    repeated = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["learner"],
        json=payload,
    )
    assert captured.status_code == 200
    assert captured.json()["status"] == "paid"
    assert captured.json()["entitlement_active"] is True
    assert repeated.json()["entitlement_active"] is True
    with payment_app["factory"]() as db:
        assert db.query(PremiumSubscription).filter_by(user_id=payment_app["user_ids"]["learner"]).count() == 1
        assert db.query(PremiumPaymentAttempt).count() == 1


def test_existing_order_can_be_verified_if_checkout_pricing_is_later_disabled(
    payment_app,
    monkeypatch,
):
    order = _created_order(payment_app)
    payment_id = "pay_after_price_change"
    payment_app["provider"].payment.entities[payment_id] = _payment_entity(
        order,
        payment_id,
    )
    monkeypatch.setattr(settings, "PREMIUM_AMOUNT_MINOR", None)

    response = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["learner"],
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": VALID_SIGNATURE,
        },
    )

    assert response.status_code == 200
    assert response.json()["entitlement_active"] is True


def test_payment_cannot_be_reused_for_an_unrelated_user_order(payment_app):
    learner_order = _created_order(payment_app, "learner")
    other_order = _created_order(payment_app, "other")
    payment_id = "pay_reused"
    payment_app["provider"].payment.entities[payment_id] = _payment_entity(
        learner_order,
        payment_id,
        "captured",
    )
    response = payment_app["client"].post(
        "/premium/payment/verify",
        headers=payment_app["headers"]["other"],
        json={
            "razorpay_order_id": other_order["order_id"],
            "razorpay_payment_id": payment_id,
            "razorpay_signature": VALID_SIGNATURE,
        },
    )
    assert response.status_code == 409
    with payment_app["factory"]() as db:
        assert db.query(PremiumSubscription).count() == 0


def test_provider_timeout_keeps_order_reconcilable_and_does_not_leak_payload(payment_app):
    def timeout(*args, **kwargs):
        raise requests.Timeout("sensitive provider payload")

    payment_app["provider"].order.create = timeout
    response = payment_app["client"].post(
        "/premium/payment/orders",
        headers=payment_app["headers"]["learner"],
    )
    assert response.status_code == 502
    assert "sensitive provider payload" not in response.text
    assert "server-only-secret" not in response.text
    assert "status is being reconciled" in response.json()["detail"]
    with payment_app["factory"]() as db:
        order = db.query(PremiumPaymentOrder).one()
        assert order.status == "creation_unknown"


def test_duplicate_webhook_and_out_of_order_failure_do_not_repeat_or_downgrade(payment_app):
    order = _created_order(payment_app)
    payment_id = "pay_webhook"
    captured_entity = _payment_entity(order, payment_id, "captured")
    payload = {
        "event": "payment.captured",
        "payload": {"payment": {"entity": captured_entity}},
    }
    body, signature = _signed_webhook(payload, "evt-captured")
    headers = {
        "x-razorpay-signature": signature,
        "x-razorpay-event-id": "evt-captured",
    }
    captured = payment_app["client"].post(
        "/premium/payment/webhook",
        content=body,
        headers=headers,
    )
    duplicate = payment_app["client"].post(
        "/premium/payment/webhook",
        content=body,
        headers=headers,
    )
    assert captured.json()["status"] == "processed"
    assert duplicate.json()["status"] == "duplicate"

    failed_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    **captured_entity,
                    "status": "failed",
                }
            },
        },
    }
    failed_body, failed_signature = _signed_webhook(failed_payload, "evt-failed")
    stale = payment_app["client"].post(
        "/premium/payment/webhook",
        content=failed_body,
        headers={
            "x-razorpay-signature": failed_signature,
            "x-razorpay-event-id": "evt-failed",
        },
    )
    assert stale.status_code == 200, stale.text
    with payment_app["factory"]() as db:
        sub = db.query(PremiumSubscription).filter_by(user_id=payment_app["user_ids"]["learner"]).one()
        assert (sub.plan, sub.status) == ("premium", "active")
        assert db.query(PremiumPaymentWebhookEvent).count() == 2


def test_webhook_checks_raw_body_signature_and_status_refresh_is_owner_scoped(payment_app):
    order = _created_order(payment_app)
    raw_body = '{"event": "payment.captured"}'
    rejected = payment_app["client"].post(
        "/premium/payment/webhook",
        content=raw_body,
        headers={
            "x-razorpay-signature": "not-valid",
            "x-razorpay-event-id": "evt-invalid",
        },
    )
    assert rejected.status_code == 400

    status = payment_app["client"].get(
        f"/premium/payment/orders/{order['payment_order_id']}",
        headers=payment_app["headers"]["other"],
    )
    assert status.status_code == 404
    pending = payment_app["client"].get(
        f"/premium/payment/orders/{order['payment_order_id']}",
        headers=payment_app["headers"]["learner"],
    )
    assert pending.status_code == 200
    assert pending.json()["status"] == "pending"


def test_status_refresh_reconciles_capture_without_browser_callback(payment_app):
    order = _created_order(payment_app)
    payment_app["provider"].order.payment_entities[order["order_id"]] = [
        _payment_entity(order, "pay_webhook_capture", "captured")
    ]

    status = payment_app["client"].get(
        f"/premium/payment/orders/{order['payment_order_id']}",
        headers=payment_app["headers"]["learner"],
    )

    assert status.status_code == 200
    assert status.json()["status"] == "paid"
    assert status.json()["entitlement_active"] is True


def test_access_request_remains_pending_and_does_not_activate_or_mutate_payment_flow(payment_app):
    response = payment_app["client"].post(
        "/premium/access-request",
        headers=payment_app["headers"]["learner"],
    )
    assert response.status_code == 201
    assert response.json()["access_request_pending"] is True
    with payment_app["factory"]() as db:
        assert db.query(PremiumAccessRequest).filter_by(status="pending").count() == 1
        assert db.query(PremiumSubscription).count() == 0
