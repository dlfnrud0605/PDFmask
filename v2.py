import os
import fitz  # PyMuPDF
from konlpy.tag import Okt
import random

# --- 설정 ---
pdf_file_path = "test.pdf"  # 처리할 원본 PDF 파일 이름
output_file_path = "output_review.pdf" # 결과물을 저장할 파일 이름
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

            # 1. 문제 페이지 생성: 원본 페이지를 new_doc에 그대로 복사합니다.
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
            # 방금 복사한 페이지(new_doc의 마지막 페이지)를 가져와서 마스킹 작업을 합니다.
            masked_page = new_doc[-1]

            words = original_page.get_text("words")

            keywords_to_mask = []
            for word_info in words:
                x0, y0, x1, y1, word_text = word_info[:5]

                if len(word_text) < 2:
                    continue

                is_keyword = False
                try:
                    tokens = okt.pos(word_text, norm=True, stem=True)
                    for token, pos in tokens:
                        if pos in ['Noun', 'Verb', 'Adjective', 'Alpha']:
                            is_keyword = True
                            break
                except Exception as e:
                    pass
                
                if is_keyword:
                    rect = fitz.Rect(x0, y0, x1, y1)
                    keywords_to_mask.append(rect)
            
            num_to_mask = int(len(keywords_to_mask) * mask_ratio)
            if num_to_mask > 0:
                random_keywords = random.sample(keywords_to_mask, num_to_mask)
                # 복사된 페이지 위에 직접 마스킹합니다.
                for rect in random_keywords:
                    masked_page.draw_rect(rect, color=(0, 0, 0), fill=(1, 1, 1), width=1.5)

            # 2. 정답 페이지 생성: 원본 페이지를 한 번 더 그대로 복사합니다.
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

            print(f"  - {page_num + 1} 페이지 처리 완료 (문제+정답 생성).")

        new_doc.save(output_file_path, garbage=4, deflate=True, clean=True)
        print(f"\n✨ 완료: 복습용 PDF가 '{output_file_path}'로 저장되었습니다.")

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
    finally:
        if 'doc' in locals():
            doc.close()
        if 'new_doc' in locals():
            new_doc.close()