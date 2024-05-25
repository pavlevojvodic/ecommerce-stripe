# E-Commerce API with Stripe Checkout

A Django REST API for an online store with **Stripe Checkout** payment integration. Handles the complete order lifecycle from cart to payment to fulfillment.

## Tech Stack

- **Django** + **Django REST Framework**
- **Stripe Checkout** - Secure payment processing
- **Stripe Webhooks** - Async payment confirmation
- **PostgreSQL** - Order storage
- **API Key Authentication** - `X-API-KEY` header

## Payment Flow

```
Client                    API                     Stripe
  │                        │                        │
  ├─ POST /create_session ─▶                        │
  │                        ├── Create Order (pending)│
  │                        ├── Create Session ──────▶│
  │                        │◀── checkout_url ────────┤
  │◀── checkout_url ───────┤                        │
  │                        │                        │
  ├─ Redirect to Stripe ──────────────────────────▶│
  │                        │                        │
  │                        │◀── Webhook: paid ──────┤
  │                        ├── Update order status   │
  │                        ├── Send email notification│
  │                        │                        │
  ├─ GET /order_status ───▶│                        │
  │◀── {status: "paid"} ──┤                        │
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/create_checkout_session` | API Key | Create Stripe checkout session |
| POST | `/api/stripe_webhook` | Stripe Signature | Handle payment events |
| GET | `/api/order_status?session_id=...` | API Key | Check order status |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your Stripe keys
python manage.py migrate
python manage.py runserver
```

Configure the Stripe webhook URL in your Stripe Dashboard to point to `/api/stripe_webhook`.
