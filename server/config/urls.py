# D:\AI\PDFmask\server\config\urls.py

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("masker.urls")),   # /health, /mask
]
