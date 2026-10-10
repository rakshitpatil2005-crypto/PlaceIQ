const RAZORPAY_CHECKOUT_URL = 'https://checkout.razorpay.com/v1/checkout.js';

export function loadRazorpayCheckout({
  documentRef = globalThis.document,
  windowRef = globalThis.window,
} = {}) {
  if (typeof windowRef?.Razorpay === 'function') {
    return Promise.resolve(windowRef.Razorpay);
  }
  if (!documentRef) {
    return Promise.reject(new Error('Razorpay Checkout is unavailable in this browser.'));
  }
  const existing = documentRef.querySelector('[data-placeiq-razorpay]');
  if (existing) {
    return new Promise((resolve, reject) => {
      existing.addEventListener('load', () => {
        if (typeof windowRef?.Razorpay === 'function') resolve(windowRef.Razorpay);
        else reject(new Error('Razorpay Checkout did not initialize.'));
      }, { once: true });
      existing.addEventListener('error', () => reject(new Error('Razorpay Checkout could not be loaded.')), { once: true });
    });
  }
  return new Promise((resolve, reject) => {
    const script = documentRef.createElement('script');
    script.src = RAZORPAY_CHECKOUT_URL;
    script.async = true;
    script.dataset.placeiqRazorpay = 'true';
    script.onload = () => {
      if (typeof windowRef?.Razorpay === 'function') resolve(windowRef.Razorpay);
      else reject(new Error('Razorpay Checkout did not initialize.'));
    };
    script.onerror = () => reject(new Error('Razorpay Checkout could not be loaded.'));
    documentRef.body.appendChild(script);
  });
}

export function createPremiumCheckoutOptions({
  order,
  onSuccess,
  onDismiss,
}) {
  return {
    key: order.key_id,
    amount: order.amount,
    currency: order.currency,
    name: 'PlaceIQ',
    description: order.description,
    order_id: order.order_id,
    theme: { color: '#047857' },
    handler: onSuccess,
    modal: { ondismiss: onDismiss },
    notes: { product: 'PlaceIQ Premium' },
  };
}

export async function preparePremiumCheckout({ loadCheckout, createOrder }) {
  const Razorpay = await loadCheckout();
  const order = await createOrder();
  return { Razorpay, order };
}

export function reservePremiumCheckout(lock) {
  if (lock.current) return false;
  lock.current = true;
  return true;
}

export async function verifyPremiumCheckout({ verifyPayment, response }) {
  const { data } = await verifyPayment({
    razorpay_order_id: response.razorpay_order_id,
    razorpay_payment_id: response.razorpay_payment_id,
    razorpay_signature: response.razorpay_signature,
  });
  return {
    status: data?.status === 'paid' && data?.entitlement_active === true
      ? 'confirmed'
      : 'pending',
  };
}
