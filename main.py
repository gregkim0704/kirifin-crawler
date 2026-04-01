"""
KiriFin:Auction — FastAPI 크롤링 서버
법원경매 사이트 크롤링 백엔드.

실행: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import SearchRequest, DetailRequest, AppraisalRequest
from scraper import crawl_search, crawl_detail, crawl_appraisal

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    logger.info("🚀 KiriFin 크롤링 서버 시작")
    yield
    logger.info("🛑 KiriFin 크롤링 서버 종료")


app = FastAPI(
    title="KiriFin:Auction Crawler",
    description="법원경매 사이트 크롤링 API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — Next.js 프론트엔드 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://localhost:3000",
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """서버 상태 확인"""
    return {"status": "ok", "service": "kirifin-crawler"}


@app.post("/crawl/search")
async def search_auctions(req: SearchRequest):
    """
    법원경매 사이트에서 매물 검색.
    Selenium으로 크롤링 후 파싱된 결과를 반환합니다.
    소요시간: 약 2-3분.
    """
    try:
        logger.info(f"검색 요청: {req.court} / {req.usageType}")
        results = crawl_search(req)
        return {
            "success": True,
            "data": results,
            "count": len(results),
        }
    except Exception as e:
        logger.error(f"검색 크롤링 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/crawl/detail")
async def get_detail(req: DetailRequest):
    """
    매물 상세정보 크롤링.
    사건번호로 상세 페이지를 크롤링하여 기본정보, 기일내역, 문건 등을 반환합니다.
    소요시간: 약 1-2분.
    """
    try:
        logger.info(f"상세 요청: {req.caseNo}")
        detail = crawl_detail(req.caseNo, req.court)
        if not detail:
            raise HTTPException(status_code=404, detail="상세정보를 가져올 수 없습니다.")
        return {"success": True, "data": detail}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"상세 크롤링 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/crawl/appraisal")
async def get_appraisal(req: AppraisalRequest):
    """
    감정평가서 PDF URL 추출.
    소요시간: 약 30초.
    """
    try:
        logger.info(f"감정평가서 요청: {req.caseNo}")
        pdf_url = crawl_appraisal(req.caseNo, req.court)
        if not pdf_url:
            return {
                "success": True,
                "pdfUrl": None,
                "message": "감정평가서 PDF를 찾을 수 없습니다.",
            }
        return {"success": True, "pdfUrl": pdf_url}
    except Exception as e:
        logger.error(f"감정평가서 크롤링 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
