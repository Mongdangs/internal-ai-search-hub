from src.utils.page_label import extract_display_page_label


def test_extract_display_page_label_from_footer_number():
    text = "표지\n본문 내용\n- 12 -"
    assert extract_display_page_label(text, fallback=3) == "12"


def test_extract_display_page_label_from_section_page():
    text = "본문 내용\nⅢ-67"
    assert extract_display_page_label(text, fallback=70) == "Ⅲ-67"


def test_extract_display_page_label_falls_back():
    assert extract_display_page_label("본문 내용", fallback=5) == "5"
