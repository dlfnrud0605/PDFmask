import os
import fitz  # PyMuPDF
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextBox, LTTextLine
import random



# --- 설정 ---
pdf_file_path = "test.pdf"
output_file_path = "output_with_rectangle1.pdf"
# --- 설정 끝 ---

def count_special_chars_korean(input_string):
    special_char_count = 0
    for char in input_string:

        if char.isalnum() or char.isspace():
            continue # 특수 문자가 아니므로 다음 문자로 넘어감

        # 한글 범위 체크
        # 기존 함수의 한글 체크 로직 유지 (특수 문자가 아닌 것으로 간주)
        if '\uAC00' <= char <= '\uD7AF':  # 한글 완성형
            continue
        if '\u1100' <= char <= '\u11FF':  # 한글 자모
            continue
        if '\u3130' <= char <= '\u318F':  # 한글 호환 자모
            continue

        # 위 조건들을 모두 만족하지 않으면 특수 문자로 간주하고 카운트 증가
        special_char_count += 1

    return special_char_count



if not os.path.exists(pdf_file_path):
    print(f"오류: '{pdf_file_path}' 파일을 찾을 수 없습니다.")
else:
    print(f"PDF 문서: {os.path.basename(pdf_file_path)}")
    new_doc = fitz.open()

    with fitz.open(pdf_file_path) as doc:
        total_pages = len(doc)

        for page_index, layout in enumerate(reversed(list(extract_pages(pdf_file_path)))):
            page_index = total_pages - page_index-1
            if page_index == 17:
              pass
            
            new_doc.insert_pdf(doc, from_page=page_index, to_page=page_index, start_at=0)

            page = doc.load_page(page_index)
            page_dict = page.get_text("rawdict")

            # 모든 글자(character) 정보를 수집
            char_list = [
                (char.get('c'), char.get('bbox'))
                for block in page_dict.get('blocks', []) if block.get('type') == 0
                for line in block.get('lines', [])
                for span in line.get('spans', [])
                for char in span.get('chars', [])
                if char.get('c', '').strip() and char.get('bbox')
            ]

            # 텍스트 라인 추출 및 정렬 (위에서 아래 순으로)
            text_lines = [
                line for box in layout if isinstance(box, LTTextBox)
                for line in box if isinstance(line, LTTextLine)
                if line.get_text().strip().replace(" ", "") 
            ]
            text_lines.sort(key=lambda lt: (-lt.bbox[1], lt.bbox[0]))

            char_idx = 0  # 현재 문자 인덱스
            lines_bbox=[]
            while text_lines:
                matches = []
                for i, line in enumerate(text_lines):
                    line_text = line.get_text().strip().replace(" ", "")

                    temp_idx = char_idx
                    combined_text = char_list[temp_idx][0]

                    while line_text.startswith(combined_text):
                        if len(combined_text) >= len(line_text):
                            matches.append((temp_idx + 1, i))
                            break
                        temp_idx += 1
                        if temp_idx >= len(char_list):
                            break
                        combined_text += char_list[temp_idx][0]

                # 매칭 실패 시 중단
                if not matches:
                    Exception("에러")

                # 가장 긴 매칭 라인 사용
                _, matched_idx = max(matches, key=lambda x: (x[0], -x[1]))
                matched_line = text_lines.pop(matched_idx)
                words = matched_line.get_text().strip().split()

                temp_idx = char_idx
                words_bbox = []
                for word in words:
                    word = word.strip()
                    if not word:
                        continue
                    
                    if random.random() > 0.4 or len(word) < 3:
                      temp_idx += len(word)  # 글자 수만큼 인덱스 건너뜀
                      continue

                    if len(word) < 4 and count_special_chars_korean(word) > 1:
                        temp_idx += len(word)
                        continue

                    start_char = char_list[temp_idx]
                    x0, y0, y1 = start_char[1][0], start_char[1][1], start_char[1][3]
                    word_accum = ""

                    while word_accum != word and temp_idx < len(char_list):
                        c, bbox = char_list[temp_idx]
                        word_accum += c
                        y0 = min(y0, bbox[1])
                        y1 = max(y1, bbox[3])
                        temp_idx += 1

                    x1 = char_list[temp_idx - 1][1][2]
                    words_bbox.append((x0, y0, x1, y1))
                if words_bbox:
                  lines_bbox.append(words_bbox)
                char_idx = temp_idx

            lines_bbox.sort(key=lambda x: (-x[0][1], x[0][0]))
            for words_bbox in lines_bbox:
              for x0, y0, x1, y1 in sorted(words_bbox,reverse=True):
                      rect = fitz.Rect(x0, y0, x1, y1)
                      page.draw_rect(rect, color=(0, 0, 0), fill=(0.7, 0.1, 0.1))
                      new_doc.insert_pdf(doc, from_page=page_index, to_page=page_index, start_at=0)
                      page.draw_rect(rect, color=(0, 0, 0), fill=(0.7, 0.7, 0.7))

        new_doc.subset_fonts()  # 폰트 최적화 (안전)
        new_doc.save(output_file_path,
            garbage=4,              # 적당한 가비지 수집
            deflate=True,           # 기본 압축
            deflate_images=True,    # 이미지 압축
            clean=True              # PDF 정리
        )
        new_doc.close()
        print(f"완료: 사각형이 추가된 PDF가 '{output_file_path}'로 저장되었습니다.")
