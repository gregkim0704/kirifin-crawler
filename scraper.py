"""
법원경매 사이트 크롤러 (Selenium 기반)
대한민국 법원 경매정보 사이트 (courtauction.go.kr) 크롤링
"""

import os
import re
import time
import logging
import base64
import tempfile
from typing import Optional
from datetime import datetime
from pathlib import Path

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


# ─── PDF 문서 자동 크롤링 ───

# 문서 저장 디렉토리
DOCS_DIR = Path(tempfile.gettempdir()) / "kirifin_docs"
DOCS_DIR.mkdir(exist_ok=True)

DOC_TYPES = {
    "매각물건명세서": "sale_spec",
    "현황조사서": "status_report",
    "감정평가서": "appraisal",
}


def crawl_documents(case_no: str, court: Optional[str] = None) -> list[dict]:
    """사건의 모든 문서(매각물건명세서/현황조사서/감정평가서) PDF를 자동 크롤링.

    법원경매 사이트에서 사건번호로 상세 페이지 접속 → 문서 탭 → PDF 다운로드.
    다운로드된 PDF는 base64로 인코딩하여 반환합니다.

    Args:
        case_no: 사건번호 (예: "2024타경108834")
        court: 법원명 (선택)

    Returns:
        [{"type": "매각물건명세서", "filename": "...", "base64": "...", "url": "..."}, ...]
    """
    driver = create_driver()
    documents = []

    try:
        logger.info(f"문서 크롤링 시작: {case_no}")

        # 사건번호에서 연도와 번호 추출
        match = re.match(r"(\d{4})타경(\d+)", case_no)
        if not match:
            logger.error(f"잘못된 사건번호 형식: {case_no}")
            return []

        year, num = match.groups()

        # 법원경매 사이트 상세 페이지 접속
        detail_url = (
            f"{COURT_AUCTION_URL}/RetrieveRealEstCarHvyMacDetailInfo.laf"
            f"?saession=00000000&saession2=00000000"
        )
        driver.get(detail_url)
        time.sleep(CRAWL_DELAY * 2)

        # 사건번호 입력하여 검색 시도
        try:
            # 사건번호 직접 입력
            case_input = driver.find_elements(By.CSS_SELECTOR,
                "input[name*='saNo'], input[name*='caseNo'], input[id*='saNo']")
            if case_input:
                case_input[0].clear()
                case_input[0].send_keys(case_no)
                time.sleep(CRAWL_DELAY)
        except Exception as e:
            logger.warning(f"사건번호 입력 실패: {e}")

        # 페이지 소스 파싱
        time.sleep(CRAWL_DELAY * 2)
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # PDF 링크 탐색 패턴들
        pdf_selectors = [
            # 직접적인 PDF 링크
            "a[href*='.pdf']",
            "a[onclick*='openPdf']",
            "a[onclick*='viewPdf']",
            "a[onclick*='PDF']",
            "a[onclick*='pdf']",
            # 문건 관련 링크
            "a[onclick*='매각물건']",
            "a[onclick*='현황조사']",
            "a[onclick*='감정평가']",
            "a[onclick*='MungunView']",
            "a[onclick*='RetrieveMungun']",
            # 일반적인 문서 링크
            "a[class*='doc'], a[class*='pdf'], a[class*='file']",
        ]

        found_links = []
        for selector in pdf_selectors:
            links = soup.select(selector)
            for link in links:
                text = link.get_text(strip=True)
                href = link.get("href", "")
                onclick = link.get("onclick", "")
                found_links.append({
                    "text": text,
                    "href": href,
                    "onclick": onclick,
                })

        logger.info(f"발견된 문서 링크: {len(found_links)}개")

        # 각 문서 유형별로 PDF URL 추출
        for doc_name, doc_key in DOC_TYPES.items():
            for link_info in found_links:
                combined = f"{link_info['text']} {link_info['href']} {link_info['onclick']}"
                if doc_name in combined or doc_key in combined.lower():
                    pdf_url = None

                    # href에서 PDF URL 추출
                    if link_info["href"] and ".pdf" in link_info["href"].lower():
                        pdf_url = link_info["href"]
                        if not pdf_url.startswith("http"):
                            pdf_url = COURT_AUCTION_URL + pdf_url

                    # onclick에서 URL 추출
                    if not pdf_url and link_info["onclick"]:
                        url_match = re.search(
                            r"['\"]([^'\"]*(?:\.pdf|Mungun|mungun|PDF)[^'\"]*)['\"]",
                            link_info["onclick"]
                        )
                        if url_match:
                            pdf_url = url_match.group(1)
                            if not pdf_url.startswith("http"):
                                pdf_url = COURT_AUCTION_URL + "/" + pdf_url.lstrip("/")

                    if pdf_url:
                        doc_data = _download_pdf(driver, pdf_url, case_no, doc_key)
                        if doc_data:
                            documents.append({
                                "type": doc_name,
                                "key": doc_key,
                                "filename": f"{case_no}_{doc_key}.pdf",
                                "url": pdf_url,
                                "size": len(doc_data),
                                "base64": base64.b64encode(doc_data).decode("utf-8"),
                            })
                            logger.info(f"  ✅ {doc_name} 다운로드 완료 ({len(doc_data)} bytes)")
                        break  # 해당 문서 유형은 하나만

        # 직접 JavaScript로 문서 URL 탐색 시도
        if not documents:
            logger.info("직접 링크 탐색 시도...")
            try:
                js_urls = driver.execute_script("""
                    var urls = [];
                    var allLinks = document.querySelectorAll('a');
                    allLinks.forEach(function(a) {
                        var href = a.href || '';
                        var onclick = a.getAttribute('onclick') || '';
                        var text = a.textContent || '';
                        if (href.includes('pdf') || href.includes('PDF') ||
                            onclick.includes('pdf') || onclick.includes('PDF') ||
                            onclick.includes('Mungun') ||
                            text.includes('매각') || text.includes('현황') || text.includes('감정')) {
                            urls.push({text: text.trim(), href: href, onclick: onclick});
                        }
                    });
                    return urls;
                """)
                logger.info(f"JS 탐색 결과: {len(js_urls or [])}개 링크")
                for js_link in (js_urls or []):
                    logger.info(f"  - {js_link.get('text', '')}: {js_link.get('href', '')[:80]}")
            except Exception as e:
                logger.warning(f"JS 탐색 실패: {e}")

        logger.info(f"문서 크롤링 완료: {len(documents)}개 다운로드")

    except Exception as e:
        logger.error(f"문서 크롤링 오류: {e}")
    finally:
        driver.quit()

    return documents


def _download_pdf(driver, url: str, case_no: str, doc_key: str) -> Optional[bytes]:
    """PDF 파일 다운로드"""
    try:
        import httpx

        # Selenium 세션 쿠키를 httpx로 전달
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.get(url, cookies=cookies, headers={
                "User-Agent": driver.execute_script("return navigator.userAgent"),
                "Referer": COURT_AUCTION_URL,
            })

            if resp.status_code == 200 and len(resp.content) > 100:
                # 로컬 저장
                filepath = DOCS_DIR / f"{case_no}_{doc_key}.pdf"
                filepath.write_bytes(resp.content)
                return resp.content

        logger.warning(f"PDF 다운로드 실패: {url} (status={resp.status_code})")
        return None

    except Exception as e:
        logger.warning(f"PDF 다운로드 오류: {url} — {e}")
        return None
