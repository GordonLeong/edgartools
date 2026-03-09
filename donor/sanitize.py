from __future__ import annotations
import logging
import re
from typing import cast
from lxml import html as lhtml

logger = logging.getLogger(__name__)

def tag_name(el: lhtml.HtmlElement | None) -> str:
    if el is None: return ""
    t = el.tag or ""
    if isinstance(t, str) and t.startswith("{"): t = t.split("}", 1)[1]
    return t.lower()

def first_tag(root: lhtml.HtmlElement, name: str) -> lhtml.HtmlElement | None:
    name = name.lower()
    for el in root.iter():
        if tag_name(el) == name: return el
    return None

def ensure_utf8_meta(root: lhtml.HtmlElement) -> None:
    head = first_tag(root, "head")
    if head is None: return
    for el in list(head):
        if tag_name(el) != "meta": continue
        if el.get("charset"):
            el.set("charset", "utf-8"); continue
        if (el.get("http-equiv") or "").lower() == "content-type":
            c = el.get("content") or ""
            if "charset=" in c.lower():
                parts = [p.strip() for p in c.split(";") if p.strip()]
                el.set("content", "; ".join(["charset=utf-8" if p.lower().startswith("charset=") else p for p in parts]))

def fix_encoding(s: str) -> str:
    if "â" not in s and "Â" not in s: return s
    try: return s.encode("latin-1", "strict").decode("utf-8", "strict")
    except UnicodeError: return s

_DROP_XPATH = ("//script|//iframe|//object|//embed|//applet|//base|"
               "//meta[translate(@http-equiv,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='refresh']")
_BAD_SCHEMES = ("javascript:", "vbscript:")

def sanitize_html(raw: str | bytes | bytearray | memoryview) -> str:
    b = fix_encoding(raw).encode("utf-8", "ignore") if isinstance(raw, str) else bytes(raw)
    root = lhtml.fromstring(b); ensure_utf8_meta(root)

    drop_nodes = root.xpath(_DROP_XPATH)
    drop_count = len(drop_nodes)
    for el in drop_nodes:
        el.drop_tree()

    handlers_removed = 0
    href_cleaned = 0
    src_cleaned = 0
    style_removed = 0

    for el in root.iter():
        for k in list(el.attrib):
            if k.lower().startswith("on"):
                del el.attrib[k]
                handlers_removed += 1
        for attr in ("href", "src"):
            v = el.get(attr)
            if not v:
                continue
            vv = v.strip()
            if vv.lower().startswith(_BAD_SCHEMES):
                el.set(attr, "#")
                if attr == "href":
                    href_cleaned += 1
                else:
                    src_cleaned += 1
            if attr == "src" and vv.lower().startswith("data:") and not vv.lower().startswith("data:image/"):
                el.set(attr, "")
                src_cleaned += 1
        st = el.get("style")
        if st and re.search(r"expression\s*\(|javascript\s*:", st, re.I):
            del el.attrib["style"]
            style_removed += 1

    logger.debug(
        "sanitize_html: dropped=%d handlers_removed=%d href_cleaned=%d src_cleaned=%d style_removed=%d",
        drop_count,
        handlers_removed,
        href_cleaned,
        src_cleaned,
        style_removed,
    )
    return cast(str, lhtml.tostring(root, encoding="unicode", method="html"))
