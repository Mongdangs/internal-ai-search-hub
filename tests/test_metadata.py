from pathlib import Path

from src.ingestion.metadata_extractor import MetadataExtractor, infer_document_type, parse_year_token


def test_infer_document_type():
    assert infer_document_type("사업_제안서.pdf") == "제안서"
    assert infer_document_type("신규_RFP.docx") == "RFP"
    assert infer_document_type("요구사항정의서.pptx") == "요구사항정의서"
    assert infer_document_type("memo.pdf") == "기타 산출물"


def test_project_metadata_from_folder():
    root = Path("D:/Projects")
    extractor = MetadataExtractor(root)
    project = extractor.project_for(root / "2025_KISTEP_범부처_RnD_통합플랫폼_ISMP" / "02_제안서" / "a.pdf")
    assert project.year == "2025"
    assert project.client_name == "KISTEP"
    assert "범부처" in project.project_name


def test_project_metadata_from_dated_folder():
    root = Path("H:/01.제안서")
    extractor = MetadataExtractor(root)
    project = extractor.project_for(root / "20210818_인천공항_원스톱 입주자서비스 플랫폼 설계 용역" / "a.pdf")
    assert project.year == "2021"
    assert project.client_name == "인천공항"
    assert project.project_name == "원스톱 입주자서비스 플랫폼 설계 용역"


def test_project_metadata_from_short_dated_folder():
    root = Path("H:/02.사업수행")
    extractor = MetadataExtractor(root)
    project = extractor.project_for(root / "210927_IIAC_ISMP" / "a.pdf")
    assert project.year == "2021"
    assert project.client_name == "IIAC"
    assert project.project_name == "ISMP"


def test_parse_year_token():
    assert parse_year_token("20210818") == "2021"
    assert parse_year_token("210927") == "2021"
    assert parse_year_token("2025") == "2025"
