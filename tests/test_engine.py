# \test\test_engine.py

from engine.mask_engine import mask_pdf_bytes

def test_basic_masking():
    with open("sample_data/test_1.pdf", "rb") as f:
        out = mask_pdf_bytes(f.read())
    assert isinstance(out, bytes)
