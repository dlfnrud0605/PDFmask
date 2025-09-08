import os
import fitz  # PyMuPDF
from konlpy.tag import Okt
import random

# --- 설정 ---
pdf_file_path = "test.pdf"  # 처리할 원본 PDF 파일 이름
output_file_path = "output_review_v3.pdf" # 결과물을 저장할 파일 이름
mask_ratio = 0.7  # 각 페이지에서 키워드 중 몇 퍼센트를 가릴지 (0.7 = 70%)
# --- 설정 끝 ---

# --- 메인 로직 ---
if not os.path.exists(pdf_file_path):
    print(f"오류: '{pdf_file_path}' 파일을 찾을 수 없습니다.")
else:
    try:
        okt = Okt()
        
        doc = fitz.open(pdf_file_path)
        new_doc = fitz.open()

        print(f"PDF 문서 '{os.path.basename(pdf_file_path)}' 처리 시작... (총 {len(doc)} 페이지)")

        for page_num in range(len(doc)):
            original_page = doc.load_page(page_num)

            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            masked_page = new_doc[-1]

            # [수정] 두 가지 텍스트 정보를 모두 사용합니다.
            page_dict = original_page.get_text("rawdict") # 정밀 분석용
            words_simple = original_page.get_text("words") # 안정적인 대체용

            keywords_to_mask = []
            
            # 1. 정밀 분석 시도
            processed_texts = set() # 이미 처리된 텍스트를 기록
            for block in page_dict.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            span_text = span.get("text", "").strip()
                            span_chars = span.get("chars", [])

                            if not span_text or not span_chars:
                                continue
                            
                            processed_texts.add(span_text) # 정밀 분석 시도한 텍스트로 기록

                            try:
                                tokens = okt.pos(span_text, norm=False, stem=False)
                                char_index = 0
                                for token, pos in tokens:
                                    token_len = len(token)
                                    if char_index + token_len > len(span_chars):
                                        raise IndexError("Token length mismatch") # 오류 강제 발생

                                    if pos in ['Noun', 'Verb', 'Adjective', 'Alpha', 'Number']:
                                        start_bbox = span_chars[char_index]['bbox']
                                        end_bbox = span_chars[char_index + token_len - 1]['bbox']
                                        keyword_rect = fitz.Rect(start_bbox[0], start_bbox[1], end_bbox[2], end_bbox[3])
                                        keywords_to_mask.append(keyword_rect)
                                    char_index += token_len
                            except Exception:
                                continue # 정밀 분석 실패 시 조용히 넘어감

            # 2. [수정] 정밀 분석이 실패했을 경우를 대비한 2차 분석 (안정적인 방식)
            for word_info in words_simple:
                word_rect = fitz.Rect(word_info[:4])
                word_text = word_info[4].strip()

                # 정밀 분석에서 이미 성공적으로 처리된 텍스트는 건너뜀
                if word_text in processed_texts:
                    continue
                
                # 정밀 분석에서 실패한 단어들만 대상으로 키워드가 포함되어 있는지 확인
                try:
                    tokens = okt.pos(word_text, norm=True, stem=False)
                    if any(pos in ['Noun', 'Verb', 'Adjective', 'Alpha'] for _, pos in tokens):
                        keywords_to_mask.append(word_rect) # 단어 덩어리 전체를 가릴 대상으로 추가
                except Exception:
                    pass

            # 가릴 대상 중 일부만 랜덤으로 선택
            if keywords_to_mask:
                num_to_mask = int(len(keywords_to_mask) * mask_ratio)
                if num_to_mask > 0:
                    random_rects = random.sample(keywords_to_mask, num_to_mask)
                    for rect in random_rects:
                        masked_page.draw_rect(rect, color=(0, 0, 0), fill=(1, 1, 1), width=1.5)

            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            print(f"  - {page_num + 1} 페이지 처리 완료 (문제+정답 생성).")

        new_doc.save(output_file_path, garbage=4, deflate=True, clean=True)
        print(f"\n✨ 완료: 최종 복습용 PDF가 '{output_file_path}'로 저장되었습니다.")

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
    finally:
        if 'doc' in locals():
            doc.close()
        if 'new_doc' in locals():
            new_doc.close()