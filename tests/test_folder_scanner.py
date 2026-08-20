from src.ingestion.folder_scanner import FolderScanner


def test_folder_scanner_skips_old_folders_case_insensitive(tmp_path):
    keep_dir = tmp_path / "keep"
    mixed_case_old_dir = tmp_path / "Old"
    numbered_old_dir = tmp_path / "00.old"
    reference_dir = tmp_path / "참고자료"
    reference_use_dir = tmp_path / "참고용 자료"
    cross_reference_dir = tmp_path / "01.참조자료"
    reference_summary_dir = tmp_path / "참조 요약서"
    embedded_reference_dir = tmp_path / "벤치마킹 참고"
    numbered_reference_dir = tmp_path / "99.참고"
    customer_material_dir = tmp_path / "00.고객제공자료"
    admin_material_dir = tmp_path / "10 사업관리" / "04.공문"
    evidence_dir = tmp_path / "40.증빙서류"
    contract_dir = tmp_path / "50.계약(CM)" / "CM30.SW개발완료보고"
    temp_dir = tmp_path / "00 TEMP"
    keep_dir.mkdir()
    mixed_case_old_dir.mkdir()
    numbered_old_dir.mkdir()
    reference_dir.mkdir()
    reference_use_dir.mkdir()
    cross_reference_dir.mkdir()
    reference_summary_dir.mkdir()
    embedded_reference_dir.mkdir()
    numbered_reference_dir.mkdir()
    customer_material_dir.mkdir(parents=True)
    admin_material_dir.mkdir(parents=True)
    evidence_dir.mkdir()
    contract_dir.mkdir(parents=True)
    temp_dir.mkdir()

    keep_file = keep_dir / "report.pdf"
    mixed_case_old_file = mixed_case_old_dir / "proposal.pptx"
    numbered_old_file = numbered_old_dir / "minutes.pdf"
    reference_file = reference_dir / "reference.pdf"
    reference_use_file = reference_use_dir / "reference_use.pdf"
    cross_reference_file = cross_reference_dir / "cross_reference.pdf"
    reference_summary_file = reference_summary_dir / "reference_summary.pptx"
    embedded_reference_file = embedded_reference_dir / "benchmark.pdf"
    numbered_reference_file = numbered_reference_dir / "numbered_reference.pdf"
    customer_material_file = customer_material_dir / "customer_material.pdf"
    admin_material_file = admin_material_dir / "letter.pdf"
    evidence_file = evidence_dir / "신용평가등급확인서.pdf"
    contract_file = contract_dir / "상용SW 라이선스 하자보증.pdf"
    temp_file = temp_dir / "temp_design.pdf"
    unsupported_file = keep_dir / "notes.docx"

    keep_file.write_text("keep")
    mixed_case_old_file.write_text("skip")
    numbered_old_file.write_text("skip")
    reference_file.write_text("skip")
    reference_use_file.write_text("skip")
    cross_reference_file.write_text("skip")
    reference_summary_file.write_text("skip")
    embedded_reference_file.write_text("skip")
    numbered_reference_file.write_text("skip")
    customer_material_file.write_text("skip")
    admin_material_file.write_text("skip")
    evidence_file.write_text("skip")
    contract_file.write_text("skip")
    temp_file.write_text("skip")
    unsupported_file.write_text("skip")

    files = FolderScanner((".pdf", ".ppt", ".pptx")).scan(tmp_path)

    assert keep_file in files
    assert mixed_case_old_file not in files
    assert numbered_old_file not in files
    assert reference_file not in files
    assert reference_use_file not in files
    assert cross_reference_file not in files
    assert reference_summary_file not in files
    assert embedded_reference_file not in files
    assert numbered_reference_file not in files
    assert customer_material_file not in files
    assert admin_material_file not in files
    assert evidence_file not in files
    assert contract_file not in files
    assert temp_file not in files
    assert unsupported_file not in files


def test_folder_scanner_can_include_reference_materials(tmp_path):
    reference_dir = tmp_path / "참고자료"
    reference_dir.mkdir()
    reference_file = reference_dir / "reference.pdf"
    reference_file.write_text("keep when configured")

    default_files = FolderScanner((".pdf",)).scan(tmp_path)
    included_files = FolderScanner((".pdf",), exclude_reference_materials=False).scan(tmp_path)

    assert reference_file not in default_files
    assert reference_file in included_files
