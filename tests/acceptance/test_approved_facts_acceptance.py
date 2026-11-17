"""Acceptance tests: the offer page (docs/index.html) carries only the OWNER-approved facts."""
import os, re, subprocess, sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE, FACTS = ROOT / "docs" / "index.html", ROOT / "content" / "approved_facts.md"
PLACEHOLDER = "TO BE PROVIDED BY OWNER"
SECTION_IDS = ["hero", "product-facts", "audience", "pricing", "faq", "contact"]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
SKIP = {"head", "script", "style", "template", "noscript"}
BLOCKS = ("li", "p", "dt", "dd", "td", "tr", "div", "summary")
NUM = r"\d+(?:[.,]\d+)?"

class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.kids = tag, {k: v or "" for k, v in attrs}, parent, []
    def text(self):
        parts = [k if isinstance(k, str) else k.text() for k in self.kids if isinstance(k, str) or k.tag not in SKIP]
        return " ".join(" ".join(parts).split())
    def all(self, *tags):
        for k in (k for k in self.kids if isinstance(k, Node)):
            if not tags or k.tag in tags:
                yield k
            yield from k.all(*tags)

class Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node("#doc", [])
    def handle_starttag(self, tag, attrs):
        self.cur.kids.append(Node(tag, attrs, self.cur))
        self.cur = self.cur if tag in VOID else self.cur.kids[-1]
    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        self.cur = node.parent if node is not self.root else self.cur
    def handle_data(self, data):
        self.cur.kids.append(data)

def _raw():
    return PAGE.read_text(encoding="utf-8")

def _tree():
    b = Builder()
    b.feed(_raw())
    return b.root

def _section(sid):
    found = [n for n in _tree().all() if n.attrs.get("id") == sid]
    assert len(found) == 1, f'expected one element with id="{sid}"'
    return found[0]

def _approved_page():
    assert PLACEHOLDER not in _section("product-facts").text(), "approved product facts not on the page yet"
    return _tree()

def _metas(root):
    return {m.attrs.get("name") or m.attrs.get("property"): m.attrs.get("content", "") for m in root.all("meta")}

def _has(text, *patterns):
    for p in patterns:
        assert re.search(p, text, re.IGNORECASE), f"missing {p!r} in: {text[:300]}"

def test_sections_order_and_document_basics_kept():
    """With approved content in place, the six section ids keep their order and there is one h1, a title and a meta charset."""
    root = _approved_page()
    assert [n.attrs.get("id") for n in root.all("section") if n.attrs.get("id") in SECTION_IDS] == SECTION_IDS
    assert len(list(root.all("h1"))) == 1 and len(list(root.all("title"))) == 1
    assert any("charset" in m.attrs for m in root.all("meta"))

def test_existing_acceptance_tests_still_pass():
    """With approved content in place, all existing acceptance test files are still present and pass unchanged."""
    _approved_page()
    paths = [ROOT / "tests" / "acceptance" / f"test_{n}_acceptance.py" for n in ("offer_page", "pricing_faq", "seo_metadata")]
    assert all(p.is_file() for p in paths), "an existing acceptance test file is missing"
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *map(str, paths)], cwd=ROOT,
                       capture_output=True, text=True, timeout=240, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]

def test_page_adds_no_claims_beyond_approved_facts():
    """Every number on the page appears in the approved facts and no unapproved claims (certified, eco, best...) are made."""
    root = _approved_page()
    text = " ".join([root.text(), _metas(root).get("description", ""), _metas(root).get("og:description", "")])
    extra = sorted(set(re.findall(NUM, text)) - set(re.findall(NUM, FACTS.read_text(encoding="utf-8"))))
    assert not extra, f"numbers not in approved facts: {extra}"
    bad = r"certif|organic|non-?toxic|\beco\b|eco-friendly|vegan|natural|guarantee|\bbest\b|cheapest|award|premium"
    assert not re.search(bad, text, re.IGNORECASE), re.search(bad, text, re.IGNORECASE)

def test_product_facts_list_wax_colors_unscented_and_wick_life():
    """The product facts say it is granulated candle sand wax in white, colored and full-color black, unscented, one wick about 15 hours."""
    _has(_section("product-facts").text(), r"granulated", r"candle sand", r"wax", r"\bwhite\b", r"\bcolored\b",
         r"full-color black", r"unscented", r"\bwick\b", r"15 hours")

def test_product_facts_describe_black_sand():
    """The product facts say the black sand is fully reprocessed, does not stain and has no artificial dye smell."""
    _has(_section("product-facts").text(), r"black", r"fully reprocessed", r"not stain", r"no artificial dye smell")

def test_audience_offers_wholesale_to_resellers_and_decoration_or_events():
    """The audience section says wholesale and bulk are offered to resellers and for decoration or events."""
    _has(_section("audience").text(), r"wholesale", r"bulk", r"resell", r"decoration|events?\b")

def test_pricing_lists_four_approved_pack_formats():
    """The pricing section lists 500 g with 10 wicks, 750 g with 20 wicks, 1.5 kg with 20 wicks and 3 kg with 50 wicks."""
    blocks = [b.text() for b in _section("pricing").all(*BLOCKS)]
    for size, wicks in [(r"\b500\s?g\b", r"\b10 wicks"), (r"\b750\s?g\b", r"\b20 wicks"),
                        (r"\b1\.5\s?kg\b", r"\b20 wicks"), (r"(?<![.\d])3\s?kg\b", r"\b50 wicks")]:
        assert any(re.search(size, b) and re.search(wicks, b) for b in blocks), f"missing pack {size} / {wicks}"

def test_pricing_keeps_wholesale_price_and_moq_placeholders():
    """The pricing section keeps marked "TO BE PROVIDED BY OWNER" placeholders for wholesale prices and minimum order quantity."""
    blocks = [b.text() for b in _section("pricing").all(*BLOCKS)]
    for label in (r"wholesale price", r"minimum order|\bMOQ\b"):
        assert any(re.search(label, b, re.IGNORECASE) and PLACEHOLDER in b for b in blocks), f"no {label} placeholder"

def test_no_retail_price_discount_percent_or_currency():
    """With approved content in place, no retail price, discount, percent sign or currency symbol appears anywhere on the page."""
    _approved_page()
    raw = _raw()
    assert not re.search(r"retail\s+pric|discount|%|[€$£¥]|\b(EUR|USD|GBP)\b", raw, re.IGNORECASE)
    assert not re.search(r"&(euro|pound|dollar|yen|curren|percnt);|&#(8364|36|163|165|37);|&#x(20ac|24|a3|a5|25);",
                         raw, re.IGNORECASE)

def test_faq_has_three_approved_questions_and_answers():
    """The FAQ has exactly three questions (how it works, which container, how to ask for wholesale) with approved answers."""
    faq = _section("faq")
    qs = next((q for q in (list(faq.all(t)) for t in ("dt", "summary", "h3")) if q), [])
    assert len(qs) == 3, f"expected 3 questions, found {len(qs)}"
    for q, topic in zip(qs, (r"work", r"container", r"wholesale")):
        _has(q.text(), topic)
    assert PLACEHOLDER not in faq.text()
    _has(faq.text(), r"non-flammable container", r"1 cm", r"8 cm", r"info@atomrahome\.com", r"location")

def test_contact_shows_entity_address_email_without_forms_links_or_scripts():
    """The contact section shows MB Gokas (AtomraHome), Parko g. 4, LT-97105 Kretinga, Lietuva and info@atomrahome.com, with no form, input, mailto/tel link or script."""
    text = _section("contact").text()
    for item in ("MB Gokas (AtomraHome)", "Parko g. 4, LT-97105 Kretinga, Lietuva", "info@atomrahome.com"):
        assert item in text, f"contact is missing {item!r}"
    assert not list(_tree().all("form", "input", "textarea", "select", "script"))
    assert not re.search(r"\b(mailto|tel):|<script\b", _raw(), re.IGNORECASE)

def test_meta_and_og_descriptions_are_short_approved_sentences():
    """The meta description and og:description are short (at most 160 characters) factual sentences about Atomra candle sand."""
    for key in ("description", "og:description"):
        value = _metas(_tree()).get(key, "").strip()
        assert value and "TO BE PROVIDED" not in value, f"{key} is a placeholder"
        assert len(value) <= 160, f"{key} too long ({len(value)})"
        _has(value, r"candle sand")
