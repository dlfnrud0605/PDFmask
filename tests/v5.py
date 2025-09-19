# v5_josa_cloze_fixed.py
# pip install pymupdf kiwipiepy

import os
import random
import fitz  # PyMuPDF
from kiwipiepy import Kiwi

# ===== 설정 =====
PDF_IN  = "test.pdf"
PDF_OUT = "output_review_v5.pdf"

MASK_RATIO      = 0.7   # 감지된 후보 중 몇 %를 가릴지
MIN_MASK_LEN    = 2     # 너무 짧은(1글자) 명사는 제외
ALLOW_NOUN_SPAN = True  # 연속 명사(예: "딥러닝 모델")를 하나로 묶어 가릴지
FILL_COLOR      = (0, 0, 0)  # 마스킹 색상 (검정)

# 대상 조사(필요 시 추가/수정)
JOSA_SET = {
    "은","는","이","가","을","를","에","에서","에게","께",
    "으로","로","으로서","로서","으로써","로써","에게서",
    "한테","한테서","까지","부터","처럼","보다","와","과",
    "랑","이랑","이나","나","이나마","마다","조차","마저",
    "밖에","도","만"
}

# ===== 구현 =====
# Windows에서 멀티프로세싱 관련 경고/속도 문제 피하기 위해 num_workers=0 권장
kiwi = Kiwi(num_workers=0)

def merge_rects(rects, x_gap=1.0, y_gap=0.5):
    """가까운 사각형 병합(선택)."""
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: (r.y0, r.x0))
    merged = []
    cur = rects[0]
    for r in rects[1:]:
        same_line = abs((r.y0 + r.y1)/2 - (cur.y0 + cur.y1)/2) <= y_gap * max(1.0, (cur.height + r.height)/2)
        close_h   = r.x0 <= cur.x1 + x_gap
        if same_line and close_h:
            cur = fitz.Rect(min(cur.x0, r.x0), min(cur.y0, r.y0),
                            max(cur.x1, r.x1), max(cur.y1, r.y1))
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

    # tokenize: 안정적으로 Token(form, tag, start, len) 리스트를 반환
    tokens = kiwi.tokenize(line_text)

    i = 0
    while i < len(tokens):
        t = tokens[i]
        form = t.form
        tag  = t.tag

        is_josa = (form in JOSA_SET) or (tag.startswith("J"))  # 일반 조사 전반
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
    """
    rawdict의 line 구조에서 문자 단위 배열을 수집.
    span["chars"]가 없으면 span bbox를 글자수로 균등분할(최후 수단).
    """
    line_chars = []
    for span in line.get("spans", []):
        text  = span.get("text", "") or ""
        chars = span.get("chars")
        if chars:
            for ch in chars:
                # ch: {'c': '문자', 'bbox': [x0,y0,x1,y1], ...}
                line_chars.append({"char": ch["c"], "bbox": ch["bbox"]})
        else:
            # 폴백: 정밀도 떨어짐
            if not text:
                continue
            x0, y0, x1, y1 = span["bbox"]
            w = (x1 - x0) / max(1, len(text))
            for i, c in enumerate(text):
                line_chars.append({
                    "char": c,
                    "bbox": [x0 + i*w, y0, x0 + (i+1)*w, y1]
                })
    return line_chars

def josa_cloze_mask(pdf_in, pdf_out):
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
        mask_rects = []

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

                # [명사]+[조사] 구간 찾기
                spans = noun_before_josa_spans(line_text)
                for (s, e) in spans:
                    rect = rect_from_char_range(line_chars, s, e)
                    if rect:
                        mask_rects.append(rect)

        # 병합(선택) 및 비율 적용
        mask_rects = merge_rects(mask_rects)
        if mask_rects:
            k = int(len(mask_rects) * MASK_RATIO)
            if 0 < k < len(mask_rects):
                mask_rects = random.sample(mask_rects, k)

            for r in mask_rects:
                mpage.add_redact_annot(r, fill=FILL_COLOR)

        mpage.apply_redactions()
        print(f"  - {pno+1} / {len(doc)} 페이지 처리 완료 (마스킹 후보: {len(mask_rects)})")

    new_doc.save(pdf_out, garbage=4, deflate=True, clean=True)
    new_doc.close()
    doc.close()
    print(f"\n완료: '{pdf_out}' 저장")

if __name__ == "__main__":
    josa_cloze_mask(PDF_IN, PDF_OUT)
