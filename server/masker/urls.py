# D:\AI\PDFmask\server\masker\urls.py

from django.urls import path
from .views import health, mask_api, upload_form

urlpatterns = [
    path("", upload_form),       # 루트에서 업로드 폼 표시
    path("health", health),
    path("mask", mask_api),      # API 방식 (curl/postman용)
    path("upload", upload_form), # 별도 경로에서도 접근 가능
]
