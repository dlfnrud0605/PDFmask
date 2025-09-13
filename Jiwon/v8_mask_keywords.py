# v8_mask_keywords.py
# pip install pymupdf kiwipiepy
import os, time, random
import fitz  # PyMuPDF
from kiwipiepy import Kiwi

# ===== 설정 =====
PDF_IN   = "test_1.pdf"
PDF_OUT  = "output_review_v8.pdf"

MODE         = "redact"   # "redact" | "highlight"
TARGET_MODE  = "both"        # "josa_only" | "nouns_only" | "both"
MASK_RATIO   = 0.95           # 후보 중 몇 %를 처리할지 (1.0 = 전부)
MIN_MASK_LEN = 2             # 너무 짧은(1글자) 명사 제외
ALLOW_NOUN_SPAN = True       # 연속 명사 한 덩어리로

# 가림막(흰 배경 + 검은 테두리) - redact 모드일 때 사용
STROKE_COLOR = (0, 0, 0)     # 검은 테두리
STROKE_WIDTH = 1.8

# 명사처럼 취급할 태그(영문/숫자 포함할지 여부)
NOUNISH_INCLUDE = {"SL", "SN"}   # 영문, 숫자 포함. 순수 한글 명사만 원하면 set()로.

# highlight 모드 스타일(빨간 테두리, 내부 투명)
HIGHLIGHT_COLOR = (1, 0, 0)  # 빨강
LINE_WIDTH      = 1.8

# 대상 조사(필요 시 추가/수정)
JOSA_SET = {
    "은","는","이","가","을","를","에","에서","에게","께",
    "으로","로","으로서","로서","으로써","로써","에게서",
    "한테","한테서","까지","부터","처럼","보다","와","과",
    "랑","이랑","이나","나","이나마","마다","조차","마저",
    "밖에","도","만"
    # 필요시 '등','들','중'을 추가할 수 있으나 일반적으로 조사라기보다 의존명사/접미사 분류입니다.
}

kiwi = Kiwi(num_workers=-1)  # Windows에서 안정적

# ===== 유틸 =====
def is_nounish_tag(tag: str) -> bool:
    return tag.startswith("N") or tag in NOUNISH_INCLUDE

def collect_line_chars(line):
    # 문자 bbox가 없는 span은 건너뜀(균등분할 폴백은 높이 과장 문제를 유발)
    out = []
    for span in line.get("spans", []):
        chars = span.get("chars")
        if not chars:
            continue
        for ch in chars:
            out.append({"char": ch["c"], "bbox": ch["bbox"]})
    return out

def rect_from_char_range(line_chars, s, e):
    x0=y0=1e9; x1=y1=-1e9
    for idx in range(s, e):
        if 0 <= idx < len(line_chars):
            bx0, by0, bx1, by1 = line_chars[idx]["bbox"]
            x0 = min(x0, bx0); y0 = min(y0, by0)
            x1 = max(x1, bx1); y1 = max(y1, by1)
    if x1 > x0 and y1 > y0:
        return fitz.Rect(x0, y0, x1, y1)
    return None

def merge_rects(rects, x_gap=0.5, y_gap=0.12):
    if not rects: return []
    rects = sorted(rects, key=lambda r: (round((r.y0+r.y1)/2, 2), r.x0))
    merged, cur = [], rects[0]
    for r in rects[1:]:
        same_line = abs((r.y0+r.y1)/2 - (cur.y0+cur.y1)/2) <= y_gap * max(1.0, (cur.height + r.height)/2)
        close_h   = r.x0 <= cur.x1 + x_gap
        if same_line and close_h:
            cur = fitz.Rect(min(cur.x0, r.x0), min(cur.y0, r.y0),
                            max(cur.x1, r.x1), max(cur.y1, r.y1))
        else:
            merged.append(cur); cur = r
    merged.append(cur)
    return merged

def dedup_spans(spans):
    # (s,e) 중첩/연속 구간 병합
    if not spans: return []
    spans = sorted(spans)
    out = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(x) for x in out]

# ===== 패턴 탐지 =====
def spans_before_josa(tokens):
    spans = []
    i = 0
    while i < len(tokens):
        form, tag = tokens[i].form, tokens[i].tag
        is_josa = (form in JOSA_SET) or tag.startswith("J")
        if is_josa and i > 0:
            # 왼쪽으로 명사 연속 확장
            j = i - 1
            if ALLOW_NOUN_SPAN:
                while j >= 0 and is_nounish_tag(tokens[j].tag):
                    j -= 1
                j += 1
            if j <= i-1 and is_nounish_tag(tokens[i-1].tag):
                s = tokens[j].start
                e = tokens[i-1].start + tokens[i-1].len
                if e - s >= MIN_MASK_LEN:
                    spans.append((s, e))
        i += 1
    return spans

def spans_all_noun_runs(tokens):
    # 조사 여부와 무관하게 연속된 명사(및 선택 SL/SN)를 전부
    spans = []
    i = 0
    n = len(tokens)
    while i < n:
        if is_nounish_tag(tokens[i].tag):
            j = i + 1
            while j < n and is_nounish_tag(tokens[j].tag):
                j += 1
            s = tokens[i].start
            e = tokens[j-1].start + tokens[j-1].len
            if e - s >= MIN_MASK_LEN:
                spans.append((s, e))
            i = j
        else:
            i += 1
    return spans

# ===== 저장 안전하게 =====
def safe_save_pdf(doc, out_path):
    tmp = out_path + ".tmp"
    doc.save(tmp, garbage=4, deflate=True, clean=True)
    doc.close()
    # 교체 재시도(파일 잠금 대비)
    for _ in range(6):
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
            os.replace(tmp, out_path)
            return
        except PermissionError:
            time.sleep(0.5)
    os.replace(tmp, out_path)

# ===== 메인 =====
def run(pdf_in, pdf_out):
    if not os.path.exists(pdf_in):
        print(f"오류: '{pdf_in}' 없음"); return

    src = fitz.open(pdf_in)
    out = fitz.open()
    print(f"처리 시작: {os.path.basename(pdf_in)} ({len(src)} 페이지)")

    for pno in range(len(src)):
        page = src.load_page(pno)

        # --- 1) 먼저 '마크된 복사본' 페이지 생성 ---
        out.insert_pdf(src, from_page=pno, to_page=pno)
        marked = out[-1]

        raw = page.get_text("rawdict")
        rects = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_chars = collect_line_chars(line)
                if not line_chars:
                    continue
                line_text = "".join(ch["char"] for ch in line_chars)
                if not line_text.strip():
                    continue

                tokens = kiwi.tokenize(line_text)

                spans = []
                if TARGET_MODE in ("both", "josa_only"):
                    spans += spans_before_josa(tokens)
                if TARGET_MODE in ("both", "nouns_only"):
                    spans += spans_all_noun_runs(tokens)

                spans = dedup_spans(spans)

                for s, e in spans:
                    r = rect_from_char_range(line_chars, s, e)
                    if r: rects.append(r)

        rects = merge_rects(rects)

        # 비율 조절
        if rects:
            k = int(len(rects) * MASK_RATIO)
            k = max(0, min(k, len(rects)))
            if 0 < k < len(rects):
                rects = random.sample(rects, k)

        # ---- 표시 / 가림막 적용 ----
        if MODE == "redact":
            # (A) 흰색으로 가림막 적용
            for r in rects:
                # 미리보기 테두리색은 설정 가능하나, 두께는 불가(표준 제한)
                annot = marked.add_redact_annot(r, fill=(1, 1, 1))
                try:
                    annot.set_colors(stroke=STROKE_COLOR)
                    annot.update()
                except Exception:
                    pass
            marked.apply_redactions()

            # (B) 적용 후, 검은 테두리를 다시 그림
            for r in rects:
                marked.draw_rect(
                    r, color=STROKE_COLOR, width=STROKE_WIDTH,
                    fill=None, overlay=True
                )

        elif MODE == "highlight":
            # 빨간 테두리 + 내부 투명 (overlay=True로 위에 그리기)
            for r in rects:
                marked.draw_rect(
                    r, color=HIGHLIGHT_COLOR, width=LINE_WIDTH,
                    fill=None, overlay=True
                )

        # --- 2) 이어서 같은 원본 페이지를 '수정 없이' 한번 더 삽입 ---
        out.insert_pdf(src, from_page=pno, to_page=pno)

        print(f"  - {pno+1}/{len(src)}: [마크된 복사본] + [원본] 삽입 (박스 {len(rects)})")

    safe_save_pdf(out, pdf_out)
    src.close()
    print(f"완료: {pdf_out}")

if __name__ == "__main__":
    run(PDF_IN, PDF_OUT)