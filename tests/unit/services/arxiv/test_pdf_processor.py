"""Unit tests for PDF processor helper extraction methods."""

from src.services.fetchers.arxiv.services.pdf_processor import PDFProcessor


def test_extract_equations_handles_multiple_latex_patterns() -> None:
    processor = PDFProcessor()
    text = """
    Inline $a+b=c$ and block \\[x=y\\].
    \\begin{equation}E=mc^2\\end{equation}
    """
    equations = processor._extract_equations(text)
    assert "a+b=c" in equations
    assert "x=y" in equations
    assert "E=mc^2" in equations


def test_extract_text_reads_text_field_directly() -> None:
    processor = PDFProcessor()
    assert processor._extract_text({"text": "hello"}) == "hello"


def test_extract_figures_supports_multiple_input_shapes() -> None:
    processor = PDFProcessor()
    doc_dict = {
        "pictures": [{"caption": "cap1", "page_no": 1}],
        "figures": [{"id": "f2", "caption": "cap2", "page_no": 2}],
        "elements": [{"type": "figure", "id": "f3", "caption": "cap3", "page_no": 3}],
    }
    figures = processor._extract_figures(doc_dict)
    assert len(figures) >= 3
