import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createPremiumCheckoutOptions,
  preparePremiumCheckout,
  reservePremiumCheckout,
  verifyPremiumCheckout,
} from './premiumPayment.js';

test('creates the server order before returning checkout constructor and trusted options', async () => {
  const calls = [];
  class FakeRazorpay {
    constructor(options) {
      calls.push(['checkout', options]);
    }
  }
  const order = {
    key_id: 'rzp_test_public',
    order_id: 'order_server',
    amount: 2500,
    currency: 'INR',
    description: 'PlaceIQ Premium (Test Mode)',
  };
  const prepared = await preparePremiumCheckout({
    loadCheckout: async () => {
      calls.push(['load']);
      return FakeRazorpay;
    },
    createOrder: async () => {
      calls.push(['order']);
      return order;
    },
  });
  const options = createPremiumCheckoutOptions({
    order: prepared.order,
    onSuccess: () => {},
    onDismiss: () => calls.push(['dismiss']),
  });
  new prepared.Razorpay(options);
  options.modal.ondismiss();

  assert.deepEqual(calls.map(([name]) => name), ['load', 'order', 'checkout', 'dismiss']);
  assert.equal(options.key, 'rzp_test_public');
  assert.equal(options.order_id, 'order_server');
  assert.equal(options.amount, 2500);
  assert.equal(options.currency, 'INR');
  assert.match(options.description, /Test Mode/);
  assert.equal(typeof options.handler, 'function');
  assert.equal(typeof options.modal.ondismiss, 'function');
});

test('does not continue to Checkout when loading or order creation fails', async () => {
  let orderRequested = false;
  await assert.rejects(
    preparePremiumCheckout({
      loadCheckout: async () => { throw new Error('Checkout unavailable'); },
      createOrder: async () => { orderRequested = true; },
    }),
    /Checkout unavailable/,
  );
  assert.equal(orderRequested, false);
});

test('verifies checkout using only provider identifiers and trusts active status only from backend', async () => {
  const response = {
    razorpay_order_id: 'order_server',
    razorpay_payment_id: 'pay_server',
    razorpay_signature: 'signature_server',
  };
  let submitted;
  const confirmed = await verifyPremiumCheckout({
    response,
    verifyPayment: async (payload) => {
      submitted = payload;
      return { data: { status: 'paid', entitlement_active: true } };
    },
  });
  assert.deepEqual(submitted, response);
  assert.equal(confirmed.status, 'confirmed');

  const pending = await verifyPremiumCheckout({
    response,
    verifyPayment: async () => ({
      data: { status: 'paid', entitlement_active: false },
    }),
  });
  assert.equal(pending.status, 'pending');
});

test('checkout reservation prevents duplicate submissions and releases for retry', () => {
  const lock = { current: false };
  assert.equal(reservePremiumCheckout(lock), true);
  assert.equal(reservePremiumCheckout(lock), false);
  lock.current = false;
  assert.equal(reservePremiumCheckout(lock), true);
});
