# 📚 Anki-tecture (Anki 족보 자동 생성기)

**Anki-tecture**는 방대한 학습 자료(PDF)를 분석하여 Anki 카드를 자동으로 생성하고, 내 Anki 데스크톱 앱에 직접 추가해 주는 자동화 파이프라인 툴입니다. 

Google Gemini API(Flash/Pro)의 텍스트 구조화 및 시각(Vision) 분석 능력을 활용하여 문서 내의 문제, 해설은 물론 **이미지 좌표를 추적해 실제 사진까지 깔끔하게 잘라내어** 카드에 연동합니다. 일반적인 텍스트 위주의 요약본부터, 서술형 문항이 필요한 피첵(CPX/OSCE) 체크리스트나 이미지 자료가 포함된 기출문제 분석까지 완벽하게 지원합니다.

---

## 🛠 사전 준비 사항 (Prerequisites)

이 프로그램을 실행하려면 컴퓨터에 다음 세 가지가 미리 준비되어 있어야 합니다.

1. **Python 3.8 이상** 설치
2. **Anki 데스크톱 프로그램** 설치 및 실행 중일 것
3. **AnkiConnect 애드온** 설치
   - Anki 실행 -> `도구(Tools)` -> `애드온(Add-ons)` -> `애드온 얻기(Get Add-ons)`
   - 코드 **`2055492159`** 입력 후 설치 및 Anki 재시작
4. **Google Gemini API Key** 발급 (Google AI Studio에서 무료 발급 가능)

---

## 🚀 설치 및 세팅 방법 (Installation)

다른 컴퓨터에서 이 프로그램을 처음 세팅할 때 아래 순서대로 진행해 주세요.

### 1. 프로젝트 다운로드 (Clone)
터미널을 열고 깃허브 저장소를 내 컴퓨터로 가져옵니다.
```bash
git clone https://github.com/dyk226/anki-tecture.git
cd anki-tecture
```

### 2. 필요한 파이썬 라이브러리 설치
프로젝트 구동에 필요한 패키지들(Streamlit, PyMuPDF, google-genai 등)을 한 번에 설치합니다.

```bash
pip install -r requirements.txt
```

### 3. API 키 설정 (환경변수)
이 프로젝트는 보안을 위해 API 키를 깃허브에 올리지 않습니다. 코드를 다운받은 컴퓨터에 직접 키를 입력해 주어야 합니다.

프로젝트 폴더 최상단에 .env 라는 이름의 새 파일을 만듭니다.

파일 안에 아래와 같이 본인의 Gemini API 키를 작성하고 저장합니다.


```Plaintext
GEMINI_API_KEY="여기에_발급받은_진짜_API_KEY_입력"
```

## 💻 사용 방법 (Usage)
1. 먼저 컴퓨터에서 Anki 프로그램을 실행해 둡니다. 
(Anki 프로그램이 켜져 있어야만 파이썬과 통신할 수 있습니다.)

2. 터미널에서 아래 명령어를 입력하여 웹 앱을 실행합니다.
```Bash
streamlit run app.py
```

3. 자동으로 열리는 인터넷 브라우저 창에서 다음을 수행합니다:
- 분석할 족보 또는 요약본 PDF 파일 업로드 (여러 개 동시 가능)
- 자료 성격 선택 (형태에 따라 최적화된 프롬프트가 적용됩니다)
- 카드를 추가할 대상 Anki 덱 선택 또는 새 덱 이름 입력

4. 실행 버튼 클릭!


## ⚙️ 주요 기능 작동 원리
- 프론트엔드 (app.py): Streamlit을 이용해 파일을 메모리(Bytes)에 올리고 옵션을 선택하는 직관적인 UI 제공.
- 백엔드 처리 (pdf_processor.py): 메모리의 PDF 바이트를 하드디스크 저장 없이 곧바로 Gemini API로 전송.
- 이미지 자동 크롭: Gemini가 PDF 내 이미지의 Bounding Box 좌표(0~1000)를 반환하면, PyMuPDF(fitz)가 해당 좌표를 실제 크기로 환산해 고화질로 잘라냄.
- 다이렉트 Anki 추가: AnkiConnect의 storeMediaFile과 addNote 액션을 이용해 생성된 텍스트와 이미지 미디어를 로컬 Anki로 즉각 쏴줌.