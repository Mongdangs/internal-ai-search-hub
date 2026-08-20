import os

from src.indexing.document_dedup import canonical_document_key, newest_first, select_latest_versions


def test_select_latest_versions_keeps_newest_version(tmp_path):
    root = tmp_path
    project = root / "2025_테스트_클라우드전환"
    project.mkdir()
    old_file = project / "목표모델_v0.9.pptx"
    new_file = project / "목표모델_v1.0.pptx"
    old_file.write_text("old")
    new_file.write_text("new")
    os.utime(old_file, (100, 100))
    os.utime(new_file, (200, 200))

    files = select_latest_versions([old_file, new_file], root)

    assert files == [new_file]


def test_newest_first_keeps_all_files_in_latest_order(tmp_path):
    root = tmp_path
    old_file = root / "목표모델_v0.9.pptx"
    new_file = root / "목표모델_v1.0.pptx"
    old_file.write_text("old")
    new_file.write_text("new")
    os.utime(old_file, (100, 100))
    os.utime(new_file, (200, 200))

    assert newest_first([old_file, new_file]) == [new_file, old_file]


def test_canonical_document_key_removes_version_tokens(tmp_path):
    path = tmp_path / "프로젝트" / "종합보고서_Rev.1_v0.95_20250101.pptx"
    path.parent.mkdir()
    path.write_text("x")

    key = canonical_document_key(path, tmp_path)

    assert "rev" not in key
    assert "0.95" not in key
