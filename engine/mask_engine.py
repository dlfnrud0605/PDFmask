# engine/mask_engine.py
import io, os, time, random
import fitz  # PyMuPDF
from kiwipiepy import Kiwi

DEFAULTS = {
    "mode": "redact",            # "redact" | "highlight"
    "target_mode": "both",       # "josa_only" | "nouns_only" | "both"
    "mask_ratio": 0.95,
    "min_mask_len": 2,
    "allow_noun_span": True,
    "stroke_color": (0, 0, 0),
    "stroke_width": 1.8,
    "highlight_color": (1, 0, 0),
    "line_width": 1.8,
    "nounish_include": {"SL", "SN"},
    "josa_set": {
        "은","는","이","가","을","를","에","에서","에게","께",
        "으로","로","으로서","로서","으로써","로써","에게서",
        "한테","한테서","까지","부터","처럼","보다","와","과",
        "랑","이랑","이나","나","이나마","마다","조차","마저",
        "밖에","도","만"
    }
}

_KIWI = Kiwi(num_workers=-1)

def _is_nounish_tag(tag: str, include): return tag.startswith("N") or tag in include

def _collect_line_chars(line):
    out = []
    for span in line.get("spans", []):
        chars = span.get("chars") or []
        for ch in chars:
            out.append({"char": ch["c"], "bbox": ch["bbox"]})
    return out

def _rect_from_char_range(line_chars, s, e):
    x0=y0=1e9; x1=y1=-1e9
    for idx in range(s, e):
        if 0 <= idx < len(line_chars):
            bx0, by0, bx1, by1 = line_chars[idx]["bbox"]
            x0 = min(x0, bx0); y0 = min(y0, by0)
            x1 = max(x1, bx1); y1 = max(y1, by1)
    return fitz.Rect(x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

def _merge_rects(rects, x_gap=0.5, y_gap=0.12):
    if not rects: return []
    rects = sorted(rects, key=lambda r: (round((r.y0+r.y1)/2, 2), r.x0))
    merged, cur = [], rects[0]
    for r in rects[1:]:
        same_line = abs((r.y0+r.y1)/2 - (cur.y0+cur.y1)/2) <= y_gap * max(1.0, (cur.height + r.height)/2)
        close_h   = r.x0 <= cur.x1 + x_gap
        if same_line and close_h:
            cur = fitz.Rect(min(cur.x0, r.x0), min(cur.y0, r.y0), max(cur.x1, r.x1), max(cur.y1, r.y1))
        else:
            merged.append(cur); cur = r
    merged.append(cur)
    return merged

def _dedup_spans(spans):
    if not spans: return []
    spans = sorted(spans)
    out = [list(spans[0])]
    for s, e in spans[1:]:
        if s <= out[-1][1]: out[-1][1] = max(out[-1][1], e)
        else: out.append([s, e])
    return [tuple(x) for x in out]

def _spans_before_josa(tokens, josa_set, allow_span, min_len, include):
    spans = []
    i = 0
    while i < len(tokens):
        form, tag = tokens[i].form, tokens[i].tag
        is_josa = (form in josa_set) or tag.startswith("J")
        if is_josa and i > 0:
            j = i - 1
            if allow_span:
                while j >= 0 and _is_nounish_tag(tokens[j].tag, include): j -= 1
                j += 1
            if j <= i-1 and _is_nounish_tag(tokens[i-1].tag, include):
                s = tokens[j].start
                e = tokens[i-1].start + tokens[i-1].len
                if e - s >= min_len: spans.append((s, e))
        i += 1
    return spans

def _spans_all_noun_runs(tokens, min_len, include):
    spans, i, n = [], 0, len(tokens)
    while i < n:
        if _is_nounish_tag(tokens[i].tag, include):
            j = i + 1
            while j < n and _is_nounish_tag(tokens[j].tag, include): j += 1
            s = tokens[i].start; e = tokens[j-1].start + tokens[j-1].len
            if e - s >= min_len: spans.append((s, e))
            i = j
        else:
            i += 1
    return spans

def mask_pdf_bytes(pdf_bytes: bytes, **opts) -> bytes:
    cfg = DEFAULTS.copy(); cfg.update(opts or {})
    mode = cfg["mode"]; target_mode = cfg["target_mode"]
    mask_ratio = float(cfg["mask_ratio"]); min_len = int(cfg["min_mask_len"])
    allow_span = bool(cfg["allow_noun_span"])
    stroke_color = tuple(cfg["stroke_color"]); stroke_w = float(cfg["stroke_width"])
    hi_color = tuple(cfg["highlight_color"]); line_w = float(cfg["line_width"])
    include = set(cfg["nounish_include"]); josa_set = set(cfg["josa_set"])

    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = fitz.open()

    for pno in range(len(src)):
        page = src.load_page(pno)
        out.insert_pdf(src, from_page=pno, to_page=pno)
        marked = out[-1]

        raw = page.get_text("rawdict"); rects = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0: continue
            for line in block.get("lines", []):
                line_chars = _collect_line_chars(line)
                if not line_chars: continue
                line_text = "".join(ch["char"] for ch in line_chars)
                if not line_text.strip(): continue

                tokens = _KIWI.tokenize(line_text)
                spans = []
                if target_mode in ("both", "josa_only"):
                    spans += _spans_before_josa(tokens, josa_set, allow_span, min_len, include)
                if target_mode in ("both", "nouns_only"):
                    spans += _spans_all_noun_runs(tokens, min_len, include)
                spans = _dedup_spans(spans)

                for s, e in spans:
                    r = _rect_from_char_range(line_chars, s, e)
                    if r: rects.append(r)

        rects = _merge_rects(rects)
        if rects:
            k = int(len(rects) * max(0.0, min(1.0, mask_ratio)))
            k = max(0, min(k, len(rects)))
            if 0 < k < len(rects): rects = random.sample(rects, k)

        if mode == "redact":
            for r in rects:
                annot = marked.add_redact_annot(r, fill=(1, 1, 1))
                try: annot.set_colors(stroke=stroke_color); annot.update()
                except Exception: pass
            marked.apply_redactions()
            for r in rects: marked.draw_rect(r, color=stroke_color, width=stroke_w, fill=None, overlay=True)
        else:  # highlight
            for r in rects: marked.draw_rect(r, color=hi_color, width=line_w, fill=None, overlay=True)

        out.insert_pdf(src, from_page=pno, to_page=pno)

    src.close()
    out_io = io.BytesIO()
    out.save(out_io, garbage=4, deflate=True, clean=True)
    out.close()
    return out_io.getvalue()
