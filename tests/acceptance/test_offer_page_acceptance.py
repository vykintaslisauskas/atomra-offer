"""Acceptance tests for the Atomra Candle Sand B2B wholesale offer page (docs/index.html)."""

import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "index.html"
SECTION_IDS = ("hero", "product-facts", "audience", "contact")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


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


def _offer_page():
    """Return the parsed page, asserting the offer template sections are present."""
    root = _tree()
    missing = [i for i in SECTION_IDS if root.by_id(i) is None]
    assert not missing, f"offer template sections missing: {missing}"
    return root


# 1. Hero section

def test_hero_section_exists():
    """The page has a hero section with id="hero"."""
    _section("hero")


# 2. Product facts

def test_product_facts_has_three_to_five_items():
    """The product facts section (id="product-facts") lists between 3 and 5 list items."""
    facts = _section("product-facts")
    items = facts.find_all("li")
    assert 3 <= len(items) <= 5, f"expected 3-5 list items, found {len(items)}"


# 3. Contact

def test_page_has_no_form():
    """The offer page (with its contact section) contains no <form> element anywhere."""
    _section("contact")
    root = _offer_page()
    assert not root.find_all("form")


def test_page_has_no_input_fields():
    """The offer page (with its contact section) contains no input, textarea, select or button fields."""
    _section("contact")
    root = _offer_page()
    assert not root.find_all("input", "textarea", "select", "button")


def test_page_has_no_mailto_or_tel_links():
    """The offer page (with its contact section) contains no mailto: or tel: links."""
    _section("contact")
    root = _offer_page()
    for node in root.iter():
        for attr in ("href", "action", "formaction"):
            value = (node.attrs.get(attr) or "").strip().lower()
            assert not value.startswith(("mailto:", "tel:")), f"forbidden link: {value}"
    assert not re.search(r"\b(mailto|tel):", _raw(), re.IGNORECASE)


# 4. No currencies

def test_offer_page_has_no_currency_symbols_or_codes():
    """The offer page contains no currency symbols or codes (EUR, USD, GBP, euro, dollar, pound signs)."""
    _offer_page()
    raw = _raw()
    assert not re.search(r"[€$£¥]", raw), "currency symbol found"
    assert not re.search(r"&(euro|pound|dollar|yen|curren);|&#(8364|36|163|165);|&#x(20ac|24|a3|a5);",
                         raw, re.IGNORECASE), "currency entity found"
    assert not re.search(r"\b(EUR|USD|GBP)\b", raw, re.IGNORECASE), "currency code found"


# 5. Document basics

def test_offer_page_has_non_empty_title():
    """The offer page has a non-empty <title> element."""
    root = _offer_page()
    titles = root.find_all("title")
    assert len(titles) == 1 and titles[0].text().strip()


def test_offer_page_has_meta_charset():
    """The offer page declares its character set with a <meta charset> tag."""
    root = _offer_page()
    assert any("charset" in m.attrs for m in root.find_all("meta"))


def test_offer_page_has_exactly_one_h1():
    """The offer page has exactly one <h1> element."""
    root = _offer_page()
    assert len(root.find_all("h1")) == 1
