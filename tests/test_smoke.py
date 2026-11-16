from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_index_page_exists_and_is_html():
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "<title>" in html
    assert html.rstrip().endswith("</html>")
