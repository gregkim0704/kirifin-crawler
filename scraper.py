"""
법원경매 사이트 크롤러 (Selenium 기반)
대한민국 법원 경매정보 사이트 (courtauction.go.kr) 크롤링
"""

import re
import time
import logging
from typing import Optional
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

from config import (
    COURT_AUCTION_URL,
    SELENIUM_TIMEOUT,
    SELENIUM_IMPLICIT_WAIT,
    CRAWL_DELAY,
    COURT_CODES,
    USAGE_CODES,
)
from models import AuctionItem, AuctionDetail, SearchRequest

logger = logging.getLogger(__name__)


def create_driver() -> webdriver.Chrome:
    """Chrome WebDriver 생성"""
    import os
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--headless=new")

    chrome_bin = os.environ.get("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
    if chromedriver_path:
        service = Service(chromedriver_path)
    else:
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.implicitly_wait(SELENIUM_IMPLICIT_WAIT)
    driver.set_page_load_timeout(SELENIUM_TIMEOUT)
    return driver


def parse_price(text: str) -> Optional[int]:
    """금액 문자열 → 원 단위 정수. 예: '171,000,000' → 171000000"""
    if not text:
        return None
    cleaned = re.sub(r"[^\d]", "", text)
    return int(cleaned) if cleaned else None


def parse_date(text: str) -> Optional[str]:
    """날짜 문자열 → YYYY-MM-DD 형식"""
    if not text:
        return None
    match = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if match:
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return None


def crawl_search(req: SearchRequest) -> list[dict]:
    """
    법원경매 사이트에서 매물 검색.
    Selenium으로 사이트 접속 → 검색 조건 입력 → 결과 파싱.
    """
    driver = create_driver()
    results: list[dict] = []

    try:
        logger.info(f"크롤링 시작: {req.court} / {req.usageType}")

        # 1) 사이트 접속
        driver.get(f"{COURT_AUCTION_URL}/RetrieveRealEstMulDetailList.laf")
        time.sleep(CRAWL_DELAY * 2)

        # 2) 법원 선택
        court_code = COURT_CODES.get(req.court)
        if court_code:
            try:
                court_select = Select(
                    WebDriverWait(driver, SELENIUM_TIMEOUT).until(
                        EC.presence_of_element_located((By.ID, "idJiwonNm"))
                    )
                )
                court_select.select_by_value(court_code)
                time.sleep(CRAWL_DELAY)
            except Exception as e:
                logger.warning(f"법원 선택 실패: {e}")

        # 3) 용도 선택
        if req.usageType and req.usageType != "전체":
            usage_code = USAGE_CODES.get(req.usageType)
            if usage_code:
                try:
                    usage_select = Select(driver.find_element(By.ID, "idMulKindCd"))
                    usage_select.select_by_value(usage_code)
                    time.sleep(CRAWL_DELAY)
                except Exception as e:
                    logger.warning(f"용도 선택 실패: {e}")

        # 4) 검색 실행
        try:
            search_btn = driver.find_element(By.CSS_SELECTOR, "a.btn_srch, input[type='submit'], button[onclick*='search']")
            search_btn.click()
        except NoSuchElementException:
            # JavaScript 직접 실행
            driver.execute_script("javascript:searchRealEst();")

        # 5) 결과 대기
        time.sleep(CRAWL_DELAY * 3)

        # 6) 결과 테이블 파싱
        soup = BeautifulSoup(driver.page_source, "html.parser")
        rows = soup.select("table.Ltbl_list tbody tr, table.tbl_list tbody tr")

        if not rows:
            # 대안 셀렉터 시도
            rows = soup.select("#contents table tr")

        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            try:
                # 사건번호 추출
                case_link = row.find("a")
                case_text = cells[0].get_text(strip=True) if cells else ""
                case_no_match = re.search(r"\d{4}타경\d+", case_text + (case_link.get_text(strip=True) if case_link else ""))
                if not case_no_match:
                    continue

                case_no = case_no_match.group()

                item = AuctionItem(
                    court=req.court,
                    case_no=case_no,
                    address=cells[1].get_text(strip=True) if len(cells) > 1 else None,
                    detail=cells[2].get_text(strip=True) if len(cells) > 2 else None,
                    usage_type=req.subType or req.usageType,
                    appraisal_value=parse_price(cells[3].get_text() if len(cells) > 3 else ""),
                    min_price=parse_price(cells[4].get_text() if len(cells) > 4 else ""),
                    sale_date=parse_date(cells[5].get_text() if len(cells) > 5 else ""),
                    status=cells[6].get_text(strip=True) if len(cells) > 6 else None,
                    fail_count=0,
                    raw_data={"cells": [c.get_text(strip=True) for c in cells]},
                )

                # 유찰 횟수 추출 시도
                for cell in cells:
                    fail_match = re.search(r"(\d+)\s*회?\s*유찰", cell.get_text())
                    if fail_match:
                        item.fail_count = int(fail_match.group(1))
                        break

                results.append(item.model_dump())
            except Exception as e:
                logger.warning(f"행 파싱 실패: {e}")
                continue

        logger.info(f"크롤링 완료: {len(results)}건")

    except TimeoutException:
        logger.error("페이지 로드 타임아웃")
    except Exception as e:
        logger.error(f"크롤링 오류: {e}")
    finally:
        driver.quit()

    return results


def crawl_detail(case_no: str, court: Optional[str] = None) -> Optional[dict]:
    """매물 상세정보 크롤링"""
    driver = create_driver()

    try:
        logger.info(f"상세 크롤링: {case_no}")

        # 사건번호로 직접 조회
        driver.get(f"{COURT_AUCTION_URL}/RetrieveRealEstCarHvyMacDetailInfo.laf")
        time.sleep(CRAWL_DELAY * 2)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        detail = AuctionDetail(case_no=case_no)

        # 사건기본내역 파싱
        case_basic = {}
        basic_table = soup.find("table", class_="tbl_detail")
        if basic_table:
            for row in basic_table.find_all("tr"):
                ths = row.find_all("th")
                tds = row.find_all("td")
                for th, td in zip(ths, tds):
                    key = th.get_text(strip=True)
                    val = td.get_text(strip=True)
                    if key:
                        case_basic[key] = val
        detail.case_basic = case_basic if case_basic else None

        # 기일내역 파싱
        bid_history = []
        bid_table = soup.find("table", id="tblBidHist")
        if bid_table:
            for row in bid_table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) >= 4:
                    bid_history.append({
                        "date": cells[0].get_text(strip=True),
                        "type": cells[1].get_text(strip=True),
                        "min_price": parse_price(cells[2].get_text()),
                        "result": cells[3].get_text(strip=True),
                    })
        detail.bid_history = bid_history if bid_history else None

        # 문건 목록 파싱
        documents = []
        doc_links = soup.select("a[onclick*='openPdf'], a[href*='.pdf']")
        for link in doc_links:
            doc_type = link.get_text(strip=True)
            onclick = link.get("onclick", "")
            href = link.get("href", "")
            documents.append({
                "type": doc_type,
                "url": href if href else onclick,
            })
        detail.documents = documents if documents else None

        return detail.model_dump()

    except Exception as e:
        logger.error(f"상세 크롤링 오류: {e}")
        return None
    finally:
        driver.quit()


def crawl_appraisal(case_no: str, court: Optional[str] = None) -> Optional[str]:
    """감정평가서 PDF URL 추출"""
    driver = create_driver()

    try:
        logger.info(f"감정평가서 크롤링: {case_no}")

        driver.get(f"{COURT_AUCTION_URL}/RetrieveRealEstCarHvyMacDetailInfo.laf")
        time.sleep(CRAWL_DELAY * 2)

        # 감정평가서 버튼/링크 찾기
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # PDF 링크 패턴
        pdf_patterns = [
            "a[onclick*='감정평가']",
            "a[onclick*='appraisal']",
            "a[href*='appraisal']",
            "a[href*='.pdf']",
        ]

        for pattern in pdf_patterns:
            links = soup.select(pattern)
            for link in links:
                href = link.get("href", "")
                if href and ".pdf" in href.lower():
                    return href

                onclick = link.get("onclick", "")
                url_match = re.search(r"['\"]([^'\"]*\.pdf[^'\"]*)['\"]", onclick)
                if url_match:
                    return url_match.group(1)

        logger.warning(f"감정평가서 PDF를 찾을 수 없음: {case_no}")
        return None

    except Exception as e:
        logger.error(f"감정평가서 크롤링 오류: {e}")
        return None
    finally:
        driver.quit()
