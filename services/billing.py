"""
GridWise Version 4 - Billing (Stripe)
=========================================

Handles the free -> premium upgrade flow using Stripe Checkout (hosted,
Stripe-built payment page - GridWise never sees or stores card details)
and Stripe's Customer Portal (hosted page where users can cancel/update
their own subscription without you building that UI yourself).

Setup required:
1. Create a free Stripe account at https://dashboard.stripe.com/register
   (instant, no approval wait - this is a genuine advantage over the data
   APIs we fought with earlier).
2. Stay in TEST MODE while developing (toggle top-left of the Stripe
   dashboard) - test mode uses fake card numbers (4242 4242 4242 4242)
   and never touches real money.
3. Create one Product with a recurring monthly Price (e.g. "GridWise
   Premium", £9.99/month) under Product Catalog. Copy its Price ID
   (starts "price_...").
4. Get your API keys from Developers -> API keys.
5. Add all of this to .env:
       STRIPE_SECRET_KEY=sk_test_...
       STRIPE_PUBLISHABLE_KEY=pk_test_...
       STRIPE_PREMIUM_PRICE_ID=price_...
       STRIPE_WEBHOOK_SECRET=whsec_...   (see webhook setup below)
   Never put these directly in any source file - .env only.

Webhook setup (needed so a successful payment actually upgrades the
account - without this, Stripe takes the money but GridWise never finds
out):
1. Install the Stripe CLI (https://stripe.com/docs/stripe-cli) for local
   testing.
2. Run: stripe listen --forward-to localhost:5000/billing/webhook
3. That command prints a webhook signing secret (whsec_...) - put that in
   STRIPE_WEBHOOK_SECRET in .env for local dev.
4. Once deployed (e.g. on Render), add a webhook endpoint in the Stripe
   dashboard pointing at https://your-domain/billing/webhook, listening
   for checkout.session.completed and customer.subscription.deleted -
   that gives you a separate, production webhook secret to use there.

IMPORTANT - this is real payment infrastructure, not a toy:
- Stay in Stripe test mode until you've tested the full flow (signup ->
  checkout with a test card -> webhook fires -> tier flips to premium ->
  cancel via portal -> webhook fires -> tier flips back to free).
- Only switch to live keys once that whole loop is verified working, and
  once you have a visible refund/cancellation policy and terms of
  service - Stripe (and UK consumer law, if you're charging UK
  customers) expects this before you take real payments.
"""

import os
import stripe

from services import auth

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
PREMIUM_PRICE_ID = os.getenv("STRIPE_PREMIUM_PRICE_ID")
WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


def get_premium_price_display():
    """
    Fetches the ACTUAL price Stripe will charge, formatted for display -
    this is the fix for the pricing page previously showing a hardcoded
    "£9.99" that could silently drift out of sync if the real Stripe
    price ever changed. Now the page always shows exactly what Stripe
    will actually charge, because it's reading it from Stripe directly.

    Returns a dict: {"amount": "9.99", "currency": "GBP", "interval": "month"}
    or None if Stripe isn't configured yet / the price ID is invalid.
    """

    if not stripe.api_key or not PREMIUM_PRICE_ID:
        return None

    try:
        price = stripe.Price.retrieve(PREMIUM_PRICE_ID)

        return {
            "amount": f"{price.unit_amount / 100:.2f}",
            "currency": price.currency.upper(),
            "interval": price.recurring.interval if price.recurring else "one-time",
        }
    except Exception as e:
        print("Stripe price fetch error:", e)
        return None


def create_checkout_session(user, success_url, cancel_url):
    """Returns a Stripe-hosted Checkout URL to redirect the user to."""

    if not stripe.api_key or not PREMIUM_PRICE_ID:
        raise RuntimeError("Stripe is not configured - check STRIPE_SECRET_KEY and STRIPE_PREMIUM_PRICE_ID in .env")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": PREMIUM_PRICE_ID, "quantity": 1}],
        customer_email=user.email,
        client_reference_id=user.id,
        success_url=success_url,
        cancel_url=cancel_url,
    )

    return session.url


def create_portal_session(user, return_url):
    """Returns a Stripe-hosted billing portal URL where the user can
    update payment details or cancel - Stripe builds/maintains this UI,
    not GridWise."""

    if not user.stripe_customer_id:
        raise RuntimeError("This user has no Stripe customer ID yet - they need to complete checkout first")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=return_url,
    )

    return session.url


def handle_webhook(payload, sig_header):
    """
    Verifies the webhook signature (critical - without this, anyone could
    POST a fake "payment succeeded" request to your server) and processes
    the two events that matter for tier changes.

    Returns (status_code, message) for the route to respond with.
    """

    if not WEBHOOK_SECRET:
        return 500, "Webhook secret not configured"

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        print("Stripe webhook signature verification failed:", e)
        return 400, "Invalid signature"

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")

        if user_id:
            auth.set_stripe_ids(user_id, customer_id=customer_id, subscription_id=subscription_id)
            auth.set_tier(user_id, "premium")
            print(f"User {user_id} upgraded to premium")

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        user = auth.get_user_by_stripe_customer_id(customer_id)

        if user:
            auth.set_tier(user.id, "free")
            print(f"User {user.id} downgraded to free (subscription cancelled)")

    return 200, "OK"
