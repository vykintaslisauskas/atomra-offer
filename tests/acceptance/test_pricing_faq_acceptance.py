"""Acceptance tests for the pricing/packaging and FAQ sections of docs/index.html."""

import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "index.html"
EXISTING_TESTS = ROOT / "tests" / "acceptance" / "test_offer_page_acceptance.py"
PLACEHOLDER = "TO BE PROVIDED BY OWNER"
NEW_SECTION_IDS = ("pricing", "faq")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
LABELS = HEADINGS | {"th", "caption", "legend"}
BLOCKS = {"p", "li", "dt", "dd", "td", "tr", "div", "blockquote", "figcaption", "summary", "details"}
INVISIBLE = {"head", "script", "style", "template", "noscript"}

# Existing sections exactly as they were before the pricing/FAQ work (whitespace-normalised).
ORIGINAL_SECTIONS = {
    "hero": (
        '<section id="hero">'
        '<h1 class="placeholder">Headline: TO BE PROVIDED BY OWNER</h1>'
        '<p class="placeholder">Subheading: TO BE PROVIDED BY OWNER</p>'
        '</section>'
    ),
    "product-facts": (
        '<section id="product-facts">'
        '<h2>Product facts</h2>'
        '<ul>'
        '<li class="placeholder">Product fact: TO BE PROVIDED BY OWNER</li>'
        '<li class="placeholder">Product fact: TO BE PROVIDED BY OWNER</li>'
        '<li class="placeholder">Product fact: TO BE PROVIDED BY OWNER</li>'
        '</ul>'
        '</section>'
    ),
    "audience": (
        '<section id="audience">'
        '<h2>Who it is for</h2>'
        '<p class="placeholder">Target audience: TO BE PROVIDED BY OWNER</p>'
        '</section>'
    ),
    "contact": (
        '<section id="contact">'
        '<h2>Contact</h2>'
        '<p class="placeholder">Contact details: TO BE PROVIDED BY OWNER</p>'
        '</section>'
    ),
}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []  # Node or str

    def text(self, skip=()):
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in skip:
                parts.append(child.text(skip))
        return " ".join(" ".join(parts).split())

    def iter(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.iter()

    def strings(self):
        for child in self.children:
            if isinstance(child, str):
                yield child, self
            else:
                yield from child.strings()

    def find_all(self, *tags):
        return [n for n in self.iter() if n.tag in tags]

    def by_id(self, element_id):
        for n in self.iter():
            if n.attrs.get("id") == element_id:
                return n
        return None


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

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, attrs, self.current))

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


def _section(element_id):
    node = _tree().by_id(element_id)
    assert node is not None, f'no element with id="{element_id}" on the page'
    return node


def _updated_page():
    """Return the parsed page, asserting the new pricing and FAQ sections are present."""
    root = _tree()
    missing = [i for i in NEW_SECTION_IDS if root.by_id(i) is None]
    assert not missing, f"new sections missing: {missing}"
    return root


def _normalise(html):
    return re.sub(r">\s+<", "><", " ".join(html.split()))


def _raw_section(element_id):
    match = re.search(
        r'<section\b[^>]*\bid="' + re.escape(element_id) + r'"[^>]*>.*?</section>',
        _raw(), re.DOTALL | re.IGNORECASE)
    assert match, f'no <section id="{element_id}"> in the page source'
    return _normalise(match.group(0))


def _under(node, tags, stop):
    while node is not None and node is not stop:
        if node.tag in tags:
            return True
        node = node.parent
    return False


def _nearest_block(node, stop):
    while node is not stop:
        if node.tag in BLOCKS:
            return node
        node = node.parent
    return stop


def _non_placeholder_texts(section):
    """Texts in the section (outside headings/labels) whose enclosing block has no placeholder."""
    offenders, seen = [], 0
    for string, parent in section.strings():
        if not string.strip() or _under(parent, LABELS | INVISIBLE, section):
            continue
        seen += 1
        block = _nearest_block(parent, section)
        text = string if block is section else block.text()
        if PLACEHOLDER not in text:
            offenders.append(" ".join(string.split()))
    return seen, offenders


def _labelled_items(section, pattern):
    """Innermost elements whose text matches the label pattern and contains the placeholder."""
    regex = re.compile(pattern, re.IGNORECASE)

    def matches(n):
        t = n.text()
        return bool(regex.search(t)) and PLACEHOLDER in t

    candidates = [n for n in section.iter() if matches(n)]
    return [n for n in candidates if not any(matches(d) for d in n.iter())]


def _assert_labelled_placeholder(pattern, what):
    pricing = _section("pricing")
    items = [n for n in _labelled_items(pricing, pattern)
             if n.tag in {"p", "li", "tr", "dd", "dt", "td", "div", "span", "strong", "em"}]
    assert items, f"pricing section has no {what} placeholder containing {PLACEHOLDER!r}"


def _visible_text(root):
    body = root.find_all("body")
    scope = body[0] if body else root
    return scope.text(skip=INVISIBLE)


# 1. Existing sections unchanged, existing tests still pass

def test_hero_section_unchanged():
    """With the new sections added, the hero section (id="hero") is byte-for-byte unchanged apart from whitespace."""
    _updated_page()
    assert _raw_section("hero") == ORIGINAL_SECTIONS["hero"]


def test_product_facts_section_unchanged():
    """With the new sections added, the product facts section (id="product-facts") is unchanged apart from whitespace."""
    _updated_page()
    assert _raw_section("product-facts") == ORIGINAL_SECTIONS["product-facts"]


def test_audience_section_unchanged():
    """With the new sections added, the audience section (id="audience") is unchanged apart from whitespace."""
    _updated_page()
    assert _raw_section("audience") == ORIGINAL_SECTIONS["audience"]


def test_contact_section_unchanged():
    """With the new sections added, the contact section (id="contact") is unchanged apart from whitespace."""
    _updated_page()
    assert _raw_section("contact") == ORIGINAL_SECTIONS["contact"]


def test_existing_offer_page_tests_still_pass():
    """With the new sections added, the existing offer page acceptance tests still all pass."""
    _updated_page()
    assert EXISTING_TESTS.is_file(), "existing acceptance test file is missing"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(EXISTING_TESTS)],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


# 2. Pricing and packaging section

def test_pricing_section_exists():
    """The page has a pricing and packaging <section> with id="pricing"."""
    pricing = _section("pricing")
    assert pricing.tag == "section", f'id="pricing" is on a <{pricing.tag}>, not a <section>'


def test_pricing_has_prices_placeholder():
    """The pricing section has an item mentioning prices whose text contains the owner placeholder."""
    _assert_labelled_placeholder(r"\bprices?\b", "prices")


def test_pricing_has_tiers_placeholder():
    """The pricing section has an item mentioning tiers whose text contains the owner placeholder."""
    _assert_labelled_placeholder(r"\btiers?\b", "tiers")


def test_pricing_has_package_sizes_placeholder():
    """The pricing section has an item mentioning package sizes whose text contains the owner placeholder."""
    _assert_labelled_placeholder(r"\bpackage\s+sizes?\b", "package sizes")


def test_pricing_contains_only_placeholder_text():
    """Apart from headings, every piece of text in the pricing section is an owner placeholder."""
    pricing = _section("pricing")
    seen, offenders = _non_placeholder_texts(pricing)
    assert seen, "pricing section has no text besides headings"
    assert not offenders, f"non-placeholder text in pricing section: {offenders}"


# 3. FAQ section

def test_faq_section_exists():
    """The page has a FAQ <section> with id="faq"."""
    faq = _section("faq")
    assert faq.tag == "section", f'id="faq" is on a <{faq.tag}>, not a <section>'


def test_faq_has_exactly_three_question_placeholders():
    """The FAQ section has exactly three questions, each labelled "Question" and containing the owner placeholder."""
    faq = _section("faq")
    questions = _labelled_items(faq, r"\bquestion\b")
    assert len(questions) == 3, f"expected 3 question placeholders, found {len(questions)}"


def test_faq_has_exactly_three_answer_placeholders():
    """The FAQ section has exactly three answers, each labelled "Answer" and containing the owner placeholder."""
    faq = _section("faq")
    answers = _labelled_items(faq, r"\banswer\b")
    assert len(answers) == 3, f"expected 3 answer placeholders, found {len(answers)}"


def test_faq_contains_only_placeholder_text():
    """Apart from headings, every piece of text in the FAQ section is an owner placeholder."""
    faq = _section("faq")
    seen, offenders = _non_placeholder_texts(faq)
    assert seen, "FAQ section has no text besides headings"
    assert not offenders, f"non-placeholder text in FAQ section: {offenders}"


# 4. Still no form, inputs, contact links, prices or digits

def test_updated_page_has_no_form():
    """With the new sections added, the page still contains no <form> element."""
    root = _updated_page()
    assert not root.find_all("form")


def test_updated_page_has_no_input_fields():
    """With the new sections added, the page still contains no input, textarea or select element."""
    root = _updated_page()
    assert not root.find_all("input", "textarea", "select")


def test_updated_page_has_no_mailto_or_tel_links():
    """With the new sections added, the page still contains no mailto: or tel: links."""
    _updated_page()
    assert not re.search(r"\b(mailto|tel):", _raw(), re.IGNORECASE)


def test_updated_page_has_no_currency_symbols_or_codes():
    """With the new sections added, the page still contains no currency symbols or codes (EUR, USD, GBP, €, $, £)."""
    _updated_page()
    raw = _raw()
    assert not re.search(r"[€$£¥]", raw), "currency symbol found"
    assert not re.search(r"&(euro|pound|dollar|yen|curren);|&#(8364|36|163|165);|&#x(20ac|24|a3|a5);",
                         raw, re.IGNORECASE), "currency entity found"
    assert not re.search(r"\b(EUR|USD|GBP)\b", raw, re.IGNORECASE), "currency code found"


def test_updated_page_visible_text_has_no_digits():
    """With the new sections added, the visible text of the page still contains no digits."""
    root = _updated_page()
    text = _visible_text(root)
    assert not re.search(r"\d", text), f"digits found in visible text: {text!r}"


# 5. Document basics

def test_updated_page_has_title():
    """With the new sections added, the page still has exactly one non-empty <title>."""
    root = _updated_page()
    titles = root.find_all("title")
    assert len(titles) == 1 and titles[0].text().strip()


def test_updated_page_has_meta_charset():
    """With the new sections added, the page still declares a <meta charset>."""
    root = _updated_page()
    assert any("charset" in m.attrs for m in root.find_all("meta"))


def test_updated_page_has_exactly_one_h1():
    """With the new sections added, the page still has exactly one <h1>."""
    root = _updated_page()
    assert len(root.find_all("h1")) == 1
