# pip install pymupdf kiwipiepy
import fitz  # PyMuPDF
from kiwipiepy import Kiwi

# 1) 조사 세트: 필요에 따라 추가/조정
JOSA_SET = {
    "은","는","이","가","을","를","에","에서","에게","께","으로","로","으로서","로서",
    "으로써","로써","에게서","한테","한테서","까지","부터","처럼","보다","와","과",
    "랑","이랑","이나","나","이나마","마다","조차","마저","밖에","도","만"
}

# 2) 마스킹 대상 필터(예: 최소 글자수, 불용어 등)
MIN_MASK_LEN = 2       # 1글자 명사(예: '수')는 보존하고 싶다면 2 이상 권장
ALLOW_SUBNOUN = True   # 연속된 명사/의존명사 조합을 하나의 명사구로 확장할지

kiwi = Kiwi()

def mask_noun_before_josa_in_pdf(in_pdf: str, out_pdf: str):
    doc = fitz.open(in_pdf)

    for pno in range(len(doc)):
        page = doc[pno]

        # --------------- 문자 단위 추출 ---------------
        # rawdict -> blocks -> lines -> spans -> chars
        raw = page.get_text("rawdict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                # 한 줄(시각적으로 같은 baseline)의 span들을 이어서 "문자 시퀀스 + 좌표" 구성
                line_chars = []
                for span in line.get("spans", []):
                    # 각 span은 font/size가 동일한 조각. span["text"]와 span["chars"] 동시 사용.
                    # 일부 PDF는 "chars"가 없을 수 있어 방어적 처리
                    chars = span.get("chars")
                    text  = span.get("text", "")
                    if not text:
                        continue
                    if chars:
                        for ch in chars:
                            # ch = {'c': '한', 'bbox': [x0,y0,x1,y1], ...}
                            line_chars.append({
                                "char": ch["c"],
                                "bbox": ch["bbox"]
                            })
                    else:
                        # 폴백: 문자 폭을 균등분할(정밀도 떨어짐)
                        # span bbox를 글자수로 등분 (가능하면 사용 안 함)
                        x0,y0,x1,y1 = span["bbox"]
                        if len(text) > 0:
                            w = (x1 - x0) / len(text)
                            for i, c in enumerate(text):
                                line_chars.append({
                                    "char": c,
                                    "bbox": [x0 + i*w, y0, x0 + (i+1)*w, y1]
                                })

                if not line_chars:
                    continue

                # --------------- 줄 텍스트와 인덱스 매핑 ---------------
                line_text = "".join([c["char"] for c in line_chars])

                # --------------- 형태소 분석으로 [명사]+[조사] 탐지 ---------------
                # normalize_coda=False 로 원문 보존 성향, 필요시 옵션 조정
                morphs = kiwi.analyze(line_text, top_n=1)[0].tokens
                # morphs: token.form, token.tag, token.start, token.len (문자 인덱스 기준)

                # 조사 위치를 보며, 바로 앞의 명사(구)를 결정
                i = 0
                to_mask_spans = []  # [(start_idx, end_idx)]
                while i < len(morphs):
                    m = morphs[i]
                    # 한국어 품사: NNG(일반명사), NNP(고유명사), NNB(의존명사) 등
                    is_noun = m.tag.startswith("N")
                    is_josa = (m.form in JOSA_SET) or m.tag.startswith("J")  # J* 품사는 일반적으로 조사류

                    if is_josa and i > 0:
                        # 바로 앞의 명사/명사열을 찾는다
                        j = i - 1
                        if ALLOW_SUBNOUN:
                            # 왼쪽으로 연속된 N* 토큰을 확장
                            while j >= 0 and morphs[j].tag.startswith("N"):
                                j -= 1
                            j += 1
                        # j..i-1 가 명사 또는 명사열, 그 텍스트 범위 확보
                        if j <= i - 1 and morphs[j].tag.startswith("N"):
                            start = morphs[j].start
                            end   = morphs[i-1].start + morphs[i-1].len
                            if end - start >= MIN_MASK_LEN:
                                to_mask_spans.append((start, end))
                    i += 1

                # --------------- 문자 인덱스 → 좌표(사각형) 합성 ---------------
                for (s, e) in to_mask_spans:
                    # s..e-1 문자에 해당하는 bbox들을 모아 하나의 사각형으로 유니온
                    x0=y0=1e9
                    x1=y1=-1e9
                    for idx in range(s, e):
                        if idx < 0 or idx >= len(line_chars):
                            continue
                        cx0, cy0, cx1, cy1 = line_chars[idx]["bbox"]
                        x0 = min(x0, cx0); y0 = min(y0, cy0)
                        x1 = max(x1, cx1); y1 = max(y1, cy1)
                    if x1 > x0 and y1 > y0:
                        rect = fitz.Rect(x0, y0, x1, y1)
                        page.add_redact_annot(rect, fill=(0, 0, 0))  # 검정 박스

        # 페이지 단위로 실제 마스킹 적용
        page.apply_redactions()

    doc.save(out_pdf)

# 실행 예시
mask_noun_before_josa_in_pdf("test.pdf", "result_v4.pdf")
