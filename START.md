# KiriFin Crawler 실행 가이드

## 1. Python 가상환경 생성
```bash
cd crawler
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # Mac/Linux
```

## 2. 패키지 설치
```bash
pip install -r requirements.txt
```

## 3. 서버 실행
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 4. 확인
- Health check: http://localhost:8000/health
- API 문서: http://localhost:8000/docs

## 참고
- Chrome 브라우저가 설치되어 있어야 합니다
- ChromeDriver는 webdriver-manager가 자동 설치합니다
- 크롤링 시 Chrome 창이 열립니다 (헤드리스 끔 상태)
- 헤드리스 모드: scraper.py의 `--headless=new` 주석 해제
