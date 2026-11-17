"""Acceptance tests for SEO metadata, sitemap.xml and robots.txt of the Atomra offer page."""

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
PAGE = DOCS / "index.html"
SITEMAP = DOCS / "sitemap.xml"
ROBOTS = DOCS / "robots.txt"
SITE_URL = "https://vykintaslisauskas.github.io/atomra-offer/"
SITEMAP_URL = SITE_URL + "sitemap.xml"
PLACEHOLDER = "TO BE PROVIDED BY OWNER"
EXISTING_TESTS = (
    ROOT / "tests" / "acceptance" / "test_offer_page_acceptance.py",
    ROOT / "tests" / "acceptance" / "test_pricing_faq_acceptance.py",
)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
INVISIBLE = {"head", "script", "style", "template", "noscript"}

# Body sections exactly as they were before the SEO work (whitespace-normalised).
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
    "pricing": (
        '<section id="pricing">'
        '<h2>Pricing and packaging</h2>'
        '<ul>'
        '<li class="placeholder">Prices: TO BE PROVIDED BY OWNER</li>'
        '<li class="placeholder">Tiers: TO BE PROVIDED BY OWNER</li>'
        '<li class="placeholder">Package sizes: TO BE PROVIDED BY OWNER</li>'
        '</ul>'
        '</section>'
    ),
    "faq": (
        '<section id="faq">'
        '<h2>Frequently asked questions</h2>'
        '<dl>'
        '<dt class="placeholder">Question: TO BE PROVIDED BY OWNER</dt>'
        '<dd class="placeholder">Answer: TO BE PROVIDED BY OWNER</dd>'
        '<dt class="placeholder">Question: TO BE PROVIDED BY OWNER</dt>'
        '<dd class="placeholder">Answer: TO BE PROVIDED BY OWNER</dd>'
        '<dt class="placeholder">Question: TO BE PROVIDED BY OWNER</dt>'
        '<dd class="placeholder">Answer: TO BE PROVIDED BY OWNER</dd>'
        '</dl>'
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
        self.attrs = {k: (v or "") for k, v in attrs}
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


def _head_metas(root):
    heads = root.find_all("head")
    assert len(heads) == 1, "page must have exactly one <head>"
    return heads[0].find_all("meta")


def _head_meta(root, key):
    """Return the <meta> in <head> whose name or property equals key, asserting there is one."""
    found = [m for m in _head_metas(root)
             if key in (m.attrs.get("name", "").strip().lower(),
                        m.attrs.get("property", "").strip().lower())]
    assert found, f'no <meta name/property="{key}"> in <head>'
    assert len(found) == 1, f'more than one <meta> for "{key}" in <head>'
    return found[0]


def _seo_page():
    """Return the parsed page, asserting the SEO meta description is present in <head>."""
    root = _tree()
    _head_meta(root, "description")
    return root


def _normalise(html):
    return re.sub(r">\s+<", "><", " ".join(html.split()))


def _raw_section(element_id):
    match = re.search(
        r'<section\b[^>]*\bid="' + re.escape(element_id) + r'"[^>]*>.*?</section>',
        _raw(), re.DOTALL | re.IGNORECASE)
    assert match, f'no <section id="{element_id}"> in the page source'
    return _normalise(match.group(0))


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _robots_lines():
    assert ROBOTS.is_file(), "docs/robots.txt is missing"
    return [line.strip() for line in ROBOTS.read_text(encoding="utf-8").splitlines()]


def _visible_text(root):
    body = root.find_all("body")
    scope = body[0] if body else root
    return scope.text(skip=INVISIBLE)


# 1. Existing sections unchanged, existing tests still pass

def test_hero_section_unchanged():
    """With SEO metadata added, the hero section (id="hero") is unchanged apart from whitespace."""
    _seo_page()
    assert _raw_section("hero") == ORIGINAL_SECTIONS["hero"]


def test_product_facts_section_unchanged():
    """With SEO metadata added, the product facts section (id="product-facts") is unchanged apart from whitespace."""
    _seo_page()
    assert _raw_section("product-facts") == ORIGINAL_SECTIONS["product-facts"]


def test_audience_section_unchanged():
    """With SEO metadata added, the audience section (id="audience") is unchanged apart from whitespace."""
    _seo_page()
    assert _raw_section("audience") == ORIGINAL_SECTIONS["audience"]


def test_pricing_section_unchanged():
    """With SEO metadata added, the pricing section (id="pricing") is unchanged apart from whitespace."""
    _seo_page()
    assert _raw_section("pricing") == ORIGINAL_SECTIONS["pricing"]


def test_faq_section_unchanged():
    """With SEO metadata added, the FAQ section (id="faq") is unchanged apart from whitespace."""
    _seo_page()
    assert _raw_section("faq") == ORIGINAL_SECTIONS["faq"]


def test_contact_section_unchanged():
    """With SEO metadata added, the contact section (id="contact") is unchanged apart from whitespace."""
    _seo_page()
    assert _raw_section("contact") == ORIGINAL_SECTIONS["contact"]


def test_existing_acceptance_tests_still_pass():
    """With SEO metadata added, the earlier offer page and pricing/FAQ acceptance tests still all pass."""
    _seo_page()
    for path in EXISTING_TESTS:
        assert path.is_file(), f"existing acceptance test file is missing: {path.name}"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *map(str, EXISTING_TESTS)],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr


# 2. Head metadata

def test_head_has_meta_description_placeholder():
    """The <head> has a <meta name="description"> whose content contains the owner placeholder."""
    meta = _head_meta(_tree(), "description")
    assert meta.attrs.get("name", "").strip().lower() == "description"
    assert PLACEHOLDER in meta.attrs.get("content", "")


def test_head_has_og_title():
    """The <head> has an Open Graph og:title meta tag with non-empty content."""
    meta = _head_meta(_tree(), "og:title")
    assert meta.attrs.get("content", "").strip(), "og:title has empty content"


def test_head_has_og_description_placeholder():
    """The <head> has an Open Graph og:description meta tag whose content contains the owner placeholder."""
    meta = _head_meta(_tree(), "og:description")
    assert PLACEHOLDER in meta.attrs.get("content", "")


def test_head_has_og_type_website():
    """The <head> has an Open Graph og:type meta tag with content "website"."""
    meta = _head_meta(_tree(), "og:type")
    assert meta.attrs.get("content", "").strip() == "website"


def test_head_has_og_url_site_address():
    """The <head> has an Open Graph og:url meta tag pointing to the public site address."""
    meta = _head_meta(_tree(), "og:url")
    assert meta.attrs.get("content", "").strip() == SITE_URL


# 3. sitemap.xml

def test_sitemap_is_well_formed_xml_urlset():
    """docs/sitemap.xml exists and is well-formed XML whose root element is a urlset."""
    assert SITEMAP.is_file(), "docs/sitemap.xml is missing"
    try:
        root = ET.parse(SITEMAP).getroot()
    except ET.ParseError as exc:
        raise AssertionError(f"sitemap.xml is not well-formed XML: {exc}")
    assert _local(root.tag) == "urlset", f"root element is <{root.tag}>, not <urlset>"


def test_sitemap_has_exactly_one_url_with_site_loc():
    """docs/sitemap.xml lists exactly one url, whose loc is the public site address."""
    assert SITEMAP.is_file(), "docs/sitemap.xml is missing"
    root = ET.parse(SITEMAP).getroot()
    assert _local(root.tag) == "urlset"
    urls = [el for el in root if _local(el.tag) == "url"]
    assert len(urls) == 1, f"expected exactly one <url>, found {len(urls)}"
    locs = [el for el in urls[0] if _local(el.tag) == "loc"]
    assert len(locs) == 1, "the <url> must have exactly one <loc>"
    assert (locs[0].text or "").strip() == SITE_URL


# 4. robots.txt

def test_robots_has_user_agent_all():
    """docs/robots.txt contains the line "User-agent: *"."""
    assert "User-agent: *" in _robots_lines()


def test_robots_has_allow_all():
    """docs/robots.txt contains the line "Allow: /"."""
    assert "Allow: /" in _robots_lines()


def test_robots_points_to_sitemap():
    """docs/robots.txt contains a Sitemap line pointing to the public sitemap.xml address."""
    assert f"Sitemap: {SITEMAP_URL}" in _robots_lines()


# 5. Still no form, inputs, contact links, scripts, prices or digits

def test_seo_page_has_no_form():
    """With SEO metadata added, the page still contains no <form> element."""
    root = _seo_page()
    assert not root.find_all("form")


def test_seo_page_has_no_input_fields():
    """With SEO metadata added, the page still contains no input, textarea or select element."""
    root = _seo_page()
    assert not root.find_all("input", "textarea", "select")


def test_seo_page_has_no_mailto_or_tel_links():
    """With SEO metadata added, the page still contains no mailto: or tel: links."""
    _seo_page()
    assert not re.search(r"\b(mailto|tel):", _raw(), re.IGNORECASE)


def test_seo_page_has_no_script():
    """With SEO metadata added, the page contains no <script> element anywhere (head or body)."""
    root = _seo_page()
    assert not root.find_all("script")
    assert not re.search(r"<script\b", _raw(), re.IGNORECASE)


def test_seo_page_has_no_currency_symbols_or_codes():
    """With SEO metadata added, the page still contains no currency symbols or codes (EUR, USD, GBP, €, $, £)."""
    _seo_page()
    raw = _raw()
    assert not re.search(r"[€$£¥]", raw), "currency symbol found"
    assert not re.search(r"&(euro|pound|dollar|yen|curren);|&#(8364|36|163|165);|&#x(20ac|24|a3|a5);",
                         raw, re.IGNORECASE), "currency entity found"
    assert not re.search(r"\b(EUR|USD|GBP)\b", raw, re.IGNORECASE), "currency code found"


def test_seo_page_visible_text_has_no_digits():
    """With SEO metadata added, the visible text of the page still contains no digits."""
    root = _seo_page()
    text = _visible_text(root)
    assert text, "page has no visible text"
    assert not re.search(r"\d", text), f"digits found in visible text: {text!r}"


# 6. Document basics

def test_seo_page_has_title():
    """With SEO metadata added, the page still has exactly one non-empty <title>."""
    root = _seo_page()
    titles = root.find_all("title")
    assert len(titles) == 1 and titles[0].text().strip()


def test_seo_page_has_meta_charset():
    """With SEO metadata added, the page still declares a <meta charset>."""
    root = _seo_page()
    assert any("charset" in m.attrs for m in root.find_all("meta"))


def test_seo_page_has_exactly_one_h1():
    """With SEO metadata added, the page still has exactly one <h1>."""
    root = _seo_page()
    assert len(root.find_all("h1")) == 1
