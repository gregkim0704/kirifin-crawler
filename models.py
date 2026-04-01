"""Pydantic 모델 정의"""

from pydantic import BaseModel
from typing import Optional


class SearchRequest(BaseModel):
    court: str
    usageType: str = "전체"
    subType: Optional[str] = None
    priceMin: Optional[int] = None
    priceMax: Optional[int] = None
    areaMin: Optional[float] = None
    areaMax: Optional[float] = None


class DetailRequest(BaseModel):
    caseNo: str
    court: Optional[str] = None


class AppraisalRequest(BaseModel):
    caseNo: str
    court: Optional[str] = None


class AuctionItem(BaseModel):
    court: str
    case_no: str
    item_no: Optional[str] = None
    address: Optional[str] = None
    detail: Optional[str] = None
    usage_type: Optional[str] = None
    appraisal_value: Optional[int] = None
    min_price: Optional[int] = None
    sale_date: Optional[str] = None
    fail_count: int = 0
    status: Optional[str] = None
    is_watched: bool = False
    grade: Optional[str] = None
    raw_data: Optional[dict] = None


class AuctionDetail(BaseModel):
    case_no: str
    case_basic: Optional[dict] = None
    item_basic: Optional[dict] = None
    bid_history: Optional[list] = None
    appraisal_summary: Optional[dict] = None
    documents: Optional[list] = None
    note: Optional[str] = None
    appraisal_pdf_url: Optional[str] = None
