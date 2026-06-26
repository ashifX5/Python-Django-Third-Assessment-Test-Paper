"""
=============================================================================
  middleware.py — Upload Size Limit Middleware
=============================================================================

  WHAT IS MIDDLEWARE?
  -------------------
  Middleware runs BEFORE your view (page) even loads.
  Think of it like a security guard at the door — it checks the request
  first, and can BLOCK it before it ever reaches your Python code.

  WHAT THIS MIDDLEWARE DOES:
  --------------------------
  If someone uploads a file that is TOO LARGE, we reject it immediately
  with a 413 error (413 = "Payload Too Large").

  This prevents huge files from wasting server memory.

  HOW IT WORKS:
  -------------
  Every HTTP request has a header called CONTENT_LENGTH.
  This tells us the size of the uploaded data BEFORE we read it.
  We check that number — if it's too big, we block the request right away.
=============================================================================
"""

from django.http import HttpResponse
from django.conf import settings


class UploadSizeLimitMiddleware:
    """
    Blocks any POST upload that exceeds MAX_UPLOAD_SIZE_BYTES (set in settings.py).

    Django middleware must have:
      __init__(self, get_response)  → called once when server starts
      __call__(self, request)       → called on EVERY incoming request
    """

    def __init__(self, get_response):
        # get_response is Django's way of passing control to the next middleware/view
        self.get_response = get_response

    def __call__(self, request):
        # Only check POST requests (uploads use POST)
        if request.method == 'POST':
            # CONTENT_LENGTH header tells us how big the upload is
            content_length = request.META.get('CONTENT_LENGTH', 0)

            try:
                content_length = int(content_length)
            except (ValueError, TypeError):
                content_length = 0

            # Get the limit from settings (default 1MB if not set)
            max_size = getattr(settings, 'MAX_UPLOAD_SIZE_BYTES', 1 * 1024 * 1024)

            if content_length > max_size:
                # BLOCK the request — never reaches the view
                max_mb = max_size / (1024 * 1024)
                return HttpResponse(
                    f"<h2>413 — Upload Too Large</h2>"
                    f"<p>Your file exceeds the maximum allowed size of {max_mb:.1f} MB.</p>"
                    f"<p><a href='/'>Go back</a></p>",
                    status=413,
                    content_type="text/html"
                )

        # If size is fine, pass the request to the next middleware or view
        response = self.get_response(request)
        return response
