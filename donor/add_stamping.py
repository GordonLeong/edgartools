"""
Utilities for stamping SEC filing HTML with stable source IDs
and injecting Substack-style typography.

This module is the single place where we transform raw SEC HTML
into our canonical `stamped_html` representation.
"""

from __future__ import annotations

import logging
import re
from typing import cast

from lxml import html as lhtml
from .sanitize import sanitize_html

logger = logging.getLogger(__name__)

BLOCK = {"p","div","li","h1","h2","h3","h4","h5","h6","table"}
_SENT = re.compile(r".*?(?:[.!?](?:\s+|$)|$)", re.S)
_TAIL_MIN_LEN = 8

def _tag_name(el: lhtml.HtmlElement) -> str:
    tag = el.tag or ""
    if isinstance(tag, str) and tag.startswith("{"):
        tag = tag.split("}",1)[1]
    return tag.lower()

def _first_tag(root: lhtml.HtmlElement, name:str) -> lhtml.HtmlElement | None:
    for el in root.iter():
        if _tag_name(el) == name:
            return el
    return None

def _ensure_utf8_meta(root: lhtml.HtmlElement) -> None:
    """
    Ensure the document advertises UTF-8 so that browsers decode the file correctly. 
    Stamped HTML is always UTF-8
    """

    head = _first_tag(root, "head")
    if head is None:
        return
    for el in list(head):
        if _tag_name(el) !="meta":
            continue
        charset = el.get("charset")
        if charset:
            #force utf-8
            el.set("charset", "utf-8")
            continue

        http_equiv = (el.get("http-equiv") or "").lower()
        content = el.get("content") or ""
        if http_equiv == "content-type" and "charset=" in content.lower():
            parts = [p.strip() for p in content.split(";") if p.strip()]
            new_parts: list[str] = []
            for p in parts:
                if p.lower().startswith("charset="):
                    new_parts.append("charset=utf-8")
                else:
                    new_parts.append(p)
            el.set("content","; ".join(new_parts))




def _fix_encoding(text: str) -> str:
    """
    Best-effort repair for UTF-8 text that was incorrectly decoded
    as Latin-1/CP1252, producing mojibake like 'Â', 'â€™', 'â€¢'.

    If we don't see typical markers, this is a no-op.
    """
    if "â" not in text and "Â" not in text:
        return text
    try:
        # Interpret current code points as Latin-1 bytes, then decode as UTF-8.
        return text.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
    except UnicodeError:
        return text


def _split_sentences(t: str) -> list[str]:
    return [m.group(0) for m in _SENT.finditer(t) if m.group(0).strip()]


def _should_stamp_tail(t: str) -> bool:
    stripped = t.strip()
    if not stripped:
        return False
    if len(stripped) >= _TAIL_MIN_LEN:
        return True
    # Allow short but meaningful tails like "See note 2"
    return any(ch.isalnum() for ch in stripped) and " " in stripped


_TABLE_TAGS = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "colgroup", "col"}


def _has_table_ancestor(el: lhtml.HtmlElement) -> bool:
    p = el.getparent()
    while p is not None:
        if _tag_name(p) == "table":
            return True
        p = p.getparent()
    return False


def stamp_html(raw_html: str | bytes | bytearray | memoryview) -> tuple[str, dict]:
    """Stamp HTML with stable source IDs.

    Policy:
    - Always stamp block containers (p/div/li/h1..h6) that are NOT inside a table.
    - Stamp tables at the <table> element level only (no stamps inside the table).
    - Add sentence-level spans only for *simple leaf blocks* (no child elements).
    - Handle tail text by wrapping it into <span data-src-id="..."> siblings ONLY when the
      parent container is not a table-related tag. (Prevents invalid <span> under <tr>.)

    Returns (stamped_html, meta).
    """

    if isinstance(raw_html, str):
        raw_html = _fix_encoding(raw_html)
        b = raw_html.encode("utf-8", errors="ignore")
    else:
        b = bytes(raw_html)

    # idempotence: if already stamped, do nothing
    if b"data-src-id" in b:
        s = b.decode("utf-8", errors="ignore")
        stamped_blocks = s.count("data-src-id=")
        return s, {
            "already_stamped": True,
            "stamped_blocks": stamped_blocks,
            "stamped_sentences": 0,
            "tail_spans": 0,
            "tables": 0,
            "text_dump": False,
        }

    root = lhtml.fromstring(b)

    block_i = 0
    sent_cnt = 0
    tail_cnt = 0
    table_cnt = 0

    for el in root.iter():
        tag = _tag_name(el)

        # Stamp tables as a single anchor only.
        if tag == "table":
            src = f"src_{block_i:06d}"; block_i += 1
            el.set("data-src-id", src)
            if el.get("id") is None:
                el.set("id", src)
            table_cnt += 1
            continue

        # Never stamp anything inside a table. (We treat table evidence at table-level.)
        if _has_table_ancestor(el):
            continue

        if tag not in BLOCK:
            continue

        src = f"src_{block_i:06d}"; block_i += 1
        el.set("data-src-id", src)
        if el.get("id") is None:
            el.set("id", src)

        # Sentence stamping only for simple leaf blocks to avoid DOM surgery.
        if len(el) == 0 and (el.text or "").strip():
            txt = el.text or ""
            el.text = None
            for k, part in enumerate(_split_sentences(txt)):
                sp = lhtml.Element("span")
                sp.set("data-src-id", f"{src}_s{k:03d}")
                sp.set("id", f"{src}_s{k:03d}")
                sp.text = part
                el.append(sp)
                sent_cnt += 1

        # Tail text stamping (ballpark anchors) — safe only when the parent isn't table-related.
        parent = el.getparent()
        parent_tag = _tag_name(parent) if parent is not None else ""
        if parent is not None and parent_tag not in _TABLE_TAGS:
            tail = el.tail
            if tail and _should_stamp_tail(tail):
                el.tail = None
                sp = lhtml.Element("span")
                sp.set("data-src-id", f"{src}_t{tail_cnt:03d}")
                sp.set("id", f"{src}_t{tail_cnt:03d}")
                sp.text = tail
                el.addnext(sp)
                tail_cnt += 1

    stamped = cast(str, lhtml.tostring(root, encoding="unicode", method="html"))

    # crude "text-dump" heuristic: very few stamps or a big <pre>
    pre_cnt = sum(1 for x in root.iter() if _tag_name(x) == "pre")
    text_dump = (pre_cnt >= 1 and block_i < 10) or (block_i < 5)

    meta = {
        "already_stamped": False,
        "stamped_blocks": block_i,
        "stamped_sentences": sent_cnt,
        "tail_spans": tail_cnt,
        "tables": table_cnt,
        "text_dump": text_dump,
    }
    logger.debug(
        "stamp_html: blocks=%d sentences=%d tails=%d tables=%d text_dump=%s",
        block_i,
        sent_cnt,
        tail_cnt,
        table_cnt,
        text_dump,
    )
    return _fix_encoding(stamped), meta


def process_stamp(raw_html: str | bytes | bytearray | memoryview) -> str:
    """Backward-compatible wrapper: returns only stamped HTML."""
    stamped, meta = stamp_html(raw_html)
    logger.debug(
        "process_stamp: stamped_blocks=%d sentences=%d tails=%d tables=%d already_stamped=%s",
        meta["stamped_blocks"],
        meta["stamped_sentences"],
        meta["tail_spans"],
        meta["tables"],
        meta["already_stamped"],
    )
    return stamped


def sanitize_and_stamp(raw_html: str | bytes | bytearray | memoryview) -> str:
    """
    Sanitize and stamp HTML with stable source IDs.
    Styling is intentionally omitted; apply presentation in the renderer.
    """
    sanitized = sanitize_html(raw_html)
    stamped, meta = stamp_html(sanitized)
    logger.info(
        "sanitize_and_stamp: stamped_blocks=%d sentences=%d tails=%d tables=%d text_dump=%s already_stamped=%s",
        meta["stamped_blocks"],
        meta["stamped_sentences"],
        meta["tail_spans"],
        meta["tables"],
        meta["text_dump"],
        meta["already_stamped"],
    )
    return stamped


# Backward alias for older callers
def stamp_and_style(raw_html: str | bytes | bytearray | memoryview) -> str:
    return sanitize_and_stamp(raw_html)
