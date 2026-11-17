"""Acceptance tests for filling the Atomra Candle Sand offer page with OWNER-approved facts."""

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "index.html"
FACTS = ROOT / "content" / "approved_facts.md"
PLACEHOLDER = "TO BE PROVIDED BY OWNER"
SECTION_IDS = ("hero", "product-facts", "audience", "pricing", "faq", "contact")
EARLIER_TESTS = [ROOT / "tests" / "acceptance" / f"test_{name}_acceptance.py"
                 for name in ("offer_page", "pricing_faq", "seo_metadata")]
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
INVISIBLE = {"head", "script", "style", "template", "noscript"}
QUESTION_TAGS = {"dt", "summary", "h3", "h4", "h5", "h6"}

# Words allowed besides the approved facts' vocabulary: labels and function words with no factual claim.
STRUCTURAL_WORDS = {
    "facts", "fact", "pricing", "packaging", "frequently", "asked", "question", "answer", "faq",
    "minimum", "moq", "price", "prices", "provided", "by", "owner", "offer", "package",
    "does", "do", "doesn", "don", "won", "t", "s", "i", "should", "what", "work", "we", "our",
    "this", "these", "if", "then", "also", "any", "per", "here", "resellers", "reseller",
}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag = tag
        self.attrs = {k: (v or "") for k, v in attrs}
        self.parent = parent
        self.children = []  # Node or str

    def text(self, skip_tags=INVISIBLE, skip_nodes=()):
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in skip_tags and child not in skip_nodes:
                parts.append(child.text(skip_tags, skip_nodes))
        return " ".join(" ".join(parts).split())

    def iter(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.iter()

    def find_all(self, *tags):
        return [n for n in self.iter() if n.tag in tags]

    def by_id(self, element_id):
        return next((n for n in self.iter() if n.attrs.get("id") == element_id), None)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", [])
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def _raw():
    assert PAGE.is_file(), "docs/index.html is missing"
    return PAGE.read_text(encoding="utf-8")


def _tree():
    builder = TreeBuilder()
    builder.feed(_raw())
    builder.close()
    return builder.root


def _filled_page():
    """Return the parsed page, asserting no visible placeholder remains outside the pricing section."""
    root = _tree()
    pricing = root.by_id("pricing")
    assert pricing is not None, 'no element with id="pricing" on the page'
    outside = root.text(skip_nodes=(pricing,))
    assert PLACEHOLDER not in outside, \
        f"placeholder text remains outside the pricing section: {outside!r}"
    return root


def _section(element_id):
    node = _filled_page().by_id(element_id)
    assert node is not None, f'no element with id="{element_id}" on the page'
    return node


def _head_meta_content(key):
    root = _tree()
    heads = root.find_all("head")
    assert len(heads) == 1, "page must have exactly one <head>"
    found = [m for m in heads[0].find_all("meta")
             if key in (m.attrs.get("name", "").strip().lower(),
                        m.attrs.get("property", "").strip().lower())]
    assert len(found) == 1, f'expected exactly one <meta> for "{key}" in <head>, found {len(found)}'
    return " ".join(found[0].attrs.get("content", "").split())


def _facts_body():
    assert FACTS.is_file(), "content/approved_facts.md is missing"
    text = FACTS.read_text(encoding="utf-8")
    return text[text.index("\n## "):]


def _unapproved(text):
    words = lambda t: re.findall(r"[a-z]+", t.lower())  # noqa: E731
    numbers = lambda t: {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,/]\d+)?", t)}  # noqa: E731
    vocab = set(words(_facts_body())) | STRUCTURAL_WORDS
    extra = {w for w in words(text)
             if not (w in vocab or (w.endswith("s") and w[:-1] in vocab) or w + "s" in vocab)}
    return sorted(extra | (numbers(text) - numbers(_facts_body())))


def _faq_pairs():
    # Each question element is paired with all text up to the next question element.
    faq = _section("faq")
    pairs = []

    def walk(node):
        for child in node.children:
            if isinstance(child, str):
                if pairs:
                    pairs[-1][1].append(child)
            elif child.tag in INVISIBLE:
                continue
            elif child.tag in QUESTION_TAGS:
                pairs.append((child.text(), []))
            else:
                walk(child)

    walk(faq)
    return [(q, " ".join(" ".join(a).split())) for q, a in pairs]


def _faq_answer(question_pattern):
    matches = [a for q, a in _faq_pairs() if re.search(question_pattern, q, re.IGNORECASE)]
    assert len(matches) == 1, f"expected one FAQ question matching {question_pattern!r}, found {len(matches)}"
    assert matches[0], "the FAQ question has no answer"
    return matches[0]


def _pack_formats():
    text = _section("pricing").text()
    token = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)?)\s*(kg|g)\b|(?<![\d.,])(\d+)\s*wicks?\b", re.IGNORECASE)
    pairs, weight = [], None
    for m in token.finditer(text):
        if m.group(1):
            value = float(m.group(1).replace(",", "."))
            weight = round(value * (1000 if m.group(2).lower() == "kg" else 1))
        elif weight is not None:
            pairs.append((weight, int(m.group(3))))
            weight = None
    return pairs


# 1. Structure and document basics

def test_sections_keep_ids_and_order():
    """The filled page keeps the sections hero, product-facts, audience, pricing, faq, contact in that order."""
    root = _filled_page()
    order = [n.attrs["id"] for n in root.find_all("section") if n.attrs.get("id") in SECTION_IDS]
    assert order == list(SECTION_IDS), f"section order is {order}"


def test_filled_page_has_exactly_one_h1():
    """The filled page has exactly one <h1>."""
    assert len(_filled_page().find_all("h1")) == 1


def test_filled_page_has_title():
    """The filled page has exactly one non-empty <title>."""
    titles = _filled_page().find_all("title")
    assert len(titles) == 1 and titles[0].text().strip()


def test_filled_page_has_meta_charset():
    """The filled page declares a <meta charset>."""
    assert any("charset" in m.attrs for m in _filled_page().find_all("meta"))


# 2. Approved facts only

def test_no_placeholder_outside_pricing():
    """Outside the pricing section, no visible text on the page is still a "TO BE PROVIDED BY OWNER" placeholder."""
    _filled_page()


def test_hero_has_headline_and_subheading():
    """The hero section shows a non-empty headline and a separate non-empty subheading."""
    hero = _section("hero")
    headings = hero.find_all("h1", "h2", "h3", "h4", "h5", "h6")
    assert headings and headings[0].text(), "hero section has no headline text"
    assert hero.text(skip_nodes=(headings[0],)), "hero section has no subheading text"


def test_visible_text_comes_from_approved_facts():
    """Every word and number in the visible page text occurs in content/approved_facts.md (plain labels aside)."""
    extra = _unapproved(_filled_page().text())
    assert not extra, f"words or numbers not found in the approved facts: {extra}"


def test_product_facts_granulated_wax():
    """The product facts say the candle sand is granulated wax."""
    text = _section("product-facts").text().lower()
    assert "granulated" in text and "wax" in text, text


def test_product_facts_colours():
    """The product facts list white, colored and full-color black candle sand."""
    text = _section("product-facts").text().lower()
    assert "white" in text and "colored" in text and re.search(r"full[- ]color black", text), text


def test_product_facts_black_sand_properties():
    """The product facts say the black sand is fully reprocessed, does not stain and has no artificial dye smell."""
    text = _section("product-facts").text().lower()
    assert "fully reprocessed" in text, text
    assert re.search(r"\b(will not|won't|does not|doesn't) stain", text), text
    assert "no artificial dye smell" in text, text


def test_product_facts_unscented():
    """The product facts say the candle sand wax is unscented."""
    assert "unscented" in _section("product-facts").text().lower()


def test_product_facts_wick_lasts_about_15_hours():
    """The product facts say one wick lasts about 15 hours."""
    text = _section("product-facts").text().lower()
    assert re.search(r"\bwick\b.*\babout 15 hours\b", text), text


def test_audience_wholesale_and_bulk_for_resellers():
    """The audience section says wholesale and bulk are offered to businesses that resell."""
    text = _section("audience").text().lower()
    assert "wholesale" in text and "bulk" in text and "resell" in text, text


def test_audience_decoration_and_events():
    """The audience section mentions decoration and events."""
    text = _section("audience").text().lower()
    assert "decoration" in text and "event" in text, text


# 3. Pricing and packaging

def test_pricing_lists_four_pack_formats():
    """The pricing section lists 500 g with 10 wicks, 750 g with 20, 1.5 kg with 20 and 3 kg with 50 wicks."""
    found = _pack_formats()
    for expected in ((500, 10), (750, 20), (1500, 20), (3000, 50)):
        assert expected in found, f"pack format {expected} missing; found {found}"


def _has_pricing_placeholder(label):
    return any(re.search(label, n.text(), re.IGNORECASE) and PLACEHOLDER in n.text()
               and n.tag in {"li", "p", "dd", "dt", "tr", "td", "div"} for n in _section("pricing").iter())


def test_pricing_has_wholesale_price_placeholder():
    """The pricing section has a wholesale prices item marked "TO BE PROVIDED BY OWNER"."""
    assert _has_pricing_placeholder(r"wholesale prices?")


def test_pricing_has_minimum_order_quantity_placeholder():
    """The pricing section has a minimum order quantity item marked "TO BE PROVIDED BY OWNER"."""
    assert _has_pricing_placeholder(r"minimum order quantit|\bMOQ\b")


def test_page_has_no_retail_price():
    """The filled page never mentions retail prices."""
    _filled_page()
    assert not re.search(r"retail", _raw(), re.IGNORECASE)


def test_page_has_no_discount():
    """The filled page never mentions discounts or promotions."""
    _filled_page()
    assert not re.search(r"discount|promotion", _raw(), re.IGNORECASE)


def test_page_has_no_percent_sign():
    """The filled page contains no percent sign."""
    _filled_page()
    assert not re.search(r"%|&percnt;|&#37;|&#x25;", _raw(), re.IGNORECASE)


def test_page_has_no_currency():
    """The filled page contains no currency symbol, currency entity or currency code."""
    _filled_page()
    assert not re.search(r"[€$£¥]|&(euro|pound|dollar|yen|curren);|&#(8364|36|163|165);|&#x(20ac|24|a3|a5);"
                         r"|\b(EUR|USD|GBP|euros?|dollars?)\b", _raw(), re.IGNORECASE)


# 4. FAQ

def test_faq_has_exactly_three_questions():
    """The FAQ section has exactly three questions, each followed by an answer."""
    pairs = _faq_pairs()
    assert len(pairs) == 3, f"expected 3 FAQ questions, found {len(pairs)}: {pairs}"
    assert all(q and a for q, a in pairs), f"empty question or answer: {pairs}"


def test_faq_how_candle_sand_works():
    """The FAQ answers how the candle sand works: pour the wax, insert the wick, light it."""
    answer = _faq_answer(r"\bhow\b.*\bwork").lower()
    assert "pour" in answer and "wick" in answer and "light" in answer, answer


def test_faq_which_container():
    """The FAQ answers which container to use: non-flammable, at least 8 cm wide, 5 cm of wax around each wick."""
    answer = _faq_answer(r"container").lower()
    assert re.search(r"\b8\s*cm|\b3\s*inch", answer), answer
    assert re.search(r"\b5\s*cm|\b2\s*inch", answer), answer


def test_faq_how_to_ask_for_wholesale():
    """The FAQ answers how to ask for wholesale: e-mail info@atomrahome.com with business, location and products."""
    answer = _faq_answer(r"wholesale")
    assert "info@atomrahome.com" in answer, answer
    lower = answer.lower()
    assert "business" in lower and "location" in lower and "product" in lower, answer


# 5. Contact

def test_contact_shows_legal_entity():
    """The contact section shows the legal entity "MB Gokas (AtomraHome)" as visible text."""
    assert "MB Gokas (AtomraHome)" in _section("contact").text()


def test_contact_shows_address():
    """The contact section shows the address "Parko g. 4, LT-97105 Kretinga, Lietuva" as visible text."""
    text = _section("contact").text()
    assert re.search(r"Parko g\. 4,?\s+LT-97105 Kretinga,?\s+Lietuva", text), text


def test_contact_shows_email():
    """The contact section shows the e-mail info@atomrahome.com as visible text."""
    assert "info@atomrahome.com" in _section("contact").text()


def test_filled_page_has_no_form():
    """The filled page contains no <form> element."""
    assert not _filled_page().find_all("form")


def test_filled_page_has_no_input_fields():
    """The filled page contains no input, textarea, select or button element."""
    assert not _filled_page().find_all("input", "textarea", "select", "button")


def test_filled_page_has_no_mailto_or_tel():
    """The filled page contains no mailto: or tel: link."""
    _filled_page()
    assert not re.search(r"\b(mailto|tel):", _raw(), re.IGNORECASE)


def test_filled_page_has_no_script():
    """The filled page contains no <script> element."""
    assert not _filled_page().find_all("script")
    assert not re.search(r"<script\b", _raw(), re.IGNORECASE)


# 6. Earlier acceptance tests

def test_earlier_acceptance_tests_still_pass():
    """With the approved content filled in, the (updated) earlier acceptance tests all still pass."""
    _filled_page()
    for path in EARLIER_TESTS:
        assert path.is_file(), f"earlier acceptance test file is missing: {path.name}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *map(str, EARLIER_TESTS)],
        cwd=ROOT, capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr


# 7. Meta description and og:description

def _assert_short_approved_sentence(content):
    assert content and PLACEHOLDER not in content, f"empty or still a placeholder: {content!r}"
    assert len(content) <= 160 and content.endswith("."), f"not one short sentence: {content!r}"
    extra = _unapproved(content)
    assert not extra, f"words or numbers not found in the approved facts: {extra}"


def test_meta_description_is_short_approved_sentence():
    """The meta description is a short sentence (at most 160 characters) using only the approved facts."""
    _assert_short_approved_sentence(_head_meta_content("description"))


def test_og_description_is_short_approved_sentence():
    """The og:description is a short sentence (at most 160 characters) using only the approved facts."""
    _assert_short_approved_sentence(_head_meta_content("og:description"))
