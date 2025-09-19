"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.
"""

# server/config/wsgi.py
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.getenv('DJANGO_SETTINGS_MODULE', 'config.settings.prod'))

application = get_wsgi_application()
