"""doit-voc-agent FastAPI 애플리케이션 (스펙 §6.1)."""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.agent import run_agent
from backend.config import settings
from backend.constants import ESCALATION_STATUSES
from backend.database import SessionLocal, init_database
from backend.judge import get_judge_provider, run_judge
from backend.llm import get_llm_provider
from backend.models import VocRecord
from backend.observability import get_trace_id, make_trace_handler, tracing_enabled
from backend.schemas import (
    ChatRequest,
    ChatResponse,
    StatsResponse,
    VocOut,
    VocStatusUpdate,
)


def create_app(provider=None, session_factory=None) -> FastAPI:
    """앱 팩토리 — 테스트에서 provider/session_factory를 주입한다."""
    app = FastAPI(title="doit-voc-agent API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 개발 모드 전체 허용 (tpssAgent와 동일)
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    init_database()
    app.state.provider = provider
    app.state.session_factory = session_factory or SessionLocal

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(request: ChatRequest, background_tasks: BackgroundTasks):
        provider = app.state.provider or get_llm_provider(settings)
        app.state.provider = provider
        if provider is None:
            raise HTTPException(
                status_code=503,
                detail="LLM이 설정되지 않았습니다. .env의 LLM_API_KEY를 확인하세요.",
            )
        # Langfuse 활성 시 요청 세션 단위 트레이스 핸들러를 붙인다 (비활성 → None)
        handler = make_trace_handler(settings, request.session_id) if tracing_enabled(settings) else None
        result = run_agent(
            voc_text=request.voc_text,
            session_id=request.session_id,
            provider=provider,
            session_factory=app.state.session_factory,
            callbacks=[handler] if handler else None,
        )
        voc_id = result.get("voc_id")
        trace_id = get_trace_id(handler)
        if settings.judge_enabled and voc_id is not None:
            judge_provider = get_judge_provider(settings, provider)
            background_tasks.add_task(
                run_judge, voc_id, judge_provider, app.state.session_factory, trace_id
            )
        return ChatResponse(
            response=result.get("response", ""),
            category=result.get("category", "기타"),
            priority=result.get("priority", "medium"),
            escalated=bool(result.get("escalated")),
            sources=result.get("answer_sources") or [],
            voc_id=result.get("voc_id"),
            session_id=request.session_id,
        )

    @app.get("/api/vocs", response_model=List[VocOut])
    def list_vocs(
        category: Optional[str] = None,
        escalated: Optional[bool] = None,
        status: Optional[str] = None,
        judge_cause: Optional[str] = None,
        limit: int = Query(default=100, le=500),
    ):
        db = app.state.session_factory()
        try:
            query = db.query(VocRecord).order_by(VocRecord.created_at.desc())
            if category:
                query = query.filter(VocRecord.category == category)
            if escalated is not None:
                query = query.filter(VocRecord.escalated == escalated)
            if status:
                query = query.filter(VocRecord.escalation_status == status)
            if judge_cause:
                if judge_cause == "미채점":
                    query = query.filter(VocRecord.judge_cause.is_(None))
                else:
                    query = query.filter(VocRecord.judge_cause == judge_cause)
            return query.limit(limit).all()
        finally:
            db.close()

    @app.get("/api/vocs/{voc_id}", response_model=VocOut)
    def get_voc(voc_id: int):
        db = app.state.session_factory()
        try:
            record = db.query(VocRecord).filter(VocRecord.id == voc_id).first()
            if record is None:
                raise HTTPException(status_code=404, detail="VOC를 찾을 수 없습니다")
            return record
        finally:
            db.close()

    @app.patch("/api/vocs/{voc_id}/status", response_model=VocOut)
    def update_status(voc_id: int, payload: VocStatusUpdate):
        if payload.status not in ESCALATION_STATUSES:
            raise HTTPException(status_code=422, detail="status는 open 또는 resolved여야 합니다")
        db = app.state.session_factory()
        try:
            record = db.query(VocRecord).filter(VocRecord.id == voc_id).first()
            if record is None:
                raise HTTPException(status_code=404, detail="VOC를 찾을 수 없습니다")
            record.escalation_status = payload.status
            record.resolved_at = datetime.utcnow() if payload.status == "resolved" else None
            db.commit()
            db.refresh(record)
            return record
        finally:
            db.close()

    @app.get("/api/stats", response_model=StatsResponse)
    def stats():
        db = app.state.session_factory()
        try:
            records = db.query(VocRecord).all()
            by_category: dict = {}
            for r in records:
                by_category[r.category] = by_category.get(r.category, 0) + 1
            escalated_open = sum(
                1 for r in records if r.escalated and r.escalation_status == "open"
            )
            by_day: dict = {}
            today = datetime.utcnow().date()
            for offset in range(6, -1, -1):
                by_day[(today - timedelta(days=offset)).isoformat()] = 0
            for r in records:
                key = r.created_at.date().isoformat()
                if key in by_day:
                    by_day[key] += 1
            judged = [r for r in records if r.judge_total is not None]
            avg_judge_total = (
                round(sum(r.judge_total for r in judged) / len(judged), 1) if judged else None
            )
            low_score_count = sum(1 for r in judged if r.judge_total <= 9)
            material_gap_count = sum(1 for r in records if r.judge_cause == "재료부족")
            material_gap_count += sum(
                1 for r in records
                if r.category == "사용법문의" and r.escalated and not r.answer_sources
            )
            return StatsResponse(
                total=len(records),
                by_category=by_category,
                escalated_open=escalated_open,
                by_day=[{"date": d, "count": c} for d, c in by_day.items()],
                avg_judge_total=avg_judge_total,
                low_score_count=low_score_count,
                material_gap_count=material_gap_count,
            )
        finally:
            db.close()

    @app.get("/health")
    def health():
        provider_ready = app.state.provider is not None or get_llm_provider(settings) is not None
        return {"status": "ok", "llm_configured": provider_ready}

    return app


app = create_app()
