from __future__ import annotations

import base64
from dataclasses import asdict
from datetime import datetime
from html import escape
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import time

import pandas as pd
import streamlit as st

from src.config import load_config
from src.db.database import Database
from src.db.repositories import SearchRepository
from src.ingestion.heading_extractor import STATIC_CHAPTERS
from src.search.chapter_filter import ChapterFilterNotFound
from src.search.filters import filters_for_scope
from src.search.nlu_query_parser import ParsedNaturalQuery, parse_natural_query
from src.search.query_parser import parse_search_query
from src.search.query_expander import expand_query
from src.search.reranker import rerank_results
from src.search.rfp_search_service import RfpSearchService
from src.search.search_quality_diagnostics import run_search_quality_diagnostics
from src.search.search_service import SearchService
from src.search.structured_result_service import build_evidence_rows, build_structured_rows, document_area
from src.services.download_service import DownloadService
from src.services.index_management_service import IndexManagementService
from src.services.preview_service import PreviewResult, PreviewService, request_page_no
from src.ui.search_results import document_groups, preview_request, result_rows


PREVIEW_PREFETCH_LIMIT = 8
AUTO_CHAPTER = "자동 감지"
ALL_CHAPTERS = "전체"
SCOPE_ALL = "전체"
SCOPE_PROPOSAL = "제안서"
SCOPE_REPORT = "보고서"


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --console-navy: #08224a;
                --console-blue: #0b5cff;
                --console-blue-soft: #eaf2ff;
                --console-border: #dbe5f2;
                --console-muted: #667085;
                --console-text: #12213a;
                --console-bg: #f5f8fc;
                --console-card: #ffffff;
                --console-shadow: 0 16px 42px rgba(16, 42, 78, 0.10);
            }

            html, body, [class*="css"] {
                font-family: "Pretendard", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", Arial, sans-serif;
                color: var(--console-text);
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(31, 111, 235, 0.12), transparent 34rem),
                    linear-gradient(135deg, #f8fbff 0%, #eef4fb 45%, #f7f9fc 100%);
            }

            section[data-testid="stSidebar"] {
                background: linear-gradient(180deg, #081e3c 0%, #0d2b52 58%, #081a32 100%);
                border-right: 1px solid rgba(255, 255, 255, 0.08);
            }

            section[data-testid="stSidebar"] * {
                color: #f7fbff;
            }

            section[data-testid="stSidebar"] .stCaption,
            section[data-testid="stSidebar"] small,
            section[data-testid="stSidebar"] p {
                color: rgba(247, 251, 255, 0.78);
            }

            section[data-testid="stSidebar"] button {
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.16);
                background: rgba(255, 255, 255, 0.08);
            }

            .block-container {
                padding-top: 1.35rem;
                padding-bottom: 3rem;
                max-width: 1480px;
            }

            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-color: var(--console-border);
                box-shadow: 0 10px 26px rgba(16, 42, 78, 0.06);
                background: rgba(255, 255, 255, 0.96);
            }

            div[data-testid="stMetric"] {
                background: var(--console-card);
                border: 1px solid var(--console-border);
                border-radius: 10px;
                padding: 0.85rem 0.95rem;
                box-shadow: 0 8px 22px rgba(16, 42, 78, 0.05);
            }

            div[data-testid="stTextInput"] input {
                border-radius: 10px;
                min-height: 3rem;
                border-color: #cad7e8;
                font-size: 1rem;
            }

            div[data-testid="stTextInput"] input:focus {
                border-color: var(--console-blue);
                box-shadow: 0 0 0 3px rgba(11, 92, 255, 0.12);
            }

            .stButton > button, .stDownloadButton > button {
                border-radius: 9px;
                min-height: 2.65rem;
                font-weight: 700;
            }

            .console-hero {
                position: relative;
                overflow: hidden;
                padding: 1.15rem 1.45rem;
                margin-bottom: 1rem;
                border: 1px solid rgba(150, 176, 214, 0.46);
                border-radius: 14px;
                background:
                    linear-gradient(120deg, rgba(8, 34, 74, 0.98), rgba(10, 58, 130, 0.94)),
                    radial-gradient(circle at 78% 20%, rgba(73, 144, 255, 0.38), transparent 22rem);
                color: white;
                box-shadow: var(--console-shadow);
            }

            .console-hero:after {
                content: "";
                position: absolute;
                inset: auto -6rem -9rem auto;
                width: 32rem;
                height: 22rem;
                border: 1px solid rgba(255, 255, 255, 0.11);
                border-radius: 999px;
                transform: rotate(-15deg);
            }

            .console-hero h1 {
                position: relative;
                margin: 0;
                color: white;
                font-size: clamp(2rem, 4vw, 3.15rem);
                font-weight: 850;
                letter-spacing: 0;
            }

            .console-hero p {
                position: relative;
                margin: 0.35rem 0 0;
                color: rgba(255, 255, 255, 0.82);
                font-size: 1.02rem;
            }

            .hero-grid {
                position: relative;
                display: grid;
                grid-template-columns: 1.35fr 1fr;
                gap: 1.2rem;
                margin-top: 0.95rem;
            }

            .hero-panel {
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 12px;
                padding: 1rem;
                background: rgba(255, 255, 255, 0.08);
                backdrop-filter: blur(8px);
            }

            .hero-label {
                font-size: 0.78rem;
                color: rgba(255, 255, 255, 0.66);
                margin-bottom: 0.45rem;
                font-weight: 700;
            }

            .chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: 0.45rem;
            }

            .console-chip {
                display: inline-flex;
                align-items: center;
                min-height: 1.9rem;
                padding: 0.38rem 0.75rem;
                border-radius: 999px;
                border: 1px solid rgba(11, 92, 255, 0.18);
                background: #eef5ff;
                color: #0b3d86;
                font-size: 0.82rem;
                font-weight: 700;
                margin: 0 0.35rem 0.35rem 0;
            }

            .console-chip.dark {
                border-color: rgba(255, 255, 255, 0.2);
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }

            .keyword-chip {
                display: inline-flex;
                align-items: center;
                min-height: 1.75rem;
                padding: 0.3rem 0.66rem;
                border-radius: 999px;
                border: 1px solid rgba(11, 92, 255, 0.18);
                background: var(--console-blue-soft);
                color: #0b3d86;
                font-size: 0.78rem;
                font-weight: 750;
                margin: 0 0.28rem 0.32rem 0;
            }

            .app-shell {
                display: block;
            }

            .compact-header {
                display: flex;
                justify-content: space-between;
                gap: 1rem;
                align-items: center;
                padding: 1rem 1.15rem;
                margin-bottom: 0.95rem;
                border: 1px solid var(--console-border);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.96);
                box-shadow: 0 10px 28px rgba(16, 42, 78, 0.07);
            }

            .compact-header h1 {
                margin: 0;
                color: var(--console-navy);
                font-size: 1.45rem;
                font-weight: 900;
                letter-spacing: 0;
            }

            .compact-header p {
                margin: 0.15rem 0 0;
                color: var(--console-muted);
                font-size: 0.92rem;
            }

            .status-pill {
                display: inline-flex;
                align-items: center;
                gap: 0.4rem;
                min-height: 2rem;
                padding: 0.35rem 0.72rem;
                border: 1px solid #bde7ca;
                border-radius: 999px;
                background: #eefaf2;
                color: #16703a;
                font-weight: 800;
                font-size: 0.82rem;
            }

            .search-panel {
                border: 1px solid var(--console-border);
                border-radius: 12px;
                background: rgba(255, 255, 255, 0.98);
                padding: 1rem;
                box-shadow: 0 12px 30px rgba(16, 42, 78, 0.07);
            }

            .filter-summary, .result-status-bar {
                border: 1px solid var(--console-border);
                border-radius: 10px;
                background: #f8fbff;
                padding: 0.72rem 0.9rem;
                color: var(--console-muted);
                font-size: 0.9rem;
                margin: 0.7rem 0 0.25rem;
            }

            .section-title {
                margin: 1.15rem 0 0.55rem;
            }

            .section-title h2 {
                margin: 0;
                color: var(--console-navy);
                font-size: 1.22rem;
                font-weight: 850;
                letter-spacing: 0;
            }

            .section-title p {
                margin: 0.18rem 0 0;
                color: var(--console-muted);
                font-size: 0.92rem;
            }

            .intent-card {
                border: 1px solid #bcd3ff;
                border-radius: 12px;
                padding: 1rem;
                background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
                box-shadow: 0 10px 26px rgba(11, 92, 255, 0.07);
                margin: 0.75rem 0;
            }

            .intent-card h3 {
                margin: 0 0 0.8rem;
                font-size: 1rem;
                color: #0b5cff;
                font-weight: 850;
            }

            .intent-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.65rem;
            }

            .intent-item, .kpi-card, .mode-help-card, .rfp-step {
                border: 1px solid var(--console-border);
                border-radius: 10px;
                background: #ffffff;
                padding: 0.85rem;
                box-shadow: 0 8px 20px rgba(16, 42, 78, 0.05);
            }

            .intent-label, .kpi-label {
                color: var(--console-muted);
                font-size: 0.76rem;
                font-weight: 750;
                margin-bottom: 0.25rem;
            }

            .intent-value, .kpi-value {
                color: var(--console-navy);
                font-size: 1rem;
                font-weight: 850;
                line-height: 1.35;
            }

            .kpi-value {
                font-size: 1.45rem;
            }

            .kpi-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.8rem;
                margin: 0.95rem 0 0.75rem;
            }

            .mode-help-grid, .rfp-steps {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.8rem;
                margin: 0.55rem 0 0.95rem;
            }

            .rfp-steps {
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }

            .mode-help-card.active {
                border-color: #7aa7ff;
                background: linear-gradient(180deg, #ffffff 0%, #f4f8ff 100%);
            }

            .card-title {
                margin: 0;
                color: var(--console-navy);
                font-weight: 850;
                font-size: 1rem;
            }

            .card-desc {
                margin: 0.25rem 0 0;
                color: var(--console-muted);
                font-size: 0.88rem;
                line-height: 1.45;
            }

            .document-title-line {
                color: var(--console-navy);
                font-weight: 850;
                font-size: 1.02rem;
            }

            .document-meta-line {
                color: var(--console-muted);
                font-size: 0.84rem;
                margin-top: 0.18rem;
            }

            .evidence-note {
                border: 1px solid #f0dca2;
                border-radius: 9px;
                background: #fff9e8;
                color: #614700;
                padding: 0.85rem;
                line-height: 1.55;
            }

            .evidence-box {
                border: 1px solid #f0dca2;
                border-radius: 10px;
                background: #fff9e8;
                color: #4e3b00;
                padding: 0.95rem;
                line-height: 1.68;
                font-size: 0.92rem;
            }

            .document-card, .ranking-card {
                border: 1px solid var(--console-border);
                border-radius: 12px;
                background: var(--console-card);
                padding: 1rem;
                box-shadow: 0 12px 28px rgba(16, 42, 78, 0.06);
                margin-bottom: 0.85rem;
            }

            .document-card-head {
                display: grid;
                grid-template-columns: 2.8rem 1fr auto;
                gap: 0.8rem;
                align-items: start;
            }

            .document-icon {
                width: 2.55rem;
                height: 2.55rem;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: 12px;
                background: var(--console-blue-soft);
                color: var(--console-blue);
            }

            .score-badge {
                display: inline-flex;
                align-items: center;
                border-radius: 999px;
                padding: 0.28rem 0.66rem;
                background: #eef5ff;
                border: 1px solid #cddfff;
                color: #0b5cff;
                font-weight: 850;
                font-size: 0.82rem;
            }

            .action-row {
                display: flex;
                gap: 0.45rem;
                align-items: center;
                justify-content: flex-end;
                margin-top: 0.75rem;
            }

            .rfp-workflow {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.8rem;
                margin: 0.55rem 0 0.95rem;
            }

            .rfp-step.done {
                border-color: #bde7ca;
                background: linear-gradient(180deg, #ffffff 0%, #f1fbf5 100%);
            }

            .ranking-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.8rem;
                margin-bottom: 0.9rem;
            }

            @media (max-width: 900px) {
                .compact-header,
                .hero-grid,
                .intent-grid,
                .mode-help-grid,
                .rfp-steps,
                .rfp-workflow,
                .kpi-grid,
                .ranking-grid,
                .document-card-head {
                    grid-template-columns: 1fr;
                    display: grid;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _chips(values: list[str] | tuple[str, ...], dark: bool = False, limit: int = 12) -> str:
    class_name = "console-chip dark" if dark else "keyword-chip"
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    if not cleaned:
        cleaned = ["확인 필요"]
    return "".join(f'<span class="{class_name}">{escape(value)}</span>' for value in cleaned[:limit])


def _icon(name: str) -> str:
    icons = {
        "search": '<circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2 18 18"/>',
        "document": '<path d="M6 3h7l5 5v13H6z"/><path d="M13 3v5h5"/><path d="M8.5 12h7"/><path d="M8.5 16h7"/>',
        "file": '<path d="M7 3h6l4 4v14H7z"/><path d="M13 3v4h4"/>',
        "eye": '<path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6z"/><circle cx="12" cy="12" r="3"/>',
        "download": '<path d="M12 3v11"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
        "save": '<path d="M5 4h12l2 2v14H5z"/><path d="M8 4v6h8"/><path d="M8 17h8"/>',
        "database": '<ellipse cx="12" cy="5" rx="7" ry="3"/><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5"/><path d="M5 12v5c0 1.7 3.1 3 7 3s7-1.3 7-3v-5"/>',
        "shield": '<path d="M12 3 20 6v6c0 4.8-3.3 8-8 9-4.7-1-8-4.2-8-9V6z"/>',
        "folder": '<path d="M3 6h7l2 2h9v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
        "chart": '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-5"/><path d="M12 16V8"/><path d="M16 16v-9"/>',
        "spark": '<path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8z"/>',
    }
    body = icons.get(name, icons["document"])
    return (
        '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
        'aria-hidden="true">'
        f"{body}</svg>"
    )


def _render_section_title(title: str, description: str = "") -> None:
    st.markdown(
        f"""
        <div class="section-title">
            <h2>{escape(title)}</h2>
            <p>{escape(description)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(config, repository: SearchRepository) -> None:
    try:
        stats = repository.stats()
    except Exception:
        stats = {"documents": 0, "chunks": 0}
    scope_text = " / ".join(Path(folder).name or str(folder) for folder in config.root_folders)
    examples = [
        "목표모델에서 클라우드 전환 설계 찾아줘",
        "투입인력에서 ISP 경험 있는 PM 찾아줘",
        "비용산정에서 클라우드 TCO 찾아줘",
    ]
    st.markdown(
        f"""
        <div class="console-hero">
            <h1>사내 제안/산출물 Intelligence Search Console</h1>
            <p>제안서, 보고서, RFP 기반 내부 지식자산을 자연어로 탐색하고 근거 문장까지 추적합니다.</p>
            <div class="hero-grid">
                <div class="hero-panel">
                    <div class="hero-label">자연어 질의 예시</div>
                    <div class="chip-row">{_chips(examples, dark=True)}</div>
                </div>
                <div class="hero-panel">
                    <div class="hero-label">검색 가능 범위</div>
                    <div class="chip-row">{_chips([scope_text or "색인 루트 확인 필요", f"색인 문서 {stats.get('documents', 0):,}건", f"검색 chunk {stats.get('chunks', 0):,}건"], dark=True)}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _index_finished_at(config) -> str:
    report_path = Path(config.data_dir) / "indexes" / "reindex_report.json"
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return "확인 필요"
    value = str(data.get("finished_at") or data.get("started_at") or "").strip()
    if not value:
        return "확인 필요"
    return value[:16].replace("T", " ")


def _render_compact_header(config, repository: SearchRepository) -> None:
    try:
        stats = repository.stats()
    except Exception:
        stats = {"documents": 0, "chunks": 0}
    st.markdown(
        f"""
        <div class="compact-header">
            <div>
                <h1>사내 산출물 AI 검색</h1>
                <p>제안서·보고서·RFP 기반 내부 지식자산 검색</p>
            </div>
            <div style="display:flex; gap:0.55rem; flex-wrap:wrap; justify-content:flex-end;">
                <span class="status-pill">Index Ready</span>
                <span class="keyword-chip">색인 문서 {stats.get('documents', 0):,}건</span>
                <span class="keyword-chip">검색 chunk {stats.get('chunks', 0):,}건</span>
                <span class="keyword-chip">최근 색인 {_index_finished_at(config)}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_mode_selector(search_running: bool, show_description: bool = True) -> str:
    _render_section_title("검색 모드", "업무 목적에 맞는 검색 흐름을 선택하세요.")
    current = st.session_state.get("active_search_mode", "주제/키워드 검색")
    if show_description:
        st.markdown(
            f"""
            <div class="mode-help-grid">
                <div class="mode-help-card {'active' if current == '주제/키워드 검색' else ''}">
                    <p class="card-title">{_icon('search')} 주제/키워드 검색</p>
                    <p class="card-desc">자연어 질의로 관련 문서, 페이지, 문서영역, 근거 문장을 탐색합니다.</p>
                </div>
                <div class="mode-help-card {'active' if current == '신규 RFP 기반 검색' else ''}">
                    <p class="card-title">{_icon('file')} 신규 RFP 기반 검색</p>
                    <p class="card-desc">RFP를 업로드하여 요구사항을 분석하고 유사 프로젝트 산출물을 매핑합니다.</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    options = ["주제/키워드 검색", "신규 RFP 기반 검색"]
    if hasattr(st, "segmented_control"):
        mode = st.segmented_control("검색 모드 선택", options, default=current, disabled=search_running, label_visibility="collapsed")
    else:
        mode = st.radio("검색 모드 선택", options, index=options.index(current), horizontal=True, label_visibility="collapsed", disabled=search_running)
    mode = mode or current
    st.session_state["active_search_mode"] = mode
    return mode


def _init_session_state() -> None:
    defaults = {
        "search_running": False,
        "pending_topic_search": None,
        "topic_results": None,
        "topic_error": "",
        "topic_search_info": None,
        "topic_natural_query": None,
        "topic_structured_rows": None,
        "topic_evidence_rows": None,
        "pending_rfp_search": None,
        "rfp_response": None,
        "rfp_error": "",
        "preview_request": None,
        "index_status": None,
        "index_validation": None,
        "selected_heading_filter": "",
        "topic_saved_search_id": "",
        "active_search_mode": "주제/키워드 검색",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _filters_for_scope(scope: str, root_folders: tuple[str, ...]) -> dict | None:
    return filters_for_scope(scope, root_folders)


def _chapter_options(repository: SearchRepository, base_filters: dict | None) -> list[str]:
    options = [AUTO_CHAPTER, ALL_CHAPTERS, *STATIC_CHAPTERS]
    try:
        extracted = repository.chapter_names(base_filters, limit=80)
    except Exception:
        extracted = []
    for chapter in extracted:
        if chapter and chapter not in options:
            options.append(chapter)
    return options


def _effective_chapter_filter(manual_chapter: str, detected_chapter: str) -> str:
    if manual_chapter == AUTO_CHAPTER:
        return detected_chapter
    if manual_chapter == ALL_CHAPTERS:
        return ""
    return manual_chapter


def _result_rows(results):
    return result_rows(results)


def _document_groups(results):
    return document_groups(results)


def _analyze_natural_query(query: str) -> ParsedNaturalQuery:
    return expand_query(parse_natural_query(query))


def _render_natural_query_analysis(parsed: ParsedNaturalQuery) -> None:
    if not parsed.original_query:
        return
    condition_text = ", ".join(f"{key}: {value}" for key, value in parsed.conditions.items() if value)
    confidence_label = "높음" if parsed.confidence >= 0.8 else ("보통" if parsed.confidence >= 0.5 else "낮음")
    domain_label = {
        "architecture_evidence": "아키텍처/목표모델 근거",
        "technology_trend": "기술동향 탐색",
        "cost_estimation": "비용산정 근거",
        "staff_experience": "투입인력/경력 탐색",
        "general": "일반 근거 검색",
    }.get(parsed.search_domain, parsed.search_domain)
    st.markdown(
        f"""
        <div class="intent-card">
            <h3>AI가 이해한 검색 의도</h3>
            <div class="intent-grid">
                <div class="intent-item">
                    <div class="intent-label">검색 도메인</div>
                    <div class="intent-value">{escape(domain_label)}</div>
                </div>
                <div class="intent-item">
                    <div class="intent-label">대상 챕터</div>
                    <div class="intent-value">{escape(parsed.target_chapter or "확인 필요")}</div>
                </div>
                <div class="intent-item">
                    <div class="intent-label">문서영역</div>
                    <div class="intent-value">{escape(parsed.target_section or parsed.target_subsection or "확인 필요")}</div>
                </div>
                <div class="intent-item">
                    <div class="intent-label">confidence</div>
                    <div class="intent-value">{parsed.confidence:.2f} <span class="score-badge">{escape(confidence_label)}</span></div>
                </div>
            </div>
            <div style="margin-top:0.85rem;">
                <div class="intent-label">확장 키워드</div>
                <div style="margin-top:0.35rem;">{_chips(parsed.expanded_keywords, limit=24)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("상세 분석 보기", expanded=False):
        st.write(
            {
                "원문 질의": parsed.original_query,
                "검색 주제": parsed.topic or "확인 필요",
                "추출 조건": condition_text or "확인 필요",
                "semantic_query": parsed.semantic_query,
                "output_type": parsed.output_type,
            }
        )


def _excel_bytes(rows: list[dict], sheet_name: str = "results") -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return buffer.getvalue()


def _download_excel(rows: list[dict], label: str, prefix: str, key: str) -> None:
    if not rows:
        return
    filename = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    st.download_button(
        label,
        data=_excel_bytes(rows),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=key,
    )


def _result_metrics(results) -> dict:
    documents = {result.document_id for result in results}
    pages = {(result.document_id, result.page_no) for result in results}
    areas = {}
    keywords: dict[str, int] = {}
    for result in results:
        area = document_area(result)
        areas[area] = areas.get(area, 0) + 1
        for keyword in [*getattr(result, "matched_keywords", []), *str(getattr(result, "domain_keywords", "")).split(",")]:
            keyword = keyword.strip()
            if keyword:
                keywords[keyword] = keywords.get(keyword, 0) + 1
    top_area = max(areas.items(), key=lambda item: item[1])[0] if areas else "확인 필요"
    top_keywords = ", ".join(keyword for keyword, _ in sorted(keywords.items(), key=lambda item: item[1], reverse=True)[:5])
    return {
        "document_count": len(documents),
        "page_count": len(pages),
        "max_score": max((float(result.score or 0.0) for result in results), default=0.0),
        "top_area": top_area,
        "top_keywords": top_keywords or "확인 필요",
    }


def _render_kpi_cards(metrics: dict) -> None:
    cards = [
        ("관련 문서 수", f"{metrics['document_count']:,}", "검색 결과에 포함된 고유 문서"),
        ("관련 페이지 수", f"{metrics['page_count']:,}", "근거가 발견된 문서 페이지"),
        ("최고 점수", f"{metrics['max_score']:.4f}", "상위 결과의 종합 관련도"),
    ]
    card_html = ""
    for label, value, desc in cards:
        card_html += f"""
            <div class="kpi-card">
                <div class="kpi-label">{escape(label)}</div>
                <div class="kpi-value">{escape(str(value))}</div>
                <div class="document-meta-line">{escape(desc)}</div>
            </div>
        """
    st.markdown(f'<div class="kpi-grid">{card_html}</div>', unsafe_allow_html=True)
    keywords = [keyword.strip() for keyword in str(metrics["top_keywords"]).split(",") if keyword.strip() and keyword.strip() != "확인 필요"]
    st.markdown(
        f"""
        <div class="result-status-bar">
            <strong>주요 문서영역:</strong> {escape(str(metrics["top_area"]))}
            <span style="margin-left:1rem;"><strong>대표 키워드:</strong></span>
            <span style="margin-left:0.35rem;">{_chips(keywords, limit=8)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _area_distribution_rows(results) -> list[dict]:
    grouped: dict[str, dict] = {}
    for result in results:
        area = document_area(result)
        row = grouped.setdefault(area, {"문서영역": area, "문서 수": set(), "페이지 수": set(), "chunk 수": 0, "대표 키워드": {}})
        row["문서 수"].add(result.document_id)
        row["페이지 수"].add((result.document_id, result.page_no))
        row["chunk 수"] += 1
        for keyword in [*getattr(result, "matched_keywords", []), *str(getattr(result, "domain_keywords", "")).split(",")]:
            keyword = keyword.strip()
            if keyword:
                row["대표 키워드"][keyword] = row["대표 키워드"].get(keyword, 0) + 1
    rows = []
    for row in grouped.values():
        keywords = sorted(row["대표 키워드"].items(), key=lambda item: item[1], reverse=True)
        rows.append(
            {
                "문서영역": row["문서영역"],
                "문서 수": len(row["문서 수"]),
                "페이지 수": len(row["페이지 수"]),
                "chunk 수": row["chunk 수"],
                "대표 키워드": ", ".join(keyword for keyword, _ in keywords[:6]),
            }
        )
    return sorted(rows, key=lambda item: item["chunk 수"], reverse=True)


def _rfp_requirement_rows(response) -> list[dict]:
    requirements = response.summary.get("main_requirements") or []
    if not requirements:
        requirements = ["확인 필요"]
    rows = []
    for requirement in requirements:
        matched_results = _results_for_requirement(requirement, response.results)
        if not matched_results:
            rows.append(
                {
                    "요구사항": requirement,
                    "관련 문서": "확인 필요",
                    "프로젝트명": "확인 필요",
                    "페이지": "확인 필요",
                    "근거 문장": "확인 필요",
                    "활용 가능 포인트": "확인 필요",
                }
            )
            continue
        for result in matched_results[:3]:
            rows.append(
                {
                    "요구사항": requirement,
                    "관련 문서": result.document_title or "확인 필요",
                    "프로젝트명": result.project_name or "확인 필요",
                    "페이지": result.display_page or str(result.page_no or "") or "확인 필요",
                    "근거 문장": _trim_text(result.matched_text or "확인 필요", 180),
                    "활용 가능 포인트": _trim_text(result.matched_text or "확인 필요", 180),
                }
            )
    return rows


def _trim_text(text: str, limit: int = 180) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _render_rfp_workflow(done: bool = False) -> None:
    done_class = "done" if done else ""
    status = "분석 완료" if done else "대기"
    st.markdown(
        f"""
        <div class="rfp-workflow">
            <div class="rfp-step {done_class}">
                <p class="card-title">{_icon('file')} 1. RFP 업로드</p>
                <p class="card-desc">제안요청서 파일 등록</p>
            </div>
            <div class="rfp-step {done_class}">
                <p class="card-title">{_icon('spark')} 2. 요구사항 분석</p>
                <p class="card-desc">사업 정보와 핵심 요구사항 추출</p>
            </div>
            <div class="rfp-step {done_class}">
                <p class="card-title">{_icon('chart')} 3. 유사 산출물 매핑</p>
                <p class="card-desc">기존 프로젝트 산출물 연결 · {escape(status)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_rfp_summary(summary: dict) -> None:
    requirements = summary.get("main_requirements") or summary.get("main_tasks") or []
    keywords = summary.get("requirement_keywords") or summary.get("main_keywords") or []
    rows = [
        ("사업명", summary.get("business_name") or "확인 필요"),
        ("발주기관", summary.get("client_name") or "확인 필요"),
        ("제안 범위", summary.get("business_type") or summary.get("purpose") or "확인 필요"),
        ("추천 검색 범위", "제안서 + 보고서"),
    ]
    cols = st.columns(4)
    for col, (label, value) in zip(cols, rows):
        col.markdown(
            f"""
            <div class="intent-item">
                <div class="intent-label">{escape(label)}</div>
                <div class="intent-value" style="font-size:0.94rem;">{escape(_trim_text(str(value), 80))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("**주요 요구사항**")
    st.markdown(_chips([_trim_text(item, 80) for item in requirements[:8]], limit=8), unsafe_allow_html=True)
    st.markdown("**우선 키워드**")
    st.markdown(_chips(keywords[:16], limit=16), unsafe_allow_html=True)


def _render_ranking_cards(projects: list[dict]) -> None:
    if not projects:
        st.info("유사 프로젝트를 찾지 못했습니다.")
        return
    cards = ""
    for project in projects[:3]:
        reasons = project.get("matching_reasons") or []
        points = project.get("usage_points") or []
        cards += f"""
        <div class="ranking-card">
            <div class="document-meta-line">순위 {escape(str(project.get('rank', '')))}</div>
            <div class="document-title-line">{escape(project.get('project_name', '프로젝트명 확인 필요'))}</div>
            <div style="margin:0.55rem 0;"><span class="score-badge">유사도 {float(project.get('similarity_score') or 0.0):.4f}</span></div>
            <div class="document-meta-line">관련 문서: {escape(str(project.get('related_documents') or '확인 필요'))}</div>
            <div class="document-meta-line">관련 페이지: {escape(', '.join(str(page) for page in project.get('pages', [])[:8]) or '확인 필요')}</div>
            <div class="evidence-box" style="margin-top:0.65rem;">{escape(_trim_text(' / '.join(reasons), 180))}</div>
            <div class="document-meta-line" style="margin-top:0.55rem;">활용 포인트: {escape(_trim_text(' / '.join(points), 140))}</div>
        </div>
        """
    st.markdown(f'<div class="ranking-grid">{cards}</div>', unsafe_allow_html=True)


def _results_for_requirement(requirement: str, results) -> list:
    tokens = {token for token in re.split(r"\s+", requirement or "") if len(token) >= 2}
    if not tokens or requirement == "확인 필요":
        return list(results[:5])
    scored = []
    for result in results:
        haystack = " ".join([result.document_title, result.project_name, result.canonical_heading_path, result.matched_text])
        score = sum(1 for token in tokens if token in haystack)
        if score:
            scored.append((score, result))
    scored.sort(key=lambda item: (item[0], item[1].score), reverse=True)
    return [result for _, result in scored]


def _ensure_saved_search(repository: SearchRepository, parsed: ParsedNaturalQuery | None, results) -> str:
    saved_search_id = st.session_state.get("topic_saved_search_id", "")
    if saved_search_id:
        return saved_search_id
    query_text = parsed.original_query if parsed else ""
    parsed_json = json.dumps(asdict(parsed), ensure_ascii=False) if parsed else "{}"
    saved_search_id = repository.save_search(query_text, parsed_json, len(results))
    st.session_state["topic_saved_search_id"] = saved_search_id
    return saved_search_id


def _render_natural_search_results(
    results,
    root_folders: tuple[str, ...],
    parsed: ParsedNaturalQuery | None,
    structured_rows: list[dict] | None,
    evidence_rows: list[dict] | None,
    repository: SearchRepository,
    disabled: bool = False,
    key_prefix: str = "topic",
) -> None:
    if not results:
        st.info("검색 결과가 없습니다.")
        return
    if parsed:
        _render_natural_query_analysis(parsed)
    structured_rows = structured_rows if structured_rows is not None else (build_structured_rows(results, parsed) if parsed else [])
    evidence_rows = evidence_rows if evidence_rows is not None else (build_evidence_rows(results, parsed) if parsed else [])
    metrics = _result_metrics(results)
    _render_kpi_cards(metrics)

    save_cols = st.columns([1.15, 1.15, 1.15, 4])
    if save_cols[0].button("검색 결과 저장", disabled=disabled, key=f"{key_prefix}_save_search"):
        saved_id = _ensure_saved_search(repository, parsed, results)
        st.success(f"검색 결과를 저장했습니다: {saved_id}")
    with save_cols[1]:
        _download_excel(structured_rows, "요약 Excel", "search_summary", f"{key_prefix}_summary_xlsx")
    with save_cols[2]:
        _download_excel(evidence_rows, "근거 Excel", "evidence_matrix", f"{key_prefix}_evidence_xlsx")

    tab_summary, tab_docs, tab_evidence, tab_distribution = st.tabs(["구조화 요약", "관련 문서/페이지", "근거 문장", "문서영역 분포"])
    with tab_summary:
        if structured_rows:
            st.dataframe(pd.DataFrame(structured_rows), width="stretch", hide_index=True)
        else:
            st.info("구조화 요약으로 표시할 결과가 없습니다.")
    with tab_docs:
        _render_topic_results(results, root_folders, disabled=disabled, key_prefix=key_prefix)
    with tab_evidence:
        if evidence_rows:
            for result in results[:20]:
                with st.container(border=True):
                    matched = result.matched_keywords or [keyword.strip() for keyword in str(result.domain_keywords).split(",") if keyword.strip()]
                    st.markdown(
                        f"""
                        <div class="document-title-line">{escape(result.document_title)}</div>
                        <div class="document-meta-line">
                            프로젝트: {escape(result.project_name or "확인 필요")} · 고객사: {escape(result.client_name or "확인 필요")} ·
                            페이지: {escape(str(result.display_page or result.page_no))} · 문서영역: {escape(document_area(result))}
                        </div>
                        <div style="margin-top:0.55rem;">{_chips(matched, limit=10)}</div>
                        <div class="evidence-box" style="margin-top:0.65rem;">{escape(result.matched_text or "근거 문장 확인 필요")}</div>
                        """,
                        unsafe_allow_html=True,
                    )
                    col_preview, col_save, _ = st.columns([1, 1, 4])
                    if col_preview.button("미리보기", key=f"{key_prefix}_evidence_preview_{result.chunk_id}", disabled=disabled):
                        _request_preview(result)
                    if col_save.button("근거 저장", key=f"{key_prefix}_evidence_save_{result.chunk_id}", disabled=disabled):
                        saved_id = _ensure_saved_search(repository, parsed, results)
                        evidence_id = repository.save_evidence(saved_id, result)
                        st.success(f"근거를 저장했습니다: {evidence_id}")
            with st.expander("근거 매트릭스 표로 보기", expanded=False):
                st.dataframe(pd.DataFrame(evidence_rows), width="stretch", hide_index=True)
        else:
            st.info("표시할 근거 문장이 없습니다.")
    with tab_distribution:
        rows = _area_distribution_rows(results)
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("문서영역 분포를 만들 수 없습니다.")


def _render_print_blocker() -> None:
    st.markdown(
        """
        <style>
        @media print {
            body * {
                visibility: hidden !important;
            }
            body::before {
                content: "미리보기 화면에서는 문서 인쇄를 사용할 수 없습니다.";
                visibility: visible !important;
                display: block;
                margin: 4rem;
                font-size: 18px;
                font-weight: 700;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def _get_repository(config):
    db = Database(config.database_path)
    db.initialize()
    repository = SearchRepository(db)
    return db, repository


@st.cache_resource(show_spinner=False)
def _get_search_service(config):
    _, repository = _get_repository(config)
    return SearchService(config, repository)


@st.cache_resource(show_spinner=False)
def _get_rfp_service(config):
    _, repository = _get_repository(config)
    return RfpSearchService(config, repository, _get_search_service(config))


@st.cache_resource(show_spinner=False)
def _get_index_service(config):
    _, repository = _get_repository(config)
    return IndexManagementService(config, repository, _get_search_service(config))


@st.cache_resource(show_spinner=False)
def _get_download_service(config):
    return DownloadService(config)


@st.cache_resource(show_spinner=False)
def _get_preview_service(config):
    return PreviewService(config)


def _download_url(file_path: str) -> str:
    config = load_config()
    return _get_download_service(config).url_for(file_path)


def _render_download_button(file_path: str, key: str, label: str = "다운로드") -> None:
    path = Path(file_path)
    if not path.exists():
        st.error("다운로드할 파일을 찾을 수 없습니다.")
        return
    try:
        st.link_button(label, _download_url(file_path), key=key, width="stretch")
    except PermissionError:
        st.error("허용된 색인 루트 외부 파일은 다운로드할 수 없습니다.")
    except Exception as exc:
        st.error(f"다운로드 파일을 준비할 수 없습니다: {exc}")


def _preview_identity(request: dict) -> str:
    raw = f"{request.get('chunk_id', '')}:{request.get('file_path', '')}:{request.get('page_no', '')}"
    import hashlib

    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _preview_zoom_key(request: dict) -> str:
    return f"preview_zoom_{_preview_identity(request)}"


def _render_preview_toolbar(request: dict) -> float:
    zoom_key = _preview_zoom_key(request)
    st.session_state.setdefault(zoom_key, 1.0)
    zoom = float(st.session_state[zoom_key])
    cols = st.columns([0.9, 0.9, 0.9, 4.2])
    if cols[0].button("축소", key=f"{zoom_key}_out", disabled=zoom <= 1.0, width="stretch"):
        st.session_state[zoom_key] = max(1.0, round(zoom - 0.25, 2))
        st.rerun()
    if cols[1].button("맞춤", key=f"{zoom_key}_fit", width="stretch"):
        st.session_state[zoom_key] = 1.0
        st.rerun()
    if cols[2].button("확대", key=f"{zoom_key}_in", disabled=zoom >= 2.5, width="stretch"):
        st.session_state[zoom_key] = min(2.5, round(zoom + 0.25, 2))
        st.rerun()
    cols[3].caption(f"현재 배율 {int(zoom * 100)}%")
    return zoom


def _render_page_image(image_bytes: bytes, request: dict, alt_text: str) -> None:
    zoom = _render_preview_toolbar(request)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    viewer_id = f"preview_viewer_{_preview_identity(request)}"
    image_width = "auto" if zoom <= 1.0 else f"{int(zoom * 100)}%"
    image_max_width = "100%" if zoom <= 1.0 else "none"
    image_max_height = "calc(100% - 32px)" if zoom <= 1.0 else "none"
    align_items = "center" if zoom <= 1.0 else "flex-start"
    justify_content = "center" if zoom <= 1.0 else "flex-start"
    image_margin = "auto" if zoom <= 1.0 else "0 auto"
    st.html(
        f"""
        <div id="{viewer_id}" class="preview-viewer">
            <div class="preview-stage">
                <img alt="{escape(alt_text)}" src="data:image/png;base64,{encoded}" draggable="false" />
            </div>
        </div>
        <style>
            .preview-viewer {{
                height: 674px;
                overflow: auto;
                background: #2b2d31;
                border-radius: 6px;
                cursor: grab;
                scrollbar-gutter: stable both-edges;
                user-select: none;
            }}
            .preview-viewer.dragging {{ cursor: grabbing; }}
            .preview-stage {{
                min-width: 100%;
                min-height: 100%;
                box-sizing: border-box;
                padding: 16px;
                display: flex;
                align-items: {align_items};
                justify-content: {justify_content};
            }}
            .preview-stage img {{
                display: block;
                width: {image_width};
                max-width: {image_max_width};
                max-height: {image_max_height};
                height: auto;
                object-fit: contain;
                margin: {image_margin};
                background: #ffffff;
                box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
                pointer-events: none;
            }}
        </style>
        <script>
            const viewer = document.getElementById("{viewer_id}");
            let dragging = false;
            let startX = 0;
            let startY = 0;
            let scrollLeft = 0;
            let scrollTop = 0;
            viewer.addEventListener("mousedown", (event) => {{
                dragging = true;
                viewer.classList.add("dragging");
                startX = event.clientX;
                startY = event.clientY;
                scrollLeft = viewer.scrollLeft;
                scrollTop = viewer.scrollTop;
                event.preventDefault();
            }});
            window.addEventListener("mouseup", () => {{
                dragging = false;
                viewer.classList.remove("dragging");
            }});
            window.addEventListener("mousemove", (event) => {{
                if (!dragging) return;
                viewer.scrollLeft = scrollLeft - (event.clientX - startX);
                viewer.scrollTop = scrollTop - (event.clientY - startY);
            }});
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def _render_text_preview(text: str, empty_message: str) -> None:
    if text:
        st.markdown(
            f"""
            <div style="border:1px solid #d9dce3;border-radius:6px;padding:1rem;min-height:320px;background:#fff;">
                <pre style="white-space:pre-wrap;font-family:inherit;font-size:0.95rem;line-height:1.55;margin:0;">{escape(text)}</pre>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info(empty_message)


def _render_preview_result(result: PreviewResult, request: dict) -> None:
    if result.warning:
        st.warning(result.warning)
    if result.kind == "image":
        _render_page_image(result.content if isinstance(result.content, bytes) else b"", request, request.get("document_title", "preview"))
    else:
        _render_text_preview(str(result.content or ""), "이 페이지에서 표시할 텍스트를 찾지 못했습니다.")


def _render_preview_body(request: dict) -> None:
    file_path = request["file_path"]
    path = Path(file_path)
    display_page = request.get("display_page") or str(request.get("page_no", ""))
    metadata = [
        ("프로젝트", request.get("project_name", "") or "확인 필요"),
        ("고객사", request.get("client_name", "") or "확인 필요"),
        ("표시 페이지", str(display_page or "확인 필요")),
        ("물리 페이지", str(request.get("page_no", "") or "확인 필요")),
        ("문서영역", request.get("canonical_heading_path", "") or "확인 필요"),
        ("매칭 키워드", request.get("matched_keywords", "") or "확인 필요"),
    ]
    metadata_html = "".join(
        f"""
        <div class="intent-item">
            <div class="intent-label">{escape(label)}</div>
            <div class="intent-value" style="font-size:0.92rem;">{escape(value)}</div>
        </div>
        """
        for label, value in metadata
    )
    st.markdown(
        f"""
        <div class="intent-card">
            <div class="document-title-line">{escape(request.get('document_title', path.name))}</div>
            <div class="intent-grid" style="margin-top:0.85rem;">{metadata_html}</div>
            <div class="document-meta-line" style="margin-top:0.75rem;">원본경로: {escape(request.get('raw_heading_path', '') or '확인 필요')}</div>
            <div class="evidence-note" style="margin-top:0.75rem;">{escape((request.get('matched_text') or '근거 문장 확인 필요')[:260])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not path.exists():
        st.error("파일을 찾을 수 없습니다.")
        return

    try:
        preview = _get_preview_service(load_config()).render(
            file_path,
            request_page_no(request.get("page_no")),
            matched_text=request.get("matched_text", ""),
        )
        if path.suffix.lower() == ".pdf":
            st.caption(f"{display_page} 페이지 / 전체 {preview.total_pages}쪽 - {preview.renderer} 렌더러")
        elif path.suffix.lower() in {".ppt", ".pptx"}:
            st.caption(f"슬라이드 {request_page_no(request.get('page_no'))} / 전체 {preview.total_pages}장 - {preview.renderer} 렌더러")
        _render_preview_result(preview, request)
    except Exception as exc:
        st.error(f"미리보기를 만들 수 없습니다: {exc}")


def _clear_preview_request() -> None:
    st.session_state["preview_request"] = None


@st.dialog("문서 미리보기", width="large", on_dismiss=_clear_preview_request)
def _render_preview_dialog(request: dict) -> None:
    file_path = request.get("file_path", "")
    _render_preview_body(request)
    col_download, col_close = st.columns([1, 1])
    with col_download:
        _render_download_button(file_path, f"preview_download_{request.get('chunk_id', file_path)}")
    if col_close.button("닫기", width="stretch"):
        _clear_preview_request()
        st.rerun()


def _preview_request(result) -> dict:
    return preview_request(result)


def _request_preview(result) -> None:
    st.session_state["preview_request"] = _preview_request(result)


def _render_result_actions(result, root_folders: tuple[str, ...], disabled: bool, key_prefix: str = "topic") -> None:
    page_label = result.display_page or str(result.page_no)
    cols = st.columns([1.3, 6.0, 1.4])
    cols[0].markdown(f"**p.{escape(str(page_label))}**")
    heading = document_area(result)
    cols[1].caption(f"{heading} | {result.matched_text[:180]}")
    if cols[2].button("미리보기", key=f"{key_prefix}_preview_{result.chunk_id}", disabled=disabled, width="stretch"):
        _request_preview(result)


def _prefetch_preview_results(results) -> None:
    preview_service = _get_preview_service(load_config())
    submitted = 0
    seen: set[tuple[str, int]] = set()
    for result in results:
        if submitted >= PREVIEW_PREFETCH_LIMIT:
            break
        suffix = Path(result.file_path).suffix.lower()
        if suffix not in {".ppt", ".pptx"}:
            continue
        page_no = max(int(result.page_no or 1), 1)
        key = (result.file_path, page_no)
        if key in seen:
            continue
        seen.add(key)
        preview_service.prefetch(result.file_path, page_no)
        submitted += 1


def _render_topic_results(results, root_folders: tuple[str, ...], disabled: bool = False, key_prefix: str = "topic") -> None:
    if not results:
        st.info(
            "검색 결과가 없습니다. 검색어를 더 일반적인 기술 용어로 바꾸거나, 챕터 필터와 문서유형을 전체로 조정해 보세요. "
            "계속 결과가 없으면 관리자 도구에서 색인 상태와 메타데이터 검증을 확인하세요."
        )
        return
    _prefetch_preview_results(results)
    for group in _document_groups(results):
        representative = group["results"][0] if group["results"] else None
        if representative is None:
            continue
        with st.container(border=True):
            group_pages = sorted({result.display_page or str(result.page_no) for result in group["results"]})
            group_areas = _area_distribution_rows(group["results"])
            representative_area = group_areas[0]["문서영역"] if group_areas else "확인 필요"
            representative_keywords = group_areas[0]["대표 키워드"] if group_areas else ""
            keyword_values = [keyword.strip() for keyword in representative_keywords.split(",") if keyword.strip()]
            evidence = representative.matched_text or "근거 문장 확인 필요"
            st.markdown(
                f"""
                <div class="document-card-head">
                    <div class="document-icon">{_icon('document')}</div>
                    <div>
                        <div class="document-title-line">{escape(group['document_title'] or "문서명 확인 필요")}</div>
                        <div class="document-meta-line">
                            프로젝트: {escape(group['project_name'] or "확인 필요")} ·
                            고객사: {escape(group['client_name'] or "확인 필요")} ·
                            문서유형: {escape(getattr(representative, "document_type", "") or "확인 필요")}
                        </div>
                    </div>
                    <div><span class="score-badge">score {group['score']:.4f}</span></div>
                </div>
                <div class="document-meta-line" style="margin-top:0.75rem;">매칭 페이지: {escape(', '.join(group_pages[:12]) or "확인 필요")}</div>
                <div class="document-meta-line">대표 문서영역: {escape(representative_area)}</div>
                <div style="margin-top:0.45rem;">{_chips(keyword_values, limit=8)}</div>
                <div class="evidence-box" style="margin-top:0.65rem;">{escape(evidence[:320])}</div>
                """,
                unsafe_allow_html=True,
            )
            action_cols = st.columns([1, 1, 1, 4])
            if action_cols[0].button("미리보기", key=f"{key_prefix}_doc_preview_{representative.chunk_id}", disabled=disabled, width="stretch"):
                _request_preview(representative)
            with action_cols[1]:
                _render_download_button(group["file_path"], f"{key_prefix}_download_{group['document_id']}", "다운로드")
            detail_key = f"{key_prefix}_detail_open_{group['document_id']}"
            if action_cols[2].button("상세 보기", key=f"{detail_key}_button", disabled=disabled, width="stretch"):
                st.session_state[detail_key] = not bool(st.session_state.get(detail_key, False))
            if st.session_state.get(detail_key):
                with st.expander("상세 페이지/섹션 보기", expanded=True):
                    st.dataframe(pd.DataFrame(_result_rows(group["results"])), width="stretch", hide_index=True)
                    st.markdown("**페이지별 결과**")
                    for result in group["results"]:
                        _render_result_actions(result, root_folders, disabled, key_prefix)


def _run_pending_topic_search(search_service: SearchService, repository: SearchRepository, root_folders: tuple[str, ...]) -> None:
    task = st.session_state.get("pending_topic_search")
    if not task:
        return

    progress = st.progress(0, text="검색 조건 분석 중")
    try:
        progress.progress(20, text="검색 조건 분석 중")
        parsed_natural = task.get("natural_query") or _analyze_natural_query(task["query"])
        filters = dict(_filters_for_scope(task["scope"], root_folders) or {})
        semantic_query = task.get("semantic_query") or parsed_natural.semantic_query or task["query"]
        chapter_filter = task.get("chapter_filter", "")
        if chapter_filter:
            filters["chapter_filter"] = chapter_filter
        progress.progress(45, text="후보 문서 검색 중")
        requested_top_k = int(task["top_k"])
        candidate_top_k = max(requested_top_k * 3, requested_top_k + 20)
        try:
            candidates = search_service.search(semantic_query, top_k=candidate_top_k, filters=filters)
        except ChapterFilterNotFound:
            if task.get("chapter_filter_source") != "auto":
                raise
            filters.pop("chapter_filter", None)
            chapter_filter = ""
            candidates = search_service.search(semantic_query, top_k=candidate_top_k, filters=filters)
        results = rerank_results(parsed_natural, candidates, top_k=requested_top_k)
        progress.progress(72, text="관련도 재정렬 중")
        structured_rows = build_structured_rows(results, parsed_natural)
        evidence_rows = build_evidence_rows(results, parsed_natural)
        progress.progress(88, text="근거 문장 구성 중")
        repository.log_search(task["query"], "topic", len(results))
        st.session_state["topic_results"] = results
        st.session_state["topic_natural_query"] = parsed_natural
        st.session_state["topic_structured_rows"] = structured_rows
        st.session_state["topic_evidence_rows"] = evidence_rows
        st.session_state["topic_saved_search_id"] = ""
        st.session_state["topic_error"] = ""
        st.session_state["topic_search_info"] = {
            "detected_chapter": task.get("detected_chapter", ""),
            "manual_chapter": task.get("manual_chapter", AUTO_CHAPTER),
            "chapter_filter": chapter_filter,
            "semantic_query": semantic_query,
            "natural_query": asdict(parsed_natural),
            "metadata_ready": True,
            "suggestions": [],
        }
        progress.progress(100, text="검색 완료")
    except ChapterFilterNotFound as exc:
        suggestions = ", ".join(exc.suggestions) if exc.suggestions else "추천 가능한 챕터가 없습니다."
        st.session_state["topic_results"] = []
        st.session_state["topic_natural_query"] = task.get("natural_query")
        st.session_state["topic_structured_rows"] = None
        st.session_state["topic_evidence_rows"] = None
        st.session_state["topic_error"] = f"{exc} 추천 챕터: {suggestions}"
        st.session_state["topic_search_info"] = {
            "detected_chapter": task.get("detected_chapter", ""),
            "manual_chapter": task.get("manual_chapter", AUTO_CHAPTER),
            "chapter_filter": task.get("chapter_filter", ""),
            "semantic_query": task.get("semantic_query") or task["query"],
            "metadata_ready": exc.metadata_ready,
            "suggestions": exc.suggestions,
        }
    except Exception as exc:
        st.session_state["topic_results"] = []
        st.session_state["topic_structured_rows"] = None
        st.session_state["topic_evidence_rows"] = None
        st.session_state["topic_error"] = str(exc)
    finally:
        st.session_state["pending_topic_search"] = None
        st.session_state["search_running"] = False
        st.rerun()


def _run_pending_rfp_search(rfp_service: RfpSearchService, top_k: int) -> None:
    task = st.session_state.get("pending_rfp_search")
    if not task:
        return

    progress = st.progress(0, text="RFP 검색 준비 중입니다.")
    rfp_path = Path(task["path"])
    try:
        progress.progress(25, text="RFP 내용을 분석하는 중입니다.")
        response = rfp_service.search_similar(str(rfp_path), top_k=top_k)
        progress.progress(80, text="유사 산출물을 정렬하는 중입니다.")
        st.session_state["rfp_response"] = response
        st.session_state["rfp_error"] = ""
        progress.progress(100, text="검색 완료")
    except Exception as exc:
        st.session_state["rfp_response"] = None
        st.session_state["rfp_error"] = str(exc)
    finally:
        rfp_path.unlink(missing_ok=True)
        st.session_state["pending_rfp_search"] = None
        st.session_state["search_running"] = False
        st.rerun()


def _render_sidebar(config, repository: SearchRepository, search_running: bool) -> None:
    index_service = _get_index_service(config)
    with st.sidebar:
        st.markdown("### 관리자 도구")
        st.caption("색인, 검증, 문서영역 탐색, 검색품질 진단을 관리합니다.")
        with st.expander("관리자 도구 열기", expanded=False):
            st.markdown("**색인 관리**")
            root_folder_text = st.text_area("색인 루트 폴더", value="\n".join(config.root_folders), height=90)
            col_a, col_b = st.columns(2)
            rebuild = col_a.button("신규 색인", width="stretch", disabled=search_running)
            refresh = col_b.button("변경 파일 재색인", width="stretch", disabled=search_running)
            chapter_rebuild = st.button("챕터 메타데이터 포함 전체 재색인", width="stretch", disabled=search_running)
            st.caption(f"DB: {config.database_path}")

            if chapter_rebuild:
                rebuild = True

            if rebuild or refresh:
                root_folders = [line.strip() for line in root_folder_text.splitlines() if line.strip()]
                if not root_folders:
                    st.error("색인할 폴더 경로를 입력하세요.")
                else:
                    started = time.perf_counter()
                    action_label = "챕터 메타데이터 포함 전체 재색인" if chapter_rebuild else ("신규 색인" if rebuild else "변경 파일 재색인")
                    try:
                        with st.spinner("문서를 읽고 색인하는 중입니다. 기존 인덱스 백업 후 새 인덱스를 생성합니다."):
                            summary = index_service.rebuild(root_folders) if rebuild else index_service.refresh(root_folders)
                        elapsed = time.perf_counter() - started
                        message = (
                            f"{action_label} 완료: 프로젝트 {summary.project_count}개 "
                            f"문서 {summary.document_count}개 chunk {summary.chunk_count}개 "
                            f"({elapsed:.1f}초)"
                        )
                        st.session_state["index_status"] = {
                            "message": message,
                            "unsupported_count": len(summary.unsupported_files),
                            "backup_path": summary.backup_path,
                            "report_path": summary.report_path,
                            "validation": summary.validation,
                        }
                        st.session_state["index_validation"] = summary.validation
                        st.session_state["topic_results"] = None
                        st.session_state["topic_error"] = ""
                        st.success(message)
                        if summary.backup_path:
                            st.caption(f"백업 위치: {summary.backup_path}")
                        if summary.report_path:
                            st.caption(f"리포트: {summary.report_path}")
                        if summary.unsupported_files:
                            st.warning(f"미지원/실패 파일 {len(summary.unsupported_files)}개는 건너뛰었습니다.")
                        if summary.validation.get("reindex_required"):
                            st.warning("일부 chunk의 챕터 메타데이터 또는 인덱스 버전이 기준과 다릅니다. 리포트를 확인하세요.")
                    except Exception as exc:
                        st.session_state["index_status"] = {"message": f"{action_label} 실패: {exc}", "unsupported_count": 0}
                        st.error(f"{action_label} 실패: {exc}")

            if st.session_state.get("index_status") and not (rebuild or refresh):
                st.success(st.session_state["index_status"]["message"])
                unsupported_count = st.session_state["index_status"].get("unsupported_count", 0)
                if unsupported_count:
                    st.caption(f"건너뛴 파일: {unsupported_count}개")
                if st.session_state["index_status"].get("backup_path"):
                    st.caption(f"백업 위치: {st.session_state['index_status']['backup_path']}")
                if st.session_state["index_status"].get("report_path"):
                    st.caption(f"리포트: {st.session_state['index_status']['report_path']}")

            st.divider()
            st.markdown("**검증**")
            status_col, validate_col = st.columns(2)
            if status_col.button("색인 상태 보기", width="stretch", disabled=search_running):
                validation = index_service.validate()
                st.session_state["index_validation"] = validation
                st.json({"stats": index_service.stats(), "validation": validation})

            if validate_col.button("메타데이터 검증", width="stretch", disabled=search_running):
                validation = index_service.validate()
                st.session_state["index_validation"] = validation
                if validation.get("metadata_ready"):
                    st.success("챕터/섹션 메타데이터 검증이 통과했습니다.")
                else:
                    st.warning("현재 인덱스는 챕터/섹션 메타데이터 기준을 통과하지 못했습니다. 전체 재색인이 필요합니다.")
                st.json(validation)

            st.divider()
            st.markdown("**문서영역 탐색**")
            try:
                tree = repository.heading_tree()
            except Exception as exc:
                tree = []
                st.caption(f"문서영역을 불러올 수 없습니다: {exc}")
            labels = [""] + [
                f"{'  ' * max(node['level'] - 1, 0)}{node['label']} ({node['chunk_count']})"
                for node in tree[:200]
            ]
            raw_labels = [""] + [node["label"] for node in tree[:200]]
            current = st.session_state.get("selected_heading_filter", "")
            index = raw_labels.index(current) if current in raw_labels else 0
            selected = st.selectbox("영역 필터", labels, index=index, disabled=search_running)
            selected_index = labels.index(selected) if selected in labels else 0
            st.session_state["selected_heading_filter"] = raw_labels[selected_index] if selected_index else ""

            st.divider()
            st.markdown("**검색품질 진단**")
            st.caption("대표 질의 10개로 상위 검색 결과와 누락 키워드를 점검합니다.")
            if st.button("검색품질 진단 실행", width="stretch", disabled=search_running):
                try:
                    with st.spinner("테스트 질의로 검색품질 리포트를 생성하는 중입니다."):
                        report_path = run_search_quality_diagnostics(_get_search_service(config), config.data_dir)
                    st.success(f"검색품질 리포트 생성: {report_path}")
                except Exception as exc:
                    st.error(f"검색품질 진단 실패: {exc}")


def _render_topic_search(config, repository: SearchRepository, search_running: bool) -> None:
    _render_section_title("주제/키워드 검색", "자연어 질의로 제안서·보고서의 관련 문서, 페이지, 근거 문장을 탐색합니다.")
    with st.container(border=True):
        search_col, button_col = st.columns([5.4, 1])
        query = search_col.text_input(
            "자연어 검색어",
            placeholder="예: 목표모델에서 클라우드 전환 아키텍처 찾아줘",
            disabled=search_running,
        )
        search_clicked = button_col.button("검색", type="primary", disabled=search_running, width="stretch")

        parsed_query = parse_search_query(query)
        natural_query = _analyze_natural_query(query) if query.strip() else ParsedNaturalQuery(original_query="")
        detected_chapter = parsed_query.chapter_filter or natural_query.target_chapter

        top_k = config.search.top_k
        scope = SCOPE_ALL
        base_filters = _filters_for_scope(scope, config.root_folders)
        chapter_options = _chapter_options(repository, base_filters)
        selected_heading_filter = st.session_state.get("selected_heading_filter", "")
        if selected_heading_filter and selected_heading_filter not in chapter_options:
            chapter_options.append(selected_heading_filter)
        default_chapter_index = chapter_options.index(selected_heading_filter) if selected_heading_filter in chapter_options else 0
        manual_chapter = selected_heading_filter if selected_heading_filter else AUTO_CHAPTER
        with st.expander("고급 필터", expanded=False):
            col1, col2, col3 = st.columns([1, 1, 2])
            top_k = col1.number_input("결과 수", min_value=5, max_value=100, value=config.search.top_k, disabled=search_running)
            scope = col2.selectbox("문서유형", [SCOPE_ALL, SCOPE_PROPOSAL, SCOPE_REPORT], disabled=search_running)
            base_filters = _filters_for_scope(scope, config.root_folders)
            chapter_options = _chapter_options(repository, base_filters)
            if selected_heading_filter and selected_heading_filter not in chapter_options:
                chapter_options.append(selected_heading_filter)
            default_chapter_index = chapter_options.index(selected_heading_filter) if selected_heading_filter in chapter_options else 0
            manual_chapter = col3.selectbox("챕터 필터", chapter_options, index=default_chapter_index, disabled=search_running)
            st.caption(f"감지된 검색 범위: {detected_chapter or '전체'}")
        effective_chapter = _effective_chapter_filter(manual_chapter, detected_chapter)
        chapter_filter_source = "manual" if manual_chapter not in {AUTO_CHAPTER, ALL_CHAPTERS} else ("auto" if effective_chapter else "")
        st.markdown(
            f"""
            <div class="filter-summary">
                감지 범위: {escape(detected_chapter or "전체")} ·
                적용 필터: {escape(effective_chapter or "전체")} ·
                문서유형: {escape(scope)}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if effective_chapter:
            if not repository.has_heading_metadata(base_filters):
                st.warning("현재 인덱스에 챕터/섹션 메타데이터가 없습니다. 챕터 필터 검색을 사용하려면 재색인이 필요합니다.")

    if search_clicked:
        if not query.strip():
            st.error("검색어를 입력하세요.")
        else:
            st.session_state["pending_topic_search"] = {
                "query": query.strip(),
                "semantic_query": natural_query.semantic_query or parsed_query.effective_query,
                "natural_query": natural_query,
                "detected_chapter": detected_chapter,
                "manual_chapter": manual_chapter,
                "chapter_filter": effective_chapter,
                "chapter_filter_source": chapter_filter_source,
                "top_k": int(top_k),
                "scope": scope,
            }
            st.session_state["topic_results"] = None
            st.session_state["topic_natural_query"] = natural_query
            st.session_state["topic_structured_rows"] = None
            st.session_state["topic_evidence_rows"] = None
            st.session_state["topic_saved_search_id"] = ""
            st.session_state["topic_error"] = ""
            st.session_state["search_running"] = True
            st.rerun()

    if st.session_state.get("topic_search_info"):
        info = st.session_state["topic_search_info"]
        st.caption(f"최근 검색 주제: {info.get('semantic_query') or '-'}")
        st.caption(f"최근 적용 검색 범위: {info.get('chapter_filter') or '전체'}")
    if st.session_state.get("topic_error"):
        st.error(st.session_state["topic_error"])
    elif st.session_state.get("topic_results") is not None:
        _render_natural_search_results(
            st.session_state["topic_results"],
            config.root_folders,
            st.session_state.get("topic_natural_query"),
            st.session_state.get("topic_structured_rows"),
            st.session_state.get("topic_evidence_rows"),
            repository,
            disabled=search_running,
        )


def _render_rfp_search(config, search_running: bool) -> None:
    _render_section_title("신규 RFP 기반 검색", "RFP 요구사항을 분석하고 사내 유사 프로젝트 산출물과 근거 페이지를 매핑합니다.")
    _render_rfp_workflow(done=st.session_state.get("rfp_response") is not None)
    with st.container(border=True):
        uploaded = st.file_uploader("RFP 파일 업로드", type=["pdf", "docx", "pptx"], disabled=search_running)
        st.caption("업로드된 파일은 분석 후 임시 파일에서 삭제되며, 결과는 실제 추출값과 검색 결과 기반으로만 표시합니다.")
        if st.button("RFP 분석 및 유사 산출물 검색", type="primary", disabled=search_running):
            if uploaded is None:
                st.error("RFP 파일을 업로드하세요.")
            else:
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.getbuffer())
                    rfp_path = tmp.name
                st.session_state["pending_rfp_search"] = {"path": rfp_path}
                st.session_state["rfp_response"] = None
                st.session_state["rfp_error"] = ""
                st.session_state["search_running"] = True
                st.rerun()

    if st.session_state.get("rfp_error"):
        st.error(st.session_state["rfp_error"])
    elif st.session_state.get("rfp_response") is not None:
        response = st.session_state["rfp_response"]
        with st.container(border=True):
            _render_section_title("RFP 분석 요약", "업로드한 RFP에서 추출한 사업 정보와 요구사항입니다.")
            _render_rfp_summary(response.summary)
            with st.expander("원문 분석 데이터 보기", expanded=False):
                st.json(response.summary)
        with st.container(border=True):
            _render_section_title("유사 프로젝트 TOP", "요구사항과 키워드가 유사한 기존 프로젝트 후보입니다.")
            if response.similar_projects:
                _render_ranking_cards(response.similar_projects)
                rows = []
                for project in response.similar_projects:
                    rows.append(
                        {
                            "순위": project["rank"],
                            "프로젝트명": project["project_name"],
                            "유사도 점수": round(project["similarity_score"], 4),
                            "관련 문서": project["related_documents"],
                            "관련 페이지": project["pages"],
                            "매칭 이유": "\n".join(project["matching_reasons"]),
                            "활용 가능 포인트": "\n".join(project["usage_points"]),
                        }
                    )
                with st.expander("전체 프로젝트 표로 보기", expanded=False):
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            else:
                st.info("유사 프로젝트를 찾지 못했습니다.")
        with st.container(border=True):
            _render_section_title("요구사항별 관련 산출물", "RFP 요구사항과 매칭된 문서, 페이지, 활용 포인트를 정리합니다.")
            requirement_rows = _rfp_requirement_rows(response)
            st.caption("RFP 요구사항별로 기존 산출물의 문서명, 프로젝트명, 페이지, 근거 문장, 활용 가능 포인트를 매핑했습니다.")
            _download_excel(requirement_rows, "요구사항 매핑 Excel", "rfp_requirement_mapping", "rfp_requirement_xlsx")
            st.dataframe(pd.DataFrame(requirement_rows), width="stretch", hide_index=True)
        with st.container(border=True):
            _render_section_title("관련 문서/페이지 결과", "미리보기와 다운로드가 가능한 상세 검색 결과입니다.")
            if response.results:
                _render_topic_results(response.results, config.root_folders, disabled=search_running, key_prefix="rfp")
            else:
                st.info("관련 문서/페이지 결과가 없습니다.")


def main() -> None:
    config = load_config()
    st.set_page_config(page_title=config.ui.page_title, layout="wide")
    _init_session_state()
    _inject_theme()
    _render_print_blocker()
    search_running = bool(st.session_state["search_running"])
    if search_running:
        st.info("현재 검색 중입니다. 완료될 때까지 화면의 버튼을 비활성화합니다.")

    _, repository = _get_repository(config)
    _render_sidebar(config, repository, search_running)
    has_results = st.session_state.get("topic_results") is not None or st.session_state.get("rfp_response") is not None
    if has_results:
        _render_compact_header(config, repository)
    else:
        _render_hero(config, repository)
    mode = _render_mode_selector(search_running, show_description=not has_results)

    if mode == "주제/키워드 검색":
        _render_topic_search(config, repository, search_running)
    else:
        _render_rfp_search(config, search_running)

    if st.session_state.get("pending_topic_search"):
        _run_pending_topic_search(_get_search_service(config), repository, config.root_folders)
    if st.session_state.get("pending_rfp_search"):
        _run_pending_rfp_search(_get_rfp_service(config), config.search.top_k)
    if st.session_state.get("preview_request"):
        _render_preview_dialog(st.session_state["preview_request"])


if __name__ == "__main__":
    main()
