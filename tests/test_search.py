from src.indexing.keyword_index import keyword_overlap_score
from src.indexing.design_keywords import target_model_design_keywords
from src.indexing.document_dedup import content_similarity, document_signature
from src.indexing.vector_index import HashingEmbeddingProvider, cosine_similarity
from src.search.ranking import rank_chunk_ids
from src.utils.korean_tokenizer import tokenize


def test_keyword_overlap_score():
    score = keyword_overlap_score("클린룸 복구", "랜섬웨어 복구를 위한 Clean Room 클린룸 환경")
    assert score > 0


def test_target_model_design_keywords_prefer_technical_and_domain_terms():
    keywords = target_model_design_keywords(
        (
            "현황 내용보다 목표모델 설계, 목표 아키텍처, 클라우드 네이티브, MSA, "
            "API Gateway, 컨테이너 기반 서비스 연계를 정의한다. ISP ISMP. BPR"
        ),
        context="H:/02.사업수행/재난안전 통합플랫폼/목표모델 보고서.pptx",
    )

    assert "클라우드네이티브" in keywords[:5]
    assert "MSA" in keywords[:5]
    assert "API Gateway" in keywords[:6]
    assert "컨테이너" in keywords[:8]
    assert "재난안전" in keywords
    assert "통합플랫폼" in keywords
    assert "목표모델" not in keywords
    assert "목표아키텍처" not in keywords
    assert "설계" not in keywords
    assert "isp" not in [keyword.lower().strip(".") for keyword in keywords]
    assert "ismp" not in [keyword.lower().strip(".") for keyword in keywords]
    assert "bpr" not in [keyword.lower().strip(".") for keyword in keywords]


def test_target_model_design_keywords_remove_common_internal_terms():
    keywords = target_model_design_keywords(
        (
            "분석보고서 IIAC 성과물 제출 발전법 주요내용 종합보고서 Rev 버전관리 번호 "
            "ISPISMP 원본 제안사 일반현황 클라우드 MSA 데이터 모델"
        )
    )

    lowered = {keyword.lower().replace(" ", "") for keyword in keywords}
    assert "클라우드" in keywords
    assert "MSA" in keywords
    assert "분석보고서" not in lowered
    assert "iiac" not in lowered
    assert "성과물" not in lowered
    assert "ispismp" not in lowered
    assert "원본제안사" not in lowered
    assert "일반현황" not in lowered


def test_document_signature_detects_near_duplicate_content():
    base = "클라우드 네이티브 MSA API Gateway 컨테이너 데이터 모델 인터페이스 연계 " * 20
    revised = base + "추가 보완 내용"

    assert content_similarity(document_signature(base), document_signature(revised)) >= 0.8


def test_korean_suffix_normalization():
    assert tokenize("클린룸 복구와 관련된 산출물 찾아줘") == ["클린룸", "복구"]


def test_rnd_query_expands_to_research_terms():
    tokens = tokenize("AI 기반 R&D")

    assert "ai" in tokens
    assert "인공지능" in tokens
    assert "rnd" in tokens
    assert "연구개발" in tokens
    assert "연구" in tokens


def test_long_project_name_is_not_used_as_keyword():
    keywords = target_model_design_keywords(
        "AI 기반 연구개발 통합 플랫폼의 데이터 모델과 API 연계를 설계한다.",
        context="H:/01.제안서/20260511_한국도로공사_전사 데이터거버넌스 고도화 컨설팅 및 데이터·AI 플랫폼 ISMP/제안서.pdf",
    )

    assert "전사데이터거버넌스고도화컨설팅및데이터" not in keywords
    assert "플랫폼ismp" not in [keyword.lower() for keyword in keywords]
    assert "설계한다" not in keywords
    assert "연구개발" in keywords


def test_broken_rnd_project_fragment_is_not_used_as_keyword():
    keywords = target_model_design_keywords(
        "IRIS 데이터 플랫폼 기능과 연구개발 업무 연계를 설계한다.",
        context="H:/01.제안서/20250819_한국과학기술기획평가원_데이터 중심 범부처 R&D 통합 플랫폼 구축 ISMP/정성제안_KISTEP.pdf",
    )

    assert "데이터중심범부처r" not in [keyword.lower() for keyword in keywords]
    assert "통합플랫폼구축ismp" not in [keyword.lower() for keyword in keywords]
    assert "중심" not in keywords
    assert "구축" not in keywords
    assert "iris" not in keywords
    assert "정성제안" not in keywords
    assert "kistep" not in [keyword.lower() for keyword in keywords]
    assert "IRIS" in keywords
    assert "AI" in target_model_design_keywords("AI 기반 데이터 분석 플랫폼")
    assert "연구개발" in keywords


def test_hash_embedding_cosine_similarity():
    provider = HashingEmbeddingProvider(dimensions=64)
    left = provider.embed_text("AI 검색 데이터 플랫폼")
    right = provider.embed_text("데이터 플랫폼 기반 AI 검색 서비스")
    unrelated = provider.embed_text("회의록 일정 공유")
    assert cosine_similarity(left, right) > cosine_similarity(left, unrelated)


def test_hash_vector_only_results_can_be_blocked():
    ranked = rank_chunk_ids(
        keyword_scores={"keyword_hit": 0.5},
        vector_scores={"vector_only": 1.0, "keyword_hit": 0.2},
        keyword_weight=0.4,
        vector_weight=0.6,
        top_k=10,
        allow_vector_only=False,
    )
    assert [row[0] for row in ranked] == ["keyword_hit"]
