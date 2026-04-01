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
from scraper import crawl_search, crawl_detail, crawl_appraisal, crawl_documents

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


@app.post("/crawl/documents")
async def get_documents(req: DetailRequest):
    """
    사건의 모든 문서(매각물건명세서/현황조사서/감정평가서) PDF 자동 크롤링.
    법원경매 사이트에서 PDF를 다운로드하여 base64로 인코딩해 반환합니다.
    소요시간: 약 1-3분.
    """
    try:
        logger.info(f"문서 크롤링 요청: {req.caseNo}")
        docs = crawl_documents(req.caseNo, req.court)
        return {
            "success": True,
            "data": [
                {
                    "type": d["type"],
                    "filename": d["filename"],
                    "url": d.get("url", ""),
                    "size": d.get("size", 0),
                    "hasData": bool(d.get("base64")),
                }
                for d in docs
            ],
            "count": len(docs),
            "message": f"{len(docs)}개 문서를 크롤링했습니다." if docs else "문서를 찾을 수 없습니다. 법원경매 사이트에서 해당 사건의 문서가 아직 등록되지 않았을 수 있습니다.",
        }
    except Exception as e:
        logger.error(f"문서 크롤링 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/crawl/document-download")
async def download_document(req: DetailRequest):
    """
    특정 사건의 문서를 다운로드하여 base64 데이터로 반환합니다.
    프론트엔드에서 base64를 디코딩하여 PDF로 저장할 수 있습니다.
    """
    try:
        logger.info(f"문서 다운로드 요청: {req.caseNo}")
        docs = crawl_documents(req.caseNo, req.court)
        return {
            "success": True,
            "data": docs,
            "count": len(docs),
        }
    except Exception as e:
        logger.error(f"문서 다운로드 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
