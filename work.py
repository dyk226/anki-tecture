from google import genai
from google.genai import types
import pathlib
import fitz
import anthropic

import json
import requests
import os
import base64
import time
from tenacity import Retrying, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type
from google.genai.errors import ServerError
from dotenv import load_dotenv
load_dotenv()

def upload_media_to_anki(filepath, filename):
    """
    잘라낸 이미지 파일을 읽어 Anki의 collection.media 폴더로 업로드합니다.
    """
    url = 'http://localhost:8765'
    
    try:
        # 1. 하드디스크에 저장된 이미지를 읽어서 텍스트(Base64) 형태로 변환합니다.
        with open(filepath, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
        # 2. AnkiConnect API 양식에 맞춘 데이터 구성
        payload = {
            "action": "storeMediaFile",
            "version": 6,
            "params": {
                "filename": filename,  # Anki에 저장될 이름 (예: question_1_img.png)
                "data": encoded_string # 변환된 이미지 데이터
            }
        }

        # 3. Anki로 전송!
        response = requests.post(url, json=payload).json()
        
        if response.get('error') is None:
            print(f"📸 미디어 업로드 성공: {filename}")
            return True
        else:
            print(f"❌ 미디어 업로드 실패: {response.get('error')}")
            return False
            
    except Exception as e:
        print(f"⚠️ 파일 읽기 또는 전송 중 오류 발생: {e}")
        return False

def crop_image_by_coordinates(doc, page_num, relative_coords, filename):
    """
    Gemini가 준 0~1000 상대 좌표를 이용해 PDF 페이지의 특정 영역을 자릅니다.
    [ymin, xmin, ymax, xmax] -> fitz.Rect(x0, y0, x1, y1) 변환
    """
    # 0. PDF의 실제 페이지 객체를 가져옵니다.
    try:
        page = doc[page_num - 1] # 1페이지 -> index 0
    except IndexError:
        print(f"오류: PDF에 {page_num}페이지가 없습니다.")
        return None

    # 1. PDF 페이지의 실제 크기 (Point 단위) 가져오기 (예: A4 = 595, 842)
    # fitz에서는 p.x1, p.y1이 너비와 높이를 의미합니다.
    page_rect = page.rect
    page_width = page_rect.x1
    page_height = page_rect.y1

    # 2. Gemini의 0~1000 상대 좌표 -> 실제 PDF 좌표(Point)로 환산
    ymin, xmin, ymax, xmax = relative_coords
    
    # 공식: (상대좌표 / 1000) * 실제크기
    pdf_xmin = (xmin / 1000) * page_width
    pdf_ymin = (ymin / 1000) * page_height
    pdf_xmax = (xmax / 1000) * page_width
    pdf_ymax = (ymax / 1000) * page_height

    # 3. PyMuPDF에서 사용할 크롭 영역(Rectangle) 생성 (x0, y0, x1, y1)
    crop_rect = fitz.Rect(pdf_xmin, pdf_ymin, pdf_xmax, pdf_ymax)
    
    # 🚨 중요: 크롭 영역이 페이지를 벗어나지 않게 보정 (가끔 Gemini가 1000 넘는 값을 줄 수 있음)
    crop_rect = crop_rect & page_rect 

    # 4. 해당 영역만 스크린샷 찍듯이 이미지를 가져옵니다. (Pixmap)
    # 꿀팁: 높은 화질을 위해 매트릭스(배율)를 추가하는 게 좋습니다. (예: 3배율)
    mat = fitz.Matrix(3, 3) # 해상도 3배 증가
    pix = page.get_pixmap(matrix=mat, clip=crop_rect)

    # 5. 폴더에 이미지 파일로 저장
    output_folder = "extracted_images"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        
    filepath = os.path.join(output_folder, filename)
    pix.save(filepath) # PNG 형식으로 저장됨
    
    return filepath

def add_card_to_anki(deck_name, model_name, front_text, back_text, tags):
    """
    AnkiConnect를 통해 열려있는 Anki 프로그램으로 카드를 직접 추가합니다.
    """
    url = 'http://localhost:8765'
    
    # AnkiConnect API 양식에 맞춘 데이터 구성
    payload = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": {
                "deckName": deck_name,    # 내 Anki에 이미 만들어져 있는 덱 이름
                "modelName": model_name,  # 사용할 카드 타입 (예: "기본", "Basic")
                "fields": {
                    "앞면": front_text,     # 필드 이름은 본인의 Anki 설정에 맞게 수정 필요
                    "뒷면": back_text
                },
                "tags": tags
            }
        }
    }

    try:
        response = requests.post(url, json=payload)
        result = response.json()
        
        if result.get('error') is None:
            print(f"성공: [{front_text[:10]}...] 카드가 추가되었습니다!")
        else:
            print(f"추가 실패: {result.get('error')}")
            
    except requests.exceptions.ConnectionError:
        print("오류: Anki 프로그램이 켜져 있는지, AnkiConnect 애드온이 설치되어 있는지 확인해 주세요.")

def get_valid_model_name():
    """Anki에 설치된 노트 타입 목록을 가져와서 가장 적절한 '기본' 타입을 찾습니다."""
    url = 'http://localhost:8765'
    payload = {
        "action": "modelNames",
        "version": 6
    }
    
    try:
        response = requests.post(url, json=payload)
        result = response.json()
        models = result.get('result', [])
        
        # 1순위: 한글판 Anki의 "기본"
        if "기본" in models:
            return "기본"
        # 2순위: 영문판 Anki의 "Basic"
        elif "Basic" in models:
            return "Basic"
        # 3순위: 둘 다 없으면 에러 방지를 위해 존재하는 첫 번째 노트 타입 반환
        elif len(models) > 0:
            return models[0]
        else:
            return None
            
    except requests.exceptions.ConnectionError:
        return None # Anki가 꺼져있을 때

# 메인 처리 함수 (app.py에서 이 함수를 부릅니다)
def process_pdf_to_anki(file_name, file_bytes, material_type, deck_name, use_auto_tag):
    """
    Streamlit에서 받은 PDF 바이트 데이터를 읽어 Gemini로 분석하고 Anki에 추가합니다.
    """
    # 환경변수에서 키를 읽어오거나, 안전하게 관리되는 키를 넣으세요!
    client = genai.Client() # api_key 파라미터를 빼면 자동으로 GEMINI_API_KEY 환경변수를 찾습니다.

    # 자료 성격에 따라 프롬프트 분기 처리
    if material_type == "[피첵]-강조표시_퀴즈":
        prompt = """ 
        파일의 수업 정리 부분에서 빨간색, 파란색 글씨로 된 부분은 하나도 빠짐없이, 그 부분을 잘 알고 있는지 확인하는 문제들을 만들어.
        그 외에 수업 정리 부분에서 알고 있어야 하는 내용을 포함해. 
        문제 개수는 최소 5개 ~ 최대 20개 만들어. 
        중요: 문제 유형은 의과대학 시험 문제/KMLE 문제와 매우 유사하게, 증례를 푸는 형태로 만들어. (매우 불가피할 때만 지식 체크하는 형태로 만들어.)
        문제 난이도는 의과대학 본과 2학년 학생이 풀기 살짝 어려운 난이도 혹은 그보다 조금 쉽게 만들어.
        안키에 넣을 거니까 주관식 단답형, 서술형 형태로 만들어. 안키 앞면은 "문제"에, 안키 뒷면은 "해설"에 넣어.
        안키 뒷면 만들 때 최대한 간결하게 핵심어 위주로 작성해. (불가피할 때는 ~이다. ~하다로 끝나는 문장 형태로 써도 됨)
        """
    elif material_type == "[피첵]-JBL" :
        prompt = """
        파일의 족보 풀이 뒷부분에 있는 문제와 풀이를 있는 그대로 가져와. 중요: 절대 문제를 누락하지 말 것. 
        문제와 풀이에서 띄어쓰기 이상한 부분이나, 오타가 있으면 고쳐.
        문제에서 '17학번 과정말 1교시 62번', '[19학번 2차 주시 20번]'처럼 문제의 출처 부분이 있다면 지워. 
        문제 시작할 때 '1. 다음은..' 처럼 문제 번호가 나온다면 문제 번호 삭제해.
        문제 발문 도중에 '현미경 관찰사진(사진9)이다'와 같이 사진 번호가 기재되어 있는 경우, 아예 지우고 '현미경 관찰사진이다' 이렇게만 남겨.
        문제에 사진이나 표나 그래프가 포함된 경우, 그 시각 자료를 감싸는 가장 작은 사각형 영역의 상대 좌표[ymin, xmin, ymax, xmax]를 0~1000 사이의 정수로 정확히 측정해서 상대_좌표 필드에 넣어. 중요: 표 부분도 무조건 사진에 포함시킬 것. 표와 사진이 같이 있다면 같이 포함되도록 점을 지정할 것.
        문제에 선지가 있으면 <br>① FSH<br>② PTH<br>③ activin<br>④ Cortisol<br>⑤ Thyroid hormone 이런 식으로, 선지 번호는 ①②③④⑤ 이런 원형 아이콘을 쓰고, 선지 사이는 <br>로 줄바꿈해.
        해설은 '[정답] ④ <br>[해설] 호르몬 중..' 처럼 정답을 첫째줄, 해설을 둘째 줄 이후로 쓰고, 관련 단원, 반복 내용은 지우고 진짜 설명하는 내용만 가져와. 해설에 줄바꿈 있다면 <br>로 줄바꿈해.
        """
    elif material_type == "[수업자료]땡시":
        prompt = """
        파일에서 중요한 내용을 찾아서 중요한 내용이 모두 포함되게 하되, 의과대학 본과 2학년 학생이 풀만한, 조직학 땡시 준비용 anki를 만들어.
        anki 앞면에는 조직학 사진을 넣고, 뒷면에는 무엇을 가리키는지 답을 써. 뒷면 만들 때 최대한 간결하게 핵심어 위주로 작성해. (불가피할 때는 ~이다. ~하다로 끝나는 문장 형태로 써도 됨)
        """
        
    elif material_type == "[수업자료]퀴즈":
        prompt = """
        파일에서 중요한 내용을 찾아서 중요한 내용이 모두 포함되게 하되, 의과대학 본과 2학년 학생이 풀만한, 예복습용 퀴즈 anki를 만들어.
        안키 앞면은 주관식 단답형, 서술형 형태로 문제 만들고, 뒷면에는 답을 써. 
        안키 뒷면 만들 때 최대한 간결하게 핵심어 위주로 작성해. (불가피할 때는 ~이다. ~하다로 끝나는 문장 형태로 써도 됨)
        중요: 문제 유형(안키 앞면)은 의과대학 시험 문제/KMLE 문제와 매우 유사하게, 증례를 푸는 형태로 만들어. (불가피할 때만 지식 체크하는 형태로 만들어.)
        """

    response = None

    for attempt in Retrying(
        stop=stop_after_attempt(6),
        wait=wait_exponential_jitter(initial=1, max=20),
        retry=retry_if_exception_type(ServerError),
        reraise=True,
    ):
        with attempt:
            print("👉 Gemini 호출 시도")
            # Gemini API 호출 (핵심: filepath 대신 file_bytes를 바로 꽂아 넣습니다)
            response = client.models.generate_content(
                model="gemini-3-flash-preview", # 복잡한 족보 논리 처리는 Pro 모델을 추천합니다 # 3.1-pro-preview or 3-flash-preview or 2.5-flash
                contents=[
                    types.Part.from_bytes(
                        data=file_bytes, 
                        mime_type='application/pdf'
                    ),
                    prompt
                ],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "문제": {"type": "STRING"},
                                "해설": {"type": "STRING"},
                                "이미지_존재_여부": {"type": "BOOLEAN"}, # Gemini가 판단
                                "이미지_메타데이터": { # 정보를 묶어주는 게 좋습니다.
                                    "type": "OBJECT",
                                    "properties": {
                                        "원본_페이지": {"type": "INTEGER"},
                                        # 중요: [ymin, xmin, ymax, xmax] 순서의 0~1000 상대 좌표
                                        "상대_좌표": {
                                            "type": "ARRAY", 
                                            "items": {"type": "INTEGER"},
                                            "minItems": 4, # 반드시 4개 숫자여야 함
                                            "maxItems": 4
                                    }
                                    }
                                }
                            },
                            "required": ["문제", "해설","이미지_존재_여부"]
                        }
                    }
                }
            )

    quiz_list = json.loads(response.text)
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    
    if use_auto_tag:
    #덱명과 파일명으로 태그 만들기 
        try:
            dbefore, dsep, dafter = deck_name.rpartition('.') # 26-1.1.신장 에서 신장만 자르기
            fbefore, fsep, fafter = file_name.partition('_') # 1. 신장의구조와_00교수님_피첵_..에서 1. 신장의구조와 자르기

            ff = fbefore.replace('. ', '.') # 1. 신장의구조 >> 1.신장의구조
            ffbefore, ffsep, ffafter = ff.partition('.') # 1. 신장의구조와에서 1.신장의구조와 로 바꾸기

            try:
                if int(ffbefore)<10: ffbefore = "0"+ffbefore # 1.신장의구조와 >> 01신장의구조와
            except:
                pass
            tag = dafter.replace(' ', '_') + '::' + ffbefore.replace(' ', '_') + '.' + ffafter.replace(' ','_')

        except:
            pass
    
    
    # 카드 넣기 전에, 가장 적절한 노트 타입 이름 찾아오기
    target_model = get_valid_model_name()
    
    if not target_model:
        return 0, "Anki가 켜져 있지 않거나 노트 타입을 찾을 수 없습니다."


    added_count = 0 
    for item in quiz_list:
        fronttext = item['문제']
        # --- [이미지 처리 로직 추가] ---
        if item['이미지_존재_여부'] and item['이미지_메타데이터']:
            metadata = item['이미지_메타데이터']
            coords = metadata.get('상대_좌표') # [ymin, xmin, ymax, xmax]
            orig_page = metadata.get('원본_페이지')

            if coords and orig_page:
                img_filename = f"{int(time.time())}_q{added_count + 1}.png"
                
                print(f"📸 [{orig_page}페이지] {coords} 좌표를 크롭하여 {img_filename} 저장 중...")
                
                # C. 좌표 기반 크롭 함수 호출!
                cropped_filepath = crop_image_by_coordinates(doc, orig_page, coords, img_filename)

                if cropped_filepath:
                    # D. AnkiConnect로 이미지 업로드 (다음 단계 코드)
                    upload_media_to_anki(cropped_filepath, img_filename)

                    # E. 카드 앞면에 HTML img 태그 스윽 끼워 넣기
                    before, sep, after = fronttext.partition('①')

                    if sep:
                        fronttext = before + f'<img src="{img_filename}"><br>' + sep + after
                    else: fronttext += f'<br><img src="{img_filename}">'
        
        
        add_card_to_anki(
            deck_name=deck_name, 
            model_name="기본", 
            front_text=fronttext, 
            back_text=item['해설'], 
            tags=[tag, material_type]
        )
        added_count += 1
    
    doc.close()   
    return added_count


def process_pdf_to_anki_claude(file_name, file_bytes, material_type, deck_name, use_auto_tag):
    """
    Claude API를 사용해 PDF를 분석하고 Anki에 카드를 추가합니다.
    """
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 자동 사용

    # 자료 성격에 따라 프롬프트 분기 처리
    if material_type == "[피첵]-강조표시_퀴즈":
        prompt = """ 
        당신은 의과대학 시험 출제 전문가입니다.

        아래 규칙에 따라 Anki 카드를 만들어주세요.

        [추출 범위]
        - 수업 정리 부분의 빨간색·파란색 강조 글씨를 우선 대상으로 삼고,
        그 외 수업 정리 내 핵심 개념을 추가로 포함해.
        - 총 카드 수: 10~25개 (강조 표시가 적으면 최소 10개, 많으면 25개까지만)

        [문제 형식 - 중요]
        - 반드시 증례 기반 문제로 만들어. 아래 형태를 따를 것:
        예시) "35세 남성이 복통과 황달을 주소로 내원했다. 검사상 혈청 빌리루빈이 상승해 있을 때, 이 증상의 원인이 되는 호르몬은?"
        - 단순 지식 확인형(예: "~의 기능은?")은 증례로 표현이 불가능한 경우에만 허용.
        - 단답형 또는 간단한 서술형으로 작성.

        [해설 형식]
        - 핵심 키워드 위주로 간결하게.
        - 문장이 필요한 경우 "~이다." "~한다." 로 끝낼 것.
        """
    elif material_type == "[피첵]-JBL" :
        prompt = """
        파일의 족보 풀이 뒷부분에 있는 문제와 풀이를 있는 그대로 가져와. 중요: 절대 문제를 누락하지 말 것. 
        문제와 풀이에서 띄어쓰기 이상한 부분이나, 오타가 있으면 고쳐.
        문제에서 '17학번 과정말 1교시 62번', '[19학번 2차 주시 20번]'처럼 문제의 출처 부분이 있다면 지워. 
        문제 시작할 때 '1. 다음은..' 처럼 문제 번호가 나온다면 문제 번호 삭제해.
        문제 발문 도중에 '현미경 관찰사진(사진9)이다'와 같이 사진 번호가 기재되어 있는 경우, 아예 지우고 '현미경 관찰사진이다' 이렇게만 남겨.
        문제에 사진이나 표나 그래프가 포함된 경우, 그 시각 자료를 감싸는 가장 작은 사각형 영역의 상대 좌표[ymin, xmin, ymax, xmax]를 0~1000 사이의 정수로 정확히 측정해서 상대_좌표 필드에 넣어. 중요: 표 부분도 무조건 사진에 포함시킬 것. 표와 사진이 같이 있다면 같이 포함되도록 점을 지정할 것.
        문제에 선지가 있으면 <br>① FSH<br>② PTH<br>③ activin<br>④ Cortisol<br>⑤ Thyroid hormone 이런 식으로, 선지 번호는 ①②③④⑤ 이런 원형 아이콘을 쓰고, 선지 사이는 <br>로 줄바꿈해.
        해설은 '[정답] ④ <br>[해설] 호르몬 중..' 처럼 정답을 첫째줄, 해설을 둘째 줄 이후로 쓰고, 관련 단원, 반복 내용은 지우고 진짜 설명하는 내용만 가져와. 해설에 줄바꿈 있다면 <br>로 줄바꿈해.
        """
    elif material_type == "[수업자료]땡시":
        prompt = """
        파일에서 중요한 내용을 찾아서 중요한 내용이 모두 포함되게 하되, 의과대학 본과 2학년 학생이 풀만한, 조직학 땡시 준비용 anki를 만들어.
        anki 앞면에는 조직학 사진을 넣고, 뒷면에는 무엇을 가리키는지 답을 써. 뒷면 만들 때 최대한 간결하게 핵심어 위주로 작성해. (불가피할 때는 ~이다. ~하다로 끝나는 문장 형태로 써도 됨)
        """
        
    elif material_type == "[수업자료]퀴즈":
        prompt = """
        당신은 의과대학 시험 출제 전문가입니다.

        이 파일은 의과대학 수업 자료입니다. 예복습용 Anki 퀴즈를 만들어주세요.

        [출제 범위 및 개수]
        - 파일 전체에서 핵심 개념을 고루 커버하되, 카드 수는 10~25개로 제한.
        - 한 주제에 카드가 몰리지 않도록 분산.

        [문제 형식 - 중요]
        - 증례 기반 문제를 우선으로 만들 것. 아래 형태 참고:
        예시) "28세 여성이 갑상선 기능저하 증상으로 내원. TSH 상승, T4 저하 시 일차적으로 문제가 되는 기관은?"
        - 단순 암기 확인형(예: "~의 기전은?")은 증례로 표현이 불가능한 경우에만 사용.
        - 단답형 또는 간결한 서술형.

        [해설 형식]
        - 핵심 키워드 위주로 간결하게.
        - 문장이 필요하면 "~이다." "~한다." 로 끝낼 것.
        """

    # JSON 출력 형식 지시를 프롬프트에 추가
    json_instruction = """
    
    반드시 아래 형식의 JSON 배열만 반환해. 마크다운 코드블록(```)이나 설명 텍스트 없이 순수 JSON만.
    형식:
    [
      {
        "문제": "문제 텍스트",
        "해설": "해설 텍스트",
        "이미지_존재_여부": false,
        "이미지_메타데이터": {
          "원본_페이지": 1,
          "상대_좌표": [ymin, xmin, ymax, xmax]
        }
      }
    ]
    이미지가 없는 경우 이미지_존재_여부는 false, 이미지_메타데이터는 null로 설정해.
    """

    # PDF를 base64로 변환
    pdf_base64 = base64.b64encode(file_bytes).decode('utf-8')

    response = client.messages.create(
        model="claude-sonnet-4-5",  # 또는 claude-sonnet-4-5
        max_tokens=8192,
        system="당신은 의학 교육 전문가입니다. 반드시 순수 JSON만 반환하고, 절대 마크다운이나 설명 텍스트를 포함하지 마세요.",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt + json_instruction
                    }
                ]
            }
        ]
    )

    raw_text = response.content[0].text.strip()
    
    # 혹시 ```json ... ``` 감싸진 경우 방어 처리
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    
    quiz_list = json.loads(raw_text)
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    # 이하 태그 생성, 카드 추가 로직은 기존과 완전히 동일
    tag = ""
    if use_auto_tag:
        try:
            dbefore, dsep, dafter = deck_name.rpartition('.')
            fbefore, fsep, fafter = file_name.partition('_')
            ff = fbefore.replace('. ', '.')
            ffbefore, ffsep, ffafter = ff.partition('.')
            try:
                if int(ffbefore) < 10: ffbefore = "0" + ffbefore
            except:
                pass
            tag = dafter.replace(' ', '_') + '::' + ffbefore.replace(' ', '_') + '.' + ffafter.replace(' ', '_')
        except:
            pass

    target_model = get_valid_model_name()
    if not target_model:
        return 0

    added_count = 0
    for item in quiz_list:
        fronttext = item['문제']
        if item.get('이미지_존재_여부') and item.get('이미지_메타데이터'):
            metadata = item['이미지_메타데이터']
            coords = metadata.get('상대_좌표')
            orig_page = metadata.get('원본_페이지')
            if coords and orig_page:
                img_filename = f"{int(time.time())}_q{added_count + 1}.png"
                cropped_filepath = crop_image_by_coordinates(doc, orig_page, coords, img_filename)
                if cropped_filepath:
                    upload_media_to_anki(cropped_filepath, img_filename)
                    before, sep, after = fronttext.partition('①')
                    if sep:
                        fronttext = before + f'<img src="{img_filename}"><br>' + sep + after
                    else:
                        fronttext += f'<br><img src="{img_filename}">'

        add_card_to_anki(
            deck_name=deck_name,
            model_name=target_model,
            front_text=fronttext,
            back_text=item['해설'],
            tags=[tag, material_type] if tag else [material_type]
        )
        added_count += 1

    doc.close()
    return added_count