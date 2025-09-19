# v6_josa_highlight.py
# 조사 앞 명사(구)만 빨간 박스로 "표시" (마스킹/삭제 아님)
# pip install pymupdf kiwipiepy

import os
import random
import fitz  # PyMuPDF
from kiwipiepy import Kiwi

# ===== 설정 =====
PDF_IN  = "test_1.pdf"
PDF_OUT = "output_review_v6_highlight_1.pdf"

MASK_RATIO      = 1   # 감지된 후보 중 몇 %를 표시할지
MIN_MASK_LEN    = 2     # 너무 짧은(1글자) 명사는 제외
ALLOW_NOUN_SPAN = True  # 연속 명사(예: "딥러닝 모델")를 하나로 묶어서 표시할지

# 표시용 스타일(빨간 테두리)
HIGHLIGHT_COLOR = (1, 0, 0)  # RGB 0~1
LINE_WIDTH      = 1.8
STROKE_ALPHA    = 1.0        # 테두리 불투명도(0~1)
FILL_ALPHA      = 0.0        # 내부 채움 투명도(0이면 투명)
FILL_COLOR      = None       # None이면 채움 없음. 반투명 채움 원하면 (1,0,0)과 FILL_ALPHA<1.0 사용

# 대상 조사(필요 시 추가/수정)
JOSA_SET = {
    "은","는","이","가","을","를","에","에서","에게","께",
    "으로","로","으로서","로서","으로써","로써","에게서",
    "한테","한테서","까지","부터","처럼","보다","와","과",
    "랑","이랑","이나","나","이나마","마다","조차","마저",
    "밖에","도","만","등", "들", "중"
}

# Windows에서 권장: 이전 버전과 유사 동작
kiwi = Kiwi(num_workers=-1)

def merge_rects(rects, x_gap=0.5, y_gap=0.15):  # y_gap 확 낮춤
    if not rects: return []
    rects = sorted(rects, key=lambda r: (round((r.y0+r.y1)/2, 1), r.x0))
    merged, cur = [], rects[0]
    for r in rects[1:]:
        same_line = abs((r.y0+r.y1)/2 - (cur.y0+cur.y1)/2) <= y_gap * max(1.0, (cur.height + r.height)/2)
        close_h   = r.x0 <= cur.x1 + x_gap
        if same_line and close_h:
            cur = fitz.Rect(min(cur.x0, r.x0), min(cur.y0, r.y0), max(cur.x1, r.x1), max(cur.y1, r.y1))
        else:
            merged.append(cur)
            cur = r
    merged.append(cur)
    return merged

def noun_before_josa_spans(line_text: str):
    """
    한 줄의 텍스트에서 [명사류]+[조사] 패턴을 찾아
    (start_char_idx, end_char_idx) 구간 리스트 반환.
    """
    spans = []
    if not line_text:
        return spans

    tokens = kiwi.tokenize(line_text)  # 0.21.0에는 match_all 없음

    i = 0
    while i < len(tokens):
        t = tokens[i]
        form = t.form
        tag  = t.tag

        is_josa = (form in JOSA_SET) or tag.startswith("J")
        if is_josa and i > 0:
            # 왼쪽으로 명사 구간 확장
            j = i - 1
            if ALLOW_NOUN_SPAN:
                while j >= 0 and tokens[j].tag.startswith("N"):
                    j -= 1
                j += 1
            # 최소 한 개의 명사 확보
            if j <= i - 1 and tokens[i-1].tag.startswith("N"):
                start = tokens[j].start
                end   = tokens[i-1].start + tokens[i-1].len
                if end - start >= MIN_MASK_LEN:
                    spans.append((start, end))
        i += 1
    return spans

def rect_from_char_range(line_chars, s, e):
    """문자 배열(line_chars)에서 s..e-1 범위 bbox들을 합쳐 Rect 반환."""
    x0=y0=1e9
    x1=y1=-1e9
    for idx in range(s, e):
        if 0 <= idx < len(line_chars):
            bx0, by0, bx1, by1 = line_chars[idx]["bbox"]
            x0 = min(x0, bx0); y0 = min(y0, by0)
            x1 = max(x1, bx1); y1 = max(y1, by1)
    if x1 > x0 and y1 > y0:
        return fitz.Rect(x0, y0, x1, y1)
    return None

def collect_line_chars(line):
    line_chars = []
    for span in line.get("spans", []):
        chars = span.get("chars")
        if not chars:
            # 폴백 제거: 라인 bbox 사용하지 않음 (y가 과하게 커지는 원인)
            continue
        for ch in chars:
            line_chars.append({"char": ch["c"], "bbox": ch["bbox"]})
    return line_chars

def josa_highlight(pdf_in, pdf_out):
    if not os.path.exists(pdf_in):
        print(f"오류: '{pdf_in}' 파일을 찾을 수 없습니다.")
        return

    doc = fitz.open(pdf_in)
    new_doc = fitz.open()
    print(f"PDF 문서 '{os.path.basename(pdf_in)}' 처리 시작... (총 {len(doc)} 페이지)")

    for pno in range(len(doc)):
        page = doc.load_page(pno)
        new_doc.insert_pdf(doc, from_page=pno, to_page=pno)
        mpage = new_doc[-1]

        raw = page.get_text("rawdict")
        rects = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue  # 텍스트 블록만
            for line in block.get("lines", []):
                line_chars = collect_line_chars(line)
                if not line_chars:
                    continue
                line_text = "".join(ch["char"] for ch in line_chars)
                if not line_text.strip():
                    continue

                spans = noun_before_josa_spans(line_text)
                for (s, e) in spans:
                    r = rect_from_char_range(line_chars, s, e)
                    if r:
                        rects.append(r)

        rects = merge_rects(rects)

        # 비율 적용 및 "표시"만 수행
        if rects:
            k = int(len(rects) * MASK_RATIO)
            if 0 < k < len(rects):
                rects = random.sample(rects, k)

            for r in rects:
                # 핵심: draw_rect로 빨간 박스만 그림. 텍스트 삭제 없음.
                mpage.draw_rect(
                    r,
                    color=HIGHLIGHT_COLOR,
                    fill=FILL_COLOR,             # None이면 채움 없음
                    width=LINE_WIDTH,
                    stroke_opacity=STROKE_ALPHA,
                    fill_opacity=FILL_ALPHA,
                    overlay=True                 # 기존 내용 위에 그리기
                )

        print(f"  - {pno+1} / {len(doc)} 페이지 표시 완료 (표시 박스: {len(rects)})")

    new_doc.save(pdf_out, garbage=4, deflate=True, clean=True)
    new_doc.close()
    doc.close()
    print(f"\n완료: '{pdf_out}' 저장")

if __name__ == "__main__":
    josa_highlight(PDF_IN, PDF_OUT)
