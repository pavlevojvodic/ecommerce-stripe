"""
E-commerce API views with Stripe Checkout integration.

Provides endpoints for browsing products, managing the shopping cart,
creating Stripe Checkout sessions, handling webhooks, and checking
order status.
"""
import json
import stripe
from django.http import JsonResponse
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from .models import Order
from .authentication import require_api_key

stripe.api_key = settings.STRIPE_SECRET_KEY


@csrf_exempt
@require_api_key
def create_checkout_session(request):
    """
    Create a Stripe Checkout Session.

    Accepts a list of items with prices, customer info, and shipping
    address. Creates a pending order in the database and returns the
    Stripe checkout URL for redirect.

    Expected body:
    {
        "items": [{"product_id": 1, "name": "...", "price": 250.00, "quantity": 1, "size": "90x90"}],
        "customer_email": "user@example.com",
        "customer_name": "John Doe",
        "shipping_address": {"line1": "...", "city": "...", "postal_code": "...", "country": "FR"}
    }
    """
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        customer_email = data.get('customer_email')
        customer_name = data.get('customer_name', '')
        customer_phone = data.get('customer_phone', '')
        shipping_address = data.get('shipping_address', {})

        if not items:
            return JsonResponse({"error": "No items provided"}, status=400)
        if not customer_email:
            return JsonResponse({"error": "Customer email is required"}, status=400)

        # Build Stripe line items
        line_items = []
        total_amount = 0
        for item in items:
            price = float(item.get('price', 0))
            quantity = int(item.get('quantity', 1))
            name = item.get('name', 'Product')
            size = item.get('size', '')
            product_name = f"{name} ({size})" if size else name

            line_items.append({
                'price_data': {
                    'currency': 'eur',
                    'product_data': {'name': product_name},
                    'unit_amount': int(price * 100),
                },
                'quantity': quantity,
            })
            total_amount += price * quantity

        # Create pending order
        order = Order.objects.create(
            customer_email=customer_email,
            customer_name=customer_name,
            customer_phone=customer_phone,
            shipping_address_line1=shipping_address.get('line1', ''),
            shipping_address_line2=shipping_address.get('line2', ''),
            shipping_city=shipping_address.get('city', ''),
            shipping_postal_code=shipping_address.get('postal_code', ''),
            shipping_country=shipping_address.get('country', ''),
            items=items,
            total_amount=total_amount,
            currency='EUR',
            status='pending',
        )

        # Create Stripe Checkout Session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='payment',
            customer_email=customer_email,
            success_url=settings.STRIPE_SUCCESS_URL,
            cancel_url=settings.STRIPE_CANCEL_URL,
            metadata={'order_id': order.order_id},
            shipping_address_collection={
                'allowed_countries': [
                    'AT', 'BE', 'CH', 'DE', 'DK', 'ES', 'FI', 'FR', 'GB',
                    'GR', 'HR', 'HU', 'IE', 'IT', 'LU', 'NL', 'NO', 'PL',
                    'PT', 'RO', 'RS', 'SE', 'SI', 'SK', 'US', 'CA', 'AU',
                ],
            },
        )

        order.stripe_session_id = checkout_session.id
        order.save()

        return JsonResponse({
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id,
            "order_id": order.order_id,
        })

    except stripe.error.StripeError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
def stripe_webhook(request):
    """
    Handle Stripe webhook events.

    Listens for checkout.session.completed and checkout.session.expired
    events to update order status and send email notifications.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return JsonResponse({"error": "Invalid signature"}, status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        order_id = session.get('metadata', {}).get('order_id')

        if order_id:
            try:
                order = Order.objects.get(order_id=order_id)
                order.status = 'paid'
                order.stripe_payment_intent_id = session.get('payment_intent')
                order.paid_at = timezone.now()

                # Update shipping from Stripe response
                shipping = session.get('shipping_details', {})
                if shipping:
                    address = shipping.get('address', {})
                    order.customer_name = shipping.get('name', order.customer_name)
                    order.shipping_address_line1 = address.get('line1', order.shipping_address_line1)
                    order.shipping_address_line2 = address.get('line2', order.shipping_address_line2)
                    order.shipping_city = address.get('city', order.shipping_city)
                    order.shipping_postal_code = address.get('postal_code', order.shipping_postal_code)
                    order.shipping_country = address.get('country', order.shipping_country)

                order.save()

                # Send notification email
                _send_order_notification(order)
            except Order.DoesNotExist:
                pass

    elif event['type'] == 'checkout.session.expired':
        session = event['data']['object']
        order_id = session.get('metadata', {}).get('order_id')
        if order_id:
            try:
                order = Order.objects.get(order_id=order_id)
                order.status = 'cancelled'
                order.save()
            except Order.DoesNotExist:
                pass

    return JsonResponse({"status": "success"})


def _send_order_notification(order):
    """Send email notification for a paid order."""
    try:
        items_list = "\n".join([
            f"- {item.get('name', 'Unknown')} x {item.get('quantity', 1)} - EUR {item.get('price', 0)}"
            for item in order.items
        ])
        send_mail(
            subject=f"New Order #{order.order_id}",
            message=(
                f"New paid order received!\n\n"
                f"Order ID: {order.order_id}\n"
                f"Customer: {order.customer_name}\n"
                f"Email: {order.customer_email}\n\n"
                f"Items:\n{items_list}\n\n"
                f"Total: EUR {order.total_amount}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL],
            fail_silently=True,
        )
    except Exception as e:
        print(f"Failed to send order notification: {e}")


@api_view(['GET'])
@require_api_key
def get_order_status(request):
    """
    Get order status by session_id or order_id.

    Query params: session_id or order_id
    """
    session_id = request.GET.get('session_id')
    order_id = request.GET.get('order_id')

    if not session_id and not order_id:
        return JsonResponse({"error": "session_id or order_id required"}, status=400)

    try:
        if session_id:
            order = Order.objects.get(stripe_session_id=session_id)
        else:
            order = Order.objects.get(order_id=order_id)

        return JsonResponse({
            "order_id": order.order_id,
            "status": order.status,
            "customer_email": order.customer_email,
            "customer_name": order.customer_name,
            "total_amount": str(order.total_amount),
            "currency": order.currency,
            "items": order.items,
            "created_at": order.created_at.isoformat(),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
        })
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)
