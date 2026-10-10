from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Callable, TypeVar

import requests
import razorpay
from razorpay.errors import (
    BadRequestError,
    GatewayError,
    ServerError,
    SignatureVerificationError,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    PremiumPaymentAttempt,
    PremiumPaymentOrder,
    PremiumPaymentWebhookEvent,
    PremiumSubscription,
    User,
)

Result = TypeVar("Result")


class PaymentError(Exception):
    status_code = 400


class PaymentNotConfigured(PaymentError):
    status_code = 503


class PaymentConflict(PaymentError):
    status_code = 409


class PaymentNotFound(PaymentError):
    status_code = 404


class InvalidPaymentSignature(PaymentError):
    status_code = 400


class PaymentProviderUnavailable(PaymentError):
    status_code = 502


def checkout_configuration() -> dict[str, Any]:
    credentials_ready = (
        settings.RAZORPAY_KEY_ID.startswith("rzp_test_")
        and bool(settings.RAZORPAY_KEY_SECRET)
    )
    amount_ready = (
        isinstance(settings.PREMIUM_AMOUNT_MINOR, int)
        and not isinstance(settings.PREMIUM_AMOUNT_MINOR, bool)
        and settings.PREMIUM_AMOUNT_MINOR > 0
    )
    enabled = credentials_ready and amount_ready
    if not amount_ready:
        reason = "Premium pricing is not configured."
    elif not credentials_ready:
        reason = "Razorpay Test Mode API credentials are not configured."
    else:
        reason = ""
    return {
        "checkout_enabled": enabled,
        "key_id": settings.RAZORPAY_KEY_ID if enabled else None,
        "amount": settings.PREMIUM_AMOUNT_MINOR if enabled else None,
        "currency": settings.PREMIUM_CURRENCY if enabled else None,
        "description": "PlaceIQ Premium (Test Mode)",
        "unavailable_reason": reason,
    }


def _client() -> razorpay.Client:
    if (
        not settings.RAZORPAY_KEY_ID.startswith("rzp_test_")
        or not settings.RAZORPAY_KEY_SECRET
    ):
        raise PaymentNotConfigured("Razorpay Test Mode API credentials are not configured.")
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def _provider_errors() -> tuple[type[BaseException], ...]:
    return (
        requests.exceptions.RequestException,
        BadRequestError,
        GatewayError,
        ServerError,
    )


def _error_safe_provider_call(operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except _provider_errors() as exc:
        raise PaymentProviderUnavailable(
            "Razorpay could not complete the request. Please retry."
        ) from exc


def _provider_order_matches(
    provider_order: dict[str, Any],
    order: PremiumPaymentOrder,
) -> bool:
    return (
        isinstance(provider_order, dict)
        and isinstance(provider_order.get("id"), str)
        and provider_order.get("amount") == order.amount
        and provider_order.get("currency") == order.currency
        and provider_order.get("receipt") == order.receipt
        and provider_order.get("status") in ("created", "attempted", "paid")
    )


def _checkout_order_response(order: PremiumPaymentOrder) -> dict[str, Any]:
    config = checkout_configuration()
    return {
        "payment_order_id": order.id,
        "key_id": config["key_id"],
        "order_id": order.razorpay_order_id,
        "amount": order.amount,
        "currency": order.currency,
        "description": config["description"],
    }


def _reconcile_unknown_order(client, order: PremiumPaymentOrder) -> bool:
    response = _error_safe_provider_call(
        lambda: client.order.all(
            {"receipt": order.receipt, "count": 1},
            timeout=10,
        )
    )
    items = response.get("items", []) if isinstance(response, dict) else []
    match = next(
        (
            item
            for item in items
            if _provider_order_matches(item, order)
        ),
        None,
    )
    if match is None:
        return False
    order.razorpay_order_id = match["id"]
    order.status = "created"
    order.updated_at = datetime.utcnow()
    return True


def create_order(db: Session, user: User) -> dict[str, Any]:
    config = checkout_configuration()
    if not config["checkout_enabled"]:
        raise PaymentNotConfigured(config["unavailable_reason"])
    subscription = (
        db.query(PremiumSubscription)
        .filter(PremiumSubscription.user_id == user.id)
        .first()
    )
    if subscription and subscription.plan == "premium" and subscription.status == "active":
        raise PaymentConflict("Premium access is already active.")

    order = (
        db.query(PremiumPaymentOrder)
        .filter(
            PremiumPaymentOrder.user_id == user.id,
            PremiumPaymentOrder.status.in_(("creating", "creation_unknown", "created")),
        )
        .first()
    )
    if order:
        if order.status == "created":
            return _checkout_order_response(order)
        if order.status == "creating":
            raise PaymentConflict("A Premium order is already being prepared.")
        client = _client()
        try:
            if not _reconcile_unknown_order(client, order):
                raise PaymentConflict(
                    "The previous order is awaiting provider confirmation. Retry shortly."
                )
            db.commit()
        except PaymentProviderUnavailable:
            db.rollback()
            raise
        return _checkout_order_response(order)

    idempotency_key = uuid.uuid4().hex
    receipt = f"piq_{idempotency_key[:32]}"
    order = PremiumPaymentOrder(
        user_id=user.id,
        idempotency_key=idempotency_key,
        receipt=receipt,
        amount=config["amount"],
        currency=config["currency"],
        status="creating",
    )
    db.add(order)
    try:
        db.commit()
        db.refresh(order)
    except IntegrityError as exc:
        db.rollback()
        existing_order = (
            db.query(PremiumPaymentOrder)
            .filter(
                PremiumPaymentOrder.user_id == user.id,
                PremiumPaymentOrder.status.in_(("creating", "creation_unknown", "created")),
            )
            .first()
        )
        if existing_order and existing_order.status == "created":
            return _checkout_order_response(existing_order)
        raise PaymentConflict("A Premium order is already being prepared.") from exc

    client = _client()
    try:
        provider_order = client.order.create(
            {
                "amount": order.amount,
                "currency": order.currency,
                "receipt": order.receipt,
                "notes": {"placeiq_payment_order_id": str(order.id)},
            },
            timeout=10,
        )
    except requests.exceptions.RequestException as exc:
        order.status = "creation_unknown"
        order.updated_at = datetime.utcnow()
        db.commit()
        try:
            if _reconcile_unknown_order(client, order):
                db.commit()
                return _checkout_order_response(order)
        except PaymentProviderUnavailable:
            db.rollback()
        raise PaymentProviderUnavailable(
            "Razorpay did not confirm the order. Its status is being reconciled; retry shortly."
        ) from exc
    except (BadRequestError, GatewayError, ServerError) as exc:
        order.status = "failed"
        order.updated_at = datetime.utcnow()
        db.commit()
        raise PaymentProviderUnavailable(
            "Razorpay could not create the order. Please retry."
        ) from exc

    if not _provider_order_matches(provider_order, order):
        order.status = "creation_unknown"
        order.updated_at = datetime.utcnow()
        db.commit()
        raise PaymentProviderUnavailable(
            "Razorpay returned an order that could not be verified."
        )
    order.razorpay_order_id = provider_order["id"]
    order.status = "created"
    order.updated_at = datetime.utcnow()
    db.commit()
    return _checkout_order_response(order)


def _load_owned_order(db: Session, user: User, provider_order_id: str) -> PremiumPaymentOrder:
    order = (
        db.query(PremiumPaymentOrder)
        .filter(PremiumPaymentOrder.razorpay_order_id == provider_order_id)
        .first()
    )
    if order is None:
        raise PaymentNotFound("Payment order was not found.")
    if order.user_id != user.id:
        raise PaymentNotFound("Payment order was not found.")
    return order


def _get_or_create_attempt(
    db: Session,
    order: PremiumPaymentOrder,
    payment_id: str,
    amount: int,
    currency: str,
    status: str,
) -> PremiumPaymentAttempt:
    attempt = (
        db.query(PremiumPaymentAttempt)
        .filter(PremiumPaymentAttempt.razorpay_payment_id == payment_id)
        .first()
    )
    if attempt is not None:
        if attempt.order_id != order.id or attempt.user_id != order.user_id:
            raise PaymentConflict("Payment is already associated with another order.")
    else:
        attempt = PremiumPaymentAttempt(
            order_id=order.id,
            user_id=order.user_id,
            razorpay_payment_id=payment_id,
            amount=amount,
            currency=currency,
            status=status,
        )
        db.add(attempt)
    if attempt.status != "captured":
        priorities = {"created": 0, "failed": 1, "authorized": 2, "captured": 3}
        if priorities.get(status, -1) > priorities.get(attempt.status, -1):
            attempt.status = status
            attempt.amount = amount
            attempt.currency = currency
            attempt.updated_at = datetime.utcnow()
    return attempt


def _validate_payment_entity(
    order: PremiumPaymentOrder,
    payment: dict,
    payment_id: str,
) -> str:
    if (
        not isinstance(payment, dict)
        or payment.get("id") != payment_id
        or payment.get("order_id") != order.razorpay_order_id
        or payment.get("amount") != order.amount
        or payment.get("currency") != order.currency
        or payment.get("status") not in ("created", "authorized", "captured", "failed")
    ):
        raise PaymentConflict("Payment details do not match this order.")
    return payment["status"]


def _activate_premium(
    db: Session,
    order: PremiumPaymentOrder,
    attempt: PremiumPaymentAttempt,
) -> None:
    if attempt.status != "captured":
        return
    order.status = "paid"
    order.updated_at = datetime.utcnow()
    subscription = (
        db.query(PremiumSubscription)
        .filter(PremiumSubscription.user_id == order.user_id)
        .first()
    )
    if subscription is None:
        subscription = PremiumSubscription(
            user_id=order.user_id,
            plan="premium",
            status="active",
        )
        db.add(subscription)
    else:
        subscription.plan = "premium"
        subscription.status = "active"
        subscription.updated_at = datetime.utcnow()
    db.commit()


def _payment_response(order: PremiumPaymentOrder, db: Session) -> dict[str, Any]:
    attempts = (
        db.query(PremiumPaymentAttempt)
        .filter(PremiumPaymentAttempt.order_id == order.id)
        .order_by(PremiumPaymentAttempt.id.desc())
        .all()
    )
    subscription = (
        db.query(PremiumSubscription)
        .filter(PremiumSubscription.user_id == order.user_id)
        .first()
    )
    active = bool(
        subscription
        and subscription.plan == "premium"
        and subscription.status == "active"
    )
    return {
        "payment_order_id": order.id,
        "status": "paid" if order.status == "paid" else "pending",
        "payment_attempts": [
            {"status": attempt.status} for attempt in attempts
        ],
        "entitlement_active": active,
    }


def _reconcile_payment_attempts(
    db: Session,
    order: PremiumPaymentOrder,
) -> None:
    if order.status == "paid":
        return
    attempts = (
        db.query(PremiumPaymentAttempt)
        .filter(PremiumPaymentAttempt.order_id == order.id)
        .order_by(PremiumPaymentAttempt.id.desc())
        .all()
    )
    client = _client()
    if not attempts:
        response = _error_safe_provider_call(
            lambda: client.order.payments(order.razorpay_order_id, timeout=10)
        )
        entities = response.get("items", []) if isinstance(response, dict) else []
        for payment in entities:
            payment_id = payment.get("id") if isinstance(payment, dict) else None
            if not isinstance(payment_id, str):
                continue
            status = _validate_payment_entity(order, payment, payment_id)
            attempt = _get_or_create_attempt(
                db,
                order,
                payment_id,
                payment["amount"],
                payment["currency"],
                status,
            )
            if status == "captured":
                _activate_premium(db, order, attempt)
                return
        db.commit()
        return
    for attempt in attempts:
        provider_payment = _error_safe_provider_call(
            lambda attempt=attempt: client.payment.fetch(
                attempt.razorpay_payment_id,
                timeout=10,
            )
        )
        status = _validate_payment_entity(
            order,
            provider_payment,
            attempt.razorpay_payment_id,
        )
        _get_or_create_attempt(
            db,
            order,
            attempt.razorpay_payment_id,
            provider_payment["amount"],
            provider_payment["currency"],
            status,
        )
        if status == "captured":
            _activate_premium(db, order, attempt)
            return
    db.commit()


def verify_payment(
    db: Session,
    user: User,
    provider_order_id: str,
    payment_id: str,
    signature: str,
) -> dict[str, Any]:
    if not payment_id or not signature:
        raise PaymentError("Required payment verification fields are missing.")
    order = _load_owned_order(db, user, provider_order_id)
    client = _client()
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": provider_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except SignatureVerificationError as exc:
        raise InvalidPaymentSignature("Payment signature is invalid.") from exc

    provider_payment = _error_safe_provider_call(
        lambda: client.payment.fetch(payment_id, timeout=10)
    )
    status = _validate_payment_entity(order, provider_payment, payment_id)
    try:
        attempt = _get_or_create_attempt(
            db,
            order,
            payment_id,
            provider_payment["amount"],
            provider_payment["currency"],
            status,
        )
        if status == "captured":
            _activate_premium(db, order, attempt)
        else:
            db.commit()
    except IntegrityError as exc:
        db.rollback()
        refreshed_order = (
            db.query(PremiumPaymentOrder)
            .filter(PremiumPaymentOrder.razorpay_order_id == provider_order_id)
            .first()
        )
        refreshed_attempt = (
            db.query(PremiumPaymentAttempt)
            .filter(PremiumPaymentAttempt.razorpay_payment_id == payment_id)
            .first()
        )
        if (
            refreshed_order is not None
            and refreshed_attempt is not None
            and refreshed_attempt.order_id == refreshed_order.id
            and refreshed_attempt.user_id == user.id
            and refreshed_attempt.status == "captured"
            and refreshed_order.status == "paid"
        ):
            return _payment_response(refreshed_order, db)
        raise PaymentConflict(
            "Payment verification conflicted with another payment update."
        ) from exc
    return _payment_response(order, db)


def payment_status(db: Session, user: User, local_order_id: int) -> dict[str, Any]:
    order = (
        db.query(PremiumPaymentOrder)
        .filter(
            PremiumPaymentOrder.id == local_order_id,
            PremiumPaymentOrder.user_id == user.id,
        )
        .first()
    )
    if order is None:
        raise PaymentNotFound("Payment order was not found.")
    _reconcile_payment_attempts(db, order)
    return _payment_response(order, db)


def process_webhook(
    db: Session,
    raw_body: bytes,
    signature: str,
    event_id: str,
) -> dict[str, str]:
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise PaymentNotConfigured("Razorpay webhook is not configured.")
    if not event_id or not signature:
        raise InvalidPaymentSignature("Webhook signature or event ID is missing.")
    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    try:
        client.utility.verify_webhook_signature(
            raw_body.decode("utf-8"),
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET,
        )
    except (SignatureVerificationError, UnicodeDecodeError) as exc:
        raise InvalidPaymentSignature("Webhook signature is invalid.") from exc

    existing_event = (
        db.query(PremiumPaymentWebhookEvent)
        .filter(PremiumPaymentWebhookEvent.provider_event_id == event_id)
        .first()
    )
    if existing_event:
        return {"status": "duplicate"}

    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise PaymentError("Webhook payload is invalid.") from exc
    event_type = payload.get("event")
    if not isinstance(event_type, str) or len(event_type) > 64:
        raise PaymentError("Webhook event type is invalid.")

    try:
        event = PremiumPaymentWebhookEvent(
            provider_event_id=event_id,
            event_type=event_type,
        )
        db.add(event)
        if event_type in ("payment.captured", "payment.authorized", "payment.failed"):
            payment = (
                payload.get("payload", {})
                .get("payment", {})
                .get("entity", {})
            )
            if not isinstance(payment, dict):
                raise PaymentError("Webhook payment entity is invalid.")
            order_id = payment.get("order_id")
            payment_id = payment.get("id")
            if not isinstance(order_id, str) or not isinstance(payment_id, str):
                raise PaymentError("Webhook payment identifiers are invalid.")
            order = (
                db.query(PremiumPaymentOrder)
                .filter(PremiumPaymentOrder.razorpay_order_id == order_id)
                .first()
            )
            if order is None:
                raise PaymentNotFound("Payment order was not found.")
            status = _validate_payment_entity(order, payment, payment_id)
            attempt = _get_or_create_attempt(
                db,
                order,
                payment_id,
                payment["amount"],
                payment["currency"],
                status,
            )
            if status == "captured":
                _activate_premium(db, order, attempt)
            else:
                db.commit()
        else:
            db.commit()
    except IntegrityError:
        db.rollback()
        if (
            db.query(PremiumPaymentWebhookEvent)
            .filter(PremiumPaymentWebhookEvent.provider_event_id == event_id)
            .first()
        ):
            return {"status": "duplicate"}
        raise PaymentConflict(
            "Webhook conflicts with an existing payment record."
        ) from None
    return {"status": "processed"}
