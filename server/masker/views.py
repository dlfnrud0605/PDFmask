# D:\AI\PDFmask\server\masker\views.py
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from engine.mask_engine import mask_pdf_bytes


def health(request):
    return JsonResponse({"status": "ok"})


@require_http_methods(["GET", "POST"])
def upload_form(request):
    """
    GET  : 업로드 폼 HTML 렌더
    POST : 업로드된 PDF를 마스킹하여 masked.pdf 로 반환
    """
    if request.method == "GET":
        return render(request, "masker/upload.html")

    # POST
    f = request.FILES.get("file")
    if not f:
        return HttpResponseBadRequest("파일이 필요합니다 (field name: file)")

    # 옵션 파싱
    def _get(name, default=None):
        return request.POST.get(name, request.GET.get(name, default))

    opts = {}
    m = _get("mode", "redact")
    if m:
        opts["mode"] = m

    t = _get("target_mode", "both")
    if t:
        opts["target_mode"] = t

    r = _get("mask_ratio", "0.95")
    try:
        opts["mask_ratio"] = float(r)
    except ValueError:
        return HttpResponseBadRequest("mask_ratio must be float")

    ml = _get("min_mask_len")
    if ml is not None and ml != "":
        try:
            opts["min_mask_len"] = int(ml)
        except ValueError:
            return HttpResponseBadRequest("min_mask_len must be int")

    ans = _get("allow_noun_span")
    if ans is not None and ans != "":
        opts["allow_noun_span"] = str(ans).lower() in ("1", "true", "yes", "on")

    try:
        out_bytes = mask_pdf_bytes(f.read(), **opts)
    except Exception as e:
        return HttpResponseBadRequest(f"처리 오류: {e}")

    resp = HttpResponse(out_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="masked.pdf"'
    return resp


@csrf_exempt
@require_http_methods(["POST"])
def mask_api(request):
    """
    multipart/form-data:
      file: PDF 파일
    옵션(쿼리스트링 또는 form field):
      mode: redact|highlight
      target_mode: both|josa_only|nouns_only
      mask_ratio: 0.0~1.0
      min_mask_len: int
      allow_noun_span: true|false
    """
    f = request.FILES.get("file")
    if not f:
        return HttpResponseBadRequest("file field is required (PDF)")

    # 옵션 파싱 유틸
    def _get(name, default=None):
        return request.POST.get(name, request.GET.get(name, default))

    opts = {}
    m = _get("mode")
    if m:
        opts["mode"] = m

    t = _get("target_mode")
    if t:
        opts["target_mode"] = t

    r = _get("mask_ratio")
    if r is not None:
        try:
            opts["mask_ratio"] = float(r)
        except ValueError:
            return HttpResponseBadRequest("mask_ratio must be float")

    ml = _get("min_mask_len")
    if ml is not None:
        try:
            opts["min_mask_len"] = int(ml)
        except ValueError:
            return HttpResponseBadRequest("min_mask_len must be int")

    ans = _get("allow_noun_span")
    if ans is not None:
        opts["allow_noun_span"] = str(ans).lower() in ("1", "true", "yes", "on")

    try:
        out_bytes = mask_pdf_bytes(f.read(), **opts)
    except Exception as e:
        return HttpResponseBadRequest(f"processing error: {e}")

    resp = HttpResponse(out_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="masked.pdf"'
    return resp
