"""CLI for downloading, sanitizing, and stamping SEC filings (no styling).

Styling should be applied at render-time in the front-end; this tool only
sanitizes and stamps to preserve provenance-friendly IDs.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from edgar import Company, set_identity

from utils.add_stamping import sanitize_and_stamp
from utils.patch_images import patch_relative_image_srcs

logger = logging.getLogger(__name__)

set_identity("gordon calicofund@gmail.com")


@dataclass
class FilingMeta:
    accession: str
    filing_date: Optional[str]
    form: str


def _parse_date(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid date format: {val}. Use YYYY-MM-DD.")


def _filing_date_to_path(d: Optional[str]) -> str:
    if not d:
        return "unknown_date"
    try:
        return datetime.strptime(str(d), "%Y-%m-%d").strftime("%Y%m%d")
    except Exception:
        return str(d).replace("-", "")


def _get_accession_number(filing) -> str:
    """
    Normalize how we pull the accession from the filing object.
    """
    for attr in ("accession_number", "accession", "accessionNo"):
        val = getattr(filing, attr, None)
        if val:
            return str(val)
    return "unknown_accession"


def _get_cik(filing) -> str:
    """
    Normalize how we pull the CIK from the filing object.
    """
    for attr in ("cik", "CIK", "cik_number", "cikNumber", "company_cik", "companyCik"):
        val = getattr(filing, attr, None)
        if val:
            return str(val)
    return ""


def _select_filings(
    ticker: str,
    form: str,
    limit: int,
    start_date: Optional[str],
    end_date: Optional[str],
    accession: Optional[str],
) -> List:
    company = Company(ticker)
    filings = company.get_filings(form=form)

    # Convert to list for flexible filtering/sorting
    try:
        candidates: List = list(filings)
    except Exception:
        candidates = []

    # Filter by date range if provided
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start or end:
        def in_range(f) -> bool:
            fd = getattr(f, "filing_date", None)
            fd_parsed = _parse_date(str(fd)) if fd else None
            if fd_parsed is None:
                return False
            if start and fd_parsed < start:
                return False
            if end and fd_parsed > end:
                return False
            return True

        candidates = [f for f in candidates if in_range(f)]

    # Sort by filing_date desc when available
    candidates.sort(key=lambda f: getattr(f, "filing_date", None) or "", reverse=True)

    if accession:
        match = [f for f in candidates if getattr(f, "accession_number", "") == accession]
        return match[:1]

    if limit > 0:
        return candidates[:limit]
    return candidates


def _fetch_and_stamp(filing, ticker: str, form: str, out_dir: Path) -> Path:
    raw_html = filing.html()
    accession = _get_accession_number(filing)
    cik = _get_cik(filing)
    html = patch_relative_image_srcs(raw_html, accession, cik)
    meta = FilingMeta(
        accession=accession,
        filing_date=getattr(filing, "filing_date", None),
        form=form,
    )
    stamped = sanitize_and_stamp(html)

    date_part = _filing_date_to_path(meta.filing_date)
    fname = f"{ticker}_{meta.form}_{date_part}_{meta.accession}.html"
    output = out_dir / ticker / meta.form / fname
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(stamped, encoding="utf-8")
    logger.info("Saved %s %s to %s", meta.form, meta.accession, output)
    return output


def list_filings(ticker: str, form: str, limit: int, start_date: Optional[str], end_date: Optional[str]) -> None:
    filings = _select_filings(ticker, form, limit, start_date, end_date, accession=None)
    if not filings:
        logger.warning("No filings found for %s %s", ticker, form)
        return
    for f in filings:
        logger.info(
            "%s %s filed %s (period %s)",
            getattr(f, "form", form),
            getattr(f, "accession_number", ""),
            getattr(f, "filing_date", ""),
            getattr(f, "period_of_report", ""),
        )


def download_filings(
    ticker: str,
    form: str,
    limit: int,
    start_date: Optional[str],
    end_date: Optional[str],
    accession: Optional[str],
    out_dir: Path,
) -> List[Path]:
    filings = _select_filings(ticker, form, limit, start_date, end_date, accession)
    if not filings:
        logger.warning("No filings to download for %s %s", ticker, form)
        return []
    outputs: List[Path] = []
    for f in filings:
        try:
            outputs.append(_fetch_and_stamp(f, ticker, form, out_dir))
        except Exception as exc:
            logger.error("Failed to process %s: %s", getattr(f, "accession_number", ""), exc)
    return outputs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch, sanitize, and stamp SEC filings")
    p.add_argument("ticker", help="Ticker symbol (e.g., MSFT)")
    p.add_argument("--form", choices=["10-K", "10-Q"], default="10-K", help="Filing form")
    p.add_argument("--limit", type=int, default=1, help="Number of filings to fetch (ignored if accession provided)")
    p.add_argument("--start-date", dest="start_date", help="Start date YYYY-MM-DD (optional)")
    p.add_argument("--end-date", dest="end_date", help="End date YYYY-MM-DD (optional)")
    p.add_argument("--accession", help="Specific accession number to fetch")
    p.add_argument("--out-dir", default="data/processed", type=Path, help="Output directory root")
    p.add_argument("--list-only", action="store_true", help="List filings without downloading")
    p.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return p


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    if args.list_only:
        list_filings(args.ticker, args.form, args.limit, args.start_date, args.end_date)
        return

    download_filings(args.ticker, args.form, args.limit, args.start_date, args.end_date, args.accession, args.out_dir)


if __name__ == "__main__":
    main()
