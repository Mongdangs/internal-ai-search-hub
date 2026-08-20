# 사내 산출물·제안서 근거형 검색 PoC

이 PoC는 로컬 또는 사내 폴더에 저장된 PDF, DOCX, PPTX 산출물과 제안서를 색인하고, 사용자가 입력한 주제나 신규 RFP와 관련된 프로젝트, 문서, 페이지, 문단, 원문 경로를 찾아주는 검색 시스템입니다.

초기 목적은 완성형 챗봇이 아니라 기존 폴더 체계의 문서를 페이지 또는 슬라이드 단위로 색인하고 검색 가능성을 검증하는 것입니다.

## 주요 기능

1. 로컬 폴더 내 PDF/DOCX/PPTX 문서 색인
2. 프로젝트·문서 메타데이터 자동 추출
3. PDF 페이지, PPTX 슬라이드, DOCX 문단 묶음 단위 본문 추출
4. SQLite FTS5 기반 키워드 검색
5. 로컬 해시 임베딩 기반 벡터 검색
6. 키워드 점수와 벡터 점수를 결합한 하이브리드 검색
7. 신규 RFP 파일 기반 유사 프로젝트·문서 추천
8. 검색 로그 저장

## 설치

```powershell
cd "C:\Users\JKLEE\Documents\사내 LLM 검색 구축\llm_reference_search_poc"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`sentence-transformers` 모델을 바로 쓰기 어렵거나 외부 다운로드가 제한된 환경에서는 기본 설정인 `embedding.provider: hashing`을 그대로 사용하세요. 이 방식은 외부 API를 호출하지 않습니다.

## 실행

```powershell
streamlit run app.py
```

Streamlit 화면에서 색인할 루트 폴더를 입력하고 `신규 색인`을 누른 뒤 검색을 실행합니다. 기본 대상 경로는 다음 두 곳입니다.

```text
H:\01.제안서
H:\02.사업수행
```

Windows에서 백그라운드로 실행하려면 다음 명령을 사용할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe scripts\start_app.py
```

## CLI 예시

```powershell
python -m src.cli index --root "H:\01.제안서" "H:\02.사업수행" --rebuild
python -m src.cli search "클린룸 복구와 관련된 산출물 찾아줘"
python -m src.cli rfp "D:\RFP\신규_RFP.pdf"
```

## 보안 전제

- 민감자료, 개인정보, 견적, 원가, 계약자료는 초기 색인 대상에서 제외합니다.
- 외부 LLM API 사용 시 고객자료 반출 여부를 별도로 검토해야 합니다.
- 기본 구현은 로컬 폴더와 로컬 SQLite DB만 사용합니다.

## 산출물 구조

```text
llm_reference_search_poc/
  app.py
  requirements.txt
  README.md
  config.yaml
  src/
  data/
  tests/
```
