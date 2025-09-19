import os
import fitz  # PyMuPDF
from konlpy.tag import Okt

# --- 설정 ---
pdf_file_path = "test.pdf"  # 처리할 원본 PDF 파일 이름
output_file_path = "output_masked.pdf" # 결과물을 저장할 파일 이름
# --- 설정 끝 ---

# --- 메인 로직 ---
if not os.path.exists(pdf_file_path):
    print(f"오류: '{pdf_file_path}' 파일을 찾을 수 없습니다.")
else:
    try:
        # 형태소 분석기 준비
        okt = Okt()
        
        # 원본 PDF 문서를 엽니다.
        doc = fitz.open(pdf_file_path)
        print(f"PDF 문서 '{os.path.basename(pdf_file_path)}' 처리 시작... (총 {len(doc)} 페이지)")

        # 문서의 모든 페이지를 순회합니다.
        for page_num, page in enumerate(doc):
            # "words" 옵션으로 페이지의 모든 단어와 그 좌표를 한 번에 추출합니다.
            words = page.get_text("words")

            # 추출된 각 단어를 순회하며 마스킹 대상을 찾습니다.
            for word_info in words:
                x0, y0, x1, y1, word_text = word_info[:5]

                # 단어가 2글자 미만이면 건너뜁니다.
                if len(word_text) < 2:
                    continue

                # 형태소 분석을 통해 가릴 단어인지 판단
                is_keyword = False
                try:
                    tokens = okt.pos(word_text, norm=True, stem=True)
                    for token, pos in tokens:
                        # 명사, 동사, 형용사, 알파벳 등을 키워드로 간주
                        if pos in ['Noun', 'Verb', 'Adjective', 'Alpha']:
                            is_keyword = True
                            break # 키워드임을 확인하면 더 분석할 필요 없음
                except Exception as e:
                    # Okt가 처리하지 못하는 일부 특수 문자 등의 오류 방지
                    # print(f"형태소 분석 오류 발생 (단어: {word_text}): {e}")
                    pass
                
                # 키워드로 판단된 경우에만 사각형을 그립니다.
                if is_keyword:
                    rect = fitz.Rect(x0, y0, x1, y1)
                    page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))

            print(f"  - {page_num + 1} 페이지 처리 완료.")

        # 모든 페이지 처리가 끝난 후, 문서를 저장합니다.
        doc.save(output_file_path, garbage=4, deflate=True, clean=True)
        print(f"\n✨ 완료: 마스킹된 PDF가 '{output_file_path}'로 저장되었습니다.")

    except Exception as e:
        print(f"오류가 발생했습니다: {e}")
    finally:
        if 'doc' in locals() and doc:
            doc.close()