"""API key authentication via X-API-KEY header."""
from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    """Decorator that enforces X-API-KEY header authentication."""
    def wrapper(request, *args, **kwargs):
        api_key = request.META.get('HTTP_X_API_KEY')
        if not api_key or api_key != settings.API_KEY:
            return JsonResponse({"error": "Authentication failed"}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper
