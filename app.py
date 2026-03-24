import streamlit as st
import requests
import work
import time

ANKI_URL = 'http://localhost:8765'

def get_anki_decks():
    """AnkiConnect를 통해 현재 존재하는 덱 목록을 가져옵니다."""
    payload = {
        "action": "deckNames",
        "version": 6
    }
    try:
        response = requests.post(ANKI_URL, json=payload).json()
        if not response.get('error'):
            return response.get('result', []) # 덱 이름 리스트 반환 (예: ["Default", "소화기내과", ...])
    except requests.exceptions.ConnectionError:
        return [] # Anki가 꺼져있으면 빈 리스트 반환
    return []

def create_anki_deck(deck_name):
    """새로운 덱을 생성합니다."""
    payload = {
        "action": "createDeck",
        "version": 6,
        "params": {
            "deck": deck_name
        }
    }
    try:
        requests.post(ANKI_URL, json=payload)
    except Exception as e:
        print(f"덱 생성 실패: {e}")
        

# 제목
st.title("anki-tecture")

uploaded_files = st.file_uploader("PDF 파일을 여기에 끌어다 놓으세요.", accept_multiple_files=True, type="pdf")

options = ["[피첵]-JBL", "[피첵]-강조표시_퀴즈", "[수업자료]퀴즈", "[수업자료]땡시"]
descriptions = {
    "[피첵]-JBL": "족보 문제 풀이와 해설을 그대로 카드로 만들어 덱에 추가합니다.",
    "[피첵]-강조표시_퀴즈": "피첵 내 강조표시(빨간 글씨, 파란 글씨)를 5~20개의 주관식 퀴즈로 만들어 덱에 추가합니다.",
    "[수업자료]퀴즈": "수업자료에서 제미나이가 중요하다고 판단하는 부분을 주관식 퀴즈로 만들어 덱에 추가합니다.",
    "[수업자료]땡시": "조직학 땡시를 대비하는 주관식 퀴즈를 만들어 덱에 추가합니다."
}
material_type = st.pills(
    "학습 타입 선택", 
    options, 
    selection_mode="single", # 하나만 선택 가능
    default="[피첵]-JBL"      # 기본 선택값
)
if material_type:
    st.caption(descriptions[material_type])

# 3. Anki 덱 이름 입력
existing_decks = get_anki_decks()
if not existing_decks:
    # Anki가 꺼져있거나 연동이 안 된 경우 경고를 띄우고 직접 입력받게 함
    st.warning("⚠️ Anki 데스크톱 앱이 켜져 있는지, AnkiConnect가 설치되어 있는지 확인해 주세요.")
    deck_name = st.text_input("🎯 추가할 Anki 덱 이름을 직접 입력하세요")
else:
    # 기존 덱 목록 맨 앞에 '(새 덱 만들기)' 옵션 추가
    options = ["(새 덱 만들기)"] + existing_decks
    selected_option = st.selectbox("🎯 카드를 추가할 Anki 덱을 선택하세요", options)
    
    # 사용자가 '새 덱 만들기'를 선택하면 이름을 입력할 수 있는 텍스트 박스를 짠! 하고 보여줌
    if selected_option == "(새 덱 만들기)":
        deck_name = st.text_input("✨ 새로 만들 덱 이름을 입력하세요", placeholder="예: 26-1.1.신장")
    else:
        deck_name = selected_option # 기존 덱을 선택한 경우 그 이름을 그대로 사용

#st.divider()
use_auto_tag = st.checkbox("🏷️ 자동 태그 생성", value=True)
if use_auto_tag:
    st.write(
        f'<p style="color: gray; font-size: 0.8rem; margin-left: 30px;">'
        f'활성화 시 "학습 타입"과 "덱명에서 마지막 .(온점) 뒷부분"::"파일명에서 첫 _(밑줄) 앞부분"이 태그로 달립니다.<br>'
        f'e.g. 덱명이 "26-1.1.신장", 파일명이 "1.신장과 요로계의 해부_김영석 교수님_피첵"인 경우, <br> ➩ 태그는 "신장::1.신장과_요로계의_해부"'
        f'</p>', 
        unsafe_allow_html=True
    )

# 4. 실행 버튼 및 로직 연결
if st.button("🚀 Anki 카드 추출 및 추가 시작", type="primary"):
    start_time = time.time()
    # 방어 로직: 파일이 업로드되지 않았을 때의 경고창
    if not uploaded_files:
        st.warning("먼저 PDF 파일을 업로드해 주세요!")
    elif not deck_name:
        st.warning("Anki 덱 이름을 입력해 주세요!")
    else:
        st.info(f"총 {len(uploaded_files)}개의 파일을 '{material_type}' 방식으로 분석하여 [{deck_name}] 덱에 추가합니다...")
        for file in uploaded_files:
            # 진행 상황을 보여주는 스피너 (로딩 애니메이션)
            with st.spinner(f"'{file.name}' 처리 중..."):

                # file.read()를 통해 PDF 파일을 바이트 데이터로 변환해서 넘겨줍니다.
                file_name = file.name
                file_bytes = file.read()
                
                # pdf_processor의 함수 호출
                count = work.process_pdf_to_anki(file_name, file_bytes, material_type, deck_name, use_auto_tag)
                
                end_time = time.time()
                extime = end_time-start_time
                
                time_str = f"{int(extime%60)}초" if extime < 60 else f"{int(extime//60)}분 {int(extime%60)}초"
                st.success(f"✅ {file.name}: {count}개의 카드가 Anki에 추가되었습니다! \n ⏱️ 소요시간: {time_str}")