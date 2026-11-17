"""Acceptance tests: the offer page is filled only with OWNER-approved facts (content/approved_facts.md)."""

import html
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "docs" / "index.html"
FACTS = ROOT / "content" / "approved_facts.md"
PLACEHOLDER = "TO BE PROVIDED BY OWNER"
SECTION_IDS = ["hero", "product-facts", "audience", "pricing", "faq", "contact"]
ITEM_TAGS = "li|tr|p|dd|dt|td"

class _Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, {k: (v or "") for k, v in attrs}))

def _raw():
    assert PAGE.is_file(), "docs/index.html is missing"
    return PAGE.read_text(encoding="utf-8")

def _tags():
    parser = _Tags()
    parser.feed(_raw())
    return parser.tags

def _text(fragment):
    fragment = re.sub(r"<(script|style|head)\b.*?</\1>", " ", fragment, flags=re.S | re.I)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())

def _section(sid):
    match = re.search(r'<section\b[^>]*\bid="' + re.escape(sid) + r'"[^>]*>(.*?)</section>', _raw(), re.S | re.I)
    assert match, f'no <section id="{sid}"> on the page'
    return match.group(1)

def _items(fragment, tags=ITEM_TAGS):
    return [_text(m.group(2)) for m in re.finditer(rf"<({tags})\b[^>]*>(.*?)</\1>", fragment, re.S | re.I)]

def _filled_page():
    """Assert the page has been filled with approved facts (contact e-mail visible), return the visible text."""
    text = _text(_raw())
    assert "info@atomrahome.com" in text, "page is not yet filled with the approved facts"
    return text

def _meta(key):
    found = [a.get("content", "") for t, a in _tags() if t == "meta" and key in (a.get("name"), a.get("property"))]
    assert len(found) == 1, f'expected exactly one <meta> for "{key}", found {len(found)}'
    return found[0]

def test_sections_order_and_document_basics_kept():
    """The filled page keeps sections hero, product-facts, audience, pricing, faq, contact in order, one h1, a title and a meta charset."""
    _filled_page()
    tags = _tags()
    ids = [a["id"] for t, a in tags if a.get("id") in SECTION_IDS]
    assert ids == SECTION_IDS, f"section ids/order changed: {ids}"
    assert all(t == "section" for t, a in tags if a.get("id") in SECTION_IDS)
    assert sum(t == "h1" for t, _ in tags) == 1, "page must have exactly one <h1>"
    assert re.search(r"<title>\s*\S.*?</title>", _raw(), re.S | re.I), "page must have a non-empty <title>"
    assert any(t == "meta" and "charset" in a for t, a in tags), "page must have a <meta charset>"

def test_hero_is_filled_with_candle_sand_headline():
    """The hero headline and subheading are real text about Atomra candle sand, not placeholders."""
    hero = _section("hero")
    assert PLACEHOLDER not in _text(hero), "hero still contains the placeholder"
    assert "candle sand" in _text(hero).lower(), "hero does not mention candle sand"

def test_product_facts_list_the_approved_product_facts():
    """The product facts section lists the approved facts: granulated wax, colours, reprocessed black sand, unscented, 15-hour wick."""
    text = _text(_section("product-facts")).lower()
    assert PLACEHOLDER.lower() not in text, "product facts still contain the placeholder"
    for phrase in ("granulated", "white", "colored", "full-color black", "fully reprocessed",
                   "stain", "no artificial dye smell", "unscented", "about 15 hours"):
        assert phrase in text, f"product facts do not mention {phrase!r}"

def test_audience_says_wholesale_for_resellers_and_decoration_or_events():
    """The audience section says wholesale and bulk are offered to resellers and for decoration or events."""
    text = _text(_section("audience")).lower()
    assert PLACEHOLDER.lower() not in text, "audience still contains the placeholder"
    for phrase in ("wholesale", "bulk", "resell", "decoration", "event"):
        assert phrase in text, f"audience section does not mention {phrase!r}"

def test_pricing_lists_the_four_approved_pack_formats():
    """The pricing section lists 500 g with 10 wicks, 750 g with 20 wicks, 1.5 kg with 20 wicks and 3 kg with 50 wicks."""
    items = _items(_section("pricing"))
    formats = [(r"(?<![\d.,])500\s*g\b", r"(?<!\d)10\s+wicks"), (r"(?<![\d.,])750\s*g\b", r"(?<!\d)20\s+wicks"),
               (r"(?<![\d.,])1[.,]5\s*kg\b", r"(?<!\d)20\s+wicks"), (r"(?<![\d.,])3\s*kg\b", r"(?<!\d)50\s+wicks")]
    for weight, wicks in formats:
        assert any(re.search(weight, i, re.I) and re.search(wicks, i, re.I) for i in items), \
            f"pricing has no item matching {weight} with {wicks}"

def test_pricing_keeps_placeholders_for_wholesale_prices_and_moq():
    """The pricing section keeps "TO BE PROVIDED BY OWNER" placeholders for wholesale prices and minimum order quantity."""
    items = [i for i in _items(_section("pricing")) if PLACEHOLDER in i]
    assert any(re.search(r"wholesale price", i, re.I) for i in items), "no wholesale prices placeholder"
    assert any(re.search(r"minimum order|\bMOQ\b", i, re.I) for i in items), "no minimum order quantity placeholder"

def test_no_retail_price_discount_percent_currency_or_unapproved_claim():
    """The filled page shows no retail price, discount, percent sign, currency symbol/code or unapproved claim."""
    _filled_page()
    raw = _raw()
    assert "%" not in raw, "percent sign found"
    assert not re.search(r"[€$£¥]|&(euro|pound|dollar|yen);|\b(EUR|USD|GBP)\b", raw, re.I), "currency found"
    forbidden = r"\b(retail|discounts?|sale|promo\w*|certif\w*|organic|non-toxic|eco-friendly|guarantee\w*)\b"
    found = re.findall(forbidden, raw, re.I)
    assert not found, f"forbidden or unapproved wording found: {found}"

def test_faq_has_three_questions_on_use_container_and_wholesale():
    """The FAQ has exactly three questions: how the candle sand works, which container to use, how to ask for wholesale."""
    faq = _section("faq")
    assert PLACEHOLDER not in _text(faq), "FAQ still contains the placeholder"
    questions = _items(faq, "dt") or _items(faq, "summary") or _items(faq, "h3")
    assert len(questions) == 3, f"expected exactly 3 questions, found {len(questions)}"
    for topic in (r"\bwork", r"\bcontainer", r"\bwholesale"):
        assert any(re.search(topic, q, re.I) for q in questions), f"no question about {topic}"

def test_faq_answers_use_the_approved_facts():
    """The FAQ answers give the approved usage steps, container guidance and the wholesale e-mail request."""
    text = _text(_section("faq")).lower()
    for phrase in ("pour", "non-flammable container", "flatten", "1 cm", "8 cm", "5 cm",
                   "info@atomrahome.com", "your business", "location"):
        assert phrase in text, f"FAQ answers do not mention {phrase!r}"

def test_contact_shows_entity_address_and_email_as_text():
    """The contact section shows MB Gokas (AtomraHome), Parko g. 4, LT-97105 Kretinga, Lietuva and info@atomrahome.com."""
    text = _text(_section("contact"))
    for part in ("MB Gokas (AtomraHome)", "Parko g. 4", "LT-97105 Kretinga", "Lietuva", "info@atomrahome.com"):
        assert part in text, f"contact section does not show {part!r}"

def test_filled_page_has_no_form_input_mailto_tel_or_script():
    """The filled page has no form, input fields, mailto or tel link and no script element."""
    _filled_page()
    tags = [t for t, _ in _tags()]
    for tag in ("form", "input", "textarea", "select", "button", "script"):
        assert tag not in tags, f"forbidden <{tag}> element found"
    assert not re.search(r"\b(mailto|tel):", _raw(), re.I), "mailto: or tel: link found"

def test_meta_and_og_descriptions_are_short_approved_fact_sentences():
    """The meta description and og:description are short factual sentences using only words from the approved facts."""
    vocabulary = set(re.findall(r"[a-z0-9]+", FACTS.read_text(encoding="utf-8").lower()))
    for key in ("description", "og:description"):
        content = _meta(key).strip()
        assert content and PLACEHOLDER not in content, f"{key} is empty or still a placeholder"
        assert len(content) <= 200, f"{key} is longer than 200 characters"
        unknown = set(re.findall(r"[a-z0-9]+", content.lower())) - vocabulary
        assert not unknown, f"{key} uses words not in the approved facts: {sorted(unknown)}"
