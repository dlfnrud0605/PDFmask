# PDFmask

텍스트 기반 PDF 문서에서 **명사 + 조사 패턴을 감지해 자동으로 마스킹**하는 프로젝트입니다.
Django 기반 API 서버 + 독립적인 마스킹 엔진 구조로 되어 있어, 연구/실험 환경과 운영 환경을 모두 지원합니다.

---

## 프로젝트 구조

```
PDFmask/
├─ engine/                 # 마스킹 엔진 (v8_mask_keywords.py 모듈화)
│  └─ mask_engine.py
├─ server/                 # Django 프로젝트/앱
│  ├─ manage.py
│  ├─ config/              # Django 프로젝트 (settings/urls/wsgi)
│  │  └─ settings/         # settings 분리 (base/dev/prod)
│  └─ masker/              # Django 앱 (API + HTML 뷰)
│      └─ templates/masker/upload.html
├─ docker/                 # 배포 관련 설정
│  ├─ Dockerfile
│  ├─ entrypoint.sh
│  └─ nginx.conf
├─ sample_data/            # 예제 PDF (로컬 테스트용)
├─ tests/                  # 단위 테스트 (Pytest)
│  ├─ test_engine.py
│  └─ test_views.py
├─ .env.example            # 환경변수 템플릿 (SECRET_KEY 등)
├─ requirements.txt        # Python 패키지
├─ .gitignore
└─ README.md
```

### 설계 포인트

* **관심사 분리 (Separation of Concerns)**

  * `engine/`: 마스킹 핵심 로직 (PyMuPDF + Kiwi 기반)
  * `server/`: Django API + HTML 폼 제공

* **유지보수 용이**

  * 새 기능 추가 → `engine/` 수정
  * Django는 그대로 두고 라우팅만 확장

* **환경 분리**

  * `settings/dev.py`: 로컬 개발용 (DEBUG=True)
  * `settings/prod.py`: 운영용 (DEBUG=False, 보안/호스트 제한)

---

## 설치 & 실행

### 1. 환경 준비

```bash
git clone https://github.com/yourname/PDFmask.git
cd PDFmask
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 개발 서버 실행

```bash
cd server
python manage.py migrate
python manage.py runserver
```

접속 확인:

* `http://127.0.0.1:8000/` → 업로드 폼
* `http://127.0.0.1:8000/health` → {"status": "ok"}
* `http://127.0.0.1:8000/mask` → API 엔드포인트

### 3. 운영 모드 실행

```bash
set DJANGO_SETTINGS_MODULE=config.settings.prod   # Windows
export DJANGO_SETTINGS_MODULE=config.settings.prod  # Linux/Mac
python manage.py runserver
```

---

## 📡 API 엔드포인트

### Health Check

`GET /health`
응답: `{"status": "ok"}`

### Mask API

`POST /mask`
Form-data:

* `file`: PDF 파일 (필수)
* `mode`: `redact` | `highlight`
* `target_mode`: `both` | `josa_only` | `nouns_only`
* `mask_ratio`: 0.0 \~ 1.0
* `min_mask_len`: int (기본 2)
* `allow_noun_span`: true|false

응답: 마스킹된 PDF 파일 다운로드 (`masked.pdf`)

### 업로드 폼

`GET /` 또는 `GET /upload` → 브라우저 업로드 페이지 제공

---

## 🧪 테스트

### Pytest 실행

```bash
pytest tests/
```

### 샘플 데이터 확인

```bash
curl -X POST "http://127.0.0.1:8000/mask?mode=redact&target_mode=both&mask_ratio=0.95" \
     -F "file=@sample_data/test_1.pdf" \
     -o sample_data/masked.pdf
```

---

## Docker (선택)

```bash
cd docker
docker build -t pdfmask ..
docker run -p 8000:8000 pdfmask
```

→ 운영 배포 시 Gunicorn + Nginx 조합 사용 권장.

---

## 환경변수 (.env)

`.env.example` 참고:

```
DJANGO_SECRET_KEY=change-me
DJANGO_SETTINGS_MODULE=config.settings.prod
```

---

## 배포 시나리오

1. 로컬에서 기능 개발 + 테스트
2. GitHub에 push
3. 서버(GCP VM 등)에서 pull
4. Docker 빌드 & 실행
5. Nginx 리버스프록시 + HTTPS 적용