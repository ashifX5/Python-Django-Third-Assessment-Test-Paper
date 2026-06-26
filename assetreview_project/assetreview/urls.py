"""
urls.py — URL Routes for the assetreview app

URL names allow us to use reverse() in views and {% url %} in templates
instead of hardcoding paths like '/review/123/' everywhere.
"""

from django.urls import path
from .views import UploadView, review_view, set_filter_view, ajax_validate_row

app_name = 'assetreview'   # Namespace — lets us use 'assetreview:upload' etc.

urlpatterns = [
    # Home page — upload form (Class-Based View)
    path('', UploadView.as_view(), name='upload'),

    # Review page — shows parsed CSV rows with filter
    path('review/<str:preview_id>/', review_view, name='review'),

    # Set filter — POST, saves to cookie, redirects back
    path('review/<str:preview_id>/filter/', set_filter_view, name='set_filter'),

    # AJAX endpoint — POST, returns JSON validation result
    path('ajax/validate-row/', ajax_validate_row, name='ajax_validate_row'),
]
