"""크롤링 서버 설정"""

# 법원경매 사이트
COURT_AUCTION_URL = "https://www.courtauction.go.kr"
COURT_AUCTION_SEARCH_URL = f"{COURT_AUCTION_URL}/RetrieveRealEstMulDetailList.laf"
COURT_AUCTION_DETAIL_URL = f"{COURT_AUCTION_URL}/RetrieveRealEstCarHvyMacDetailInfo.laf"

# Selenium 설정
SELENIUM_TIMEOUT = 30  # 페이지 로드 타임아웃 (초)
SELENIUM_IMPLICIT_WAIT = 10

# 크롤링 간격 (초) — 서버 부하 방지
CRAWL_DELAY = 1.0

# 법원 코드 매핑
COURT_CODES: dict[str, str] = {
    "서울중앙지방법원": "B000101",
    "서울남부지방법원": "B000104",
    "서울북부지방법원": "B000103",
    "서울동부지방법원": "B000102",
    "서울서부지방법원": "B000105",
    "의정부지방법원": "B000106",
    "인천지방법원": "B000107",
    "수원지방법원": "B000108",
    "대전지방법원": "B000401",
    "대구지방법원": "B000301",
    "부산지방법원": "B000201",
    "광주지방법원": "B000501",
    "울산지방법원": "B000202",
    "창원지방법원": "B000203",
    "청주지방법원": "B000402",
    "전주지방법원": "B000502",
    "춘천지방법원": "B000109",
    "제주지방법원": "B000503",
}

# 용도 코드 매핑
USAGE_CODES: dict[str, str] = {
    "건물": "0001",
    "토지": "0002",
    "차량": "0003",
    "기타": "0004",
}
