"""
Main URL Configuration
Connects the project to the assetreview app URLs
"""

from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('assetreview.urls')),
]

# Serve uploaded media files in development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
