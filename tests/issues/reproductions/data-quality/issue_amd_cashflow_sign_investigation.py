"""
AMD Cashflow Sign Investigation - All 10-K filings from 2022-2025.

Investigates whether the preferred_sign mechanism correctly aligns with
calculation linkbase weights in AMD's cash flow statement across years.

IMPORTANT ARCHITECTURAL NOTE:
The presentation linkbase hierarchy and the calculation linkbase hierarchy
are DIFFERENT. For cashflow statements:
- Presentation: NetIncomeLoss is a child of the *abstract* section header
  (e.g., NetCashProvidedByUsedInOperatingActivitiesContinuingOperationsAbstract),
  not a direct child of the subtotal concept.
- Calculation: NetIncomeLoss IS a direct child of the subtotal concept
  (us-gaap_NetCashProvidedByUsedInOperatingActivities).

This means we MUST use the calculation tree to enumerate children for the
subtotal verification, not the parent_concept column from the DataFrame.

For each 10-K (FY2022, FY2023, FY2024, FY2025):
1. Get raw DataFrame (no presentation transformation)
2. Find operating cashflow subtotal concept
3. Identify children via the CALCULATION linkbase
4. For each child: look up its raw value, preferred_sign (from df), and
   calc weight (from tree)
5. Sum children using calc weights; compare to subtotal's own raw value
6. Also sum children using preferred_sign; compare to subtotal
7. Report discrepancies per concept

Checks for:
- Concepts where calc weight=-1 but no negated preferredLabel (sign not
  flipped in display but should subtract from operating CF)
- Concepts where preferredLabel is absent entirely (preferred_sign=None,
  no transformation applied at all)
- Pattern changes between filing years (post-Xilinx acquisition effects)

Usage:
    python tests/issues/reproductions/data-quality/issue_amd_cashflow_sign_investigation.py

Requires network access to SEC EDGAR.
"""

import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

import edgar
edgar.set_identity("research@university.edu")

import pandas as pd
from edgar import Company
from edgar.xbrl.xbrl import XBRL

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

AMD_TICKER = "AMD"
TARGET_YEARS = [2022, 2023, 2024, 2025]

# Operating cashflow subtotal concept variants (preferred order)
OPERATING_CF_CONCEPTS = [
    "us-gaap_NetCashProvidedByUsedInOperatingActivities",
    "us-gaap_NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]

# Tolerance for "match" check (in dollars; $1,000 = rounding only)
MATCH_TOLERANCE = 1_000


def get_period_columns(df: pd.DataFrame) -> list:
    """Return columns that represent period end dates (YYYY-MM-DD format)."""
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    return [col for col in df.columns if date_pattern.match(str(col))]


def find_subtotal_row(df: pd.DataFrame, candidates: list) -> pd.Series | None:
    """Find the operating CF subtotal row from a list of candidate concept names."""
    for concept in candidates:
        rows = df[df['concept'] == concept]
        if not rows.empty:
            return rows.iloc[0]
    return None


def find_cf_calc_role(xbrl: XBRL) -> tuple[str, object] | tuple[None, None]:
    """
    Return (role_uri, CalculationTree) for the primary cash flow statement
    calculation role.

    Heuristic: find the role whose definition or URI contains 'cashflow' or
    'cash' and has the most nodes.
    """
    if not hasattr(xbrl, 'calculation_trees') or not xbrl.calculation_trees:
        return None, None

    best_role = None
    best_tree = None
    best_score = -1

    for role, tree in xbrl.calculation_trees.items():
        role_lower = role.lower()
        defn_lower = tree.definition.lower()
        if ('cashflow' in role_lower or 'cashflow' in defn_lower or
                'cash flow' in defn_lower or 'cash flows' in defn_lower):
            score = len(tree.all_nodes)
            if score > best_score:
                best_score = score
                best_role = role
                best_tree = tree

    return best_role, best_tree


def find_cf_presentation_role(xbrl: XBRL) -> str | None:
    """Return the presentation role URI for the Cash Flow Statement."""
    if not hasattr(xbrl, 'presentation_trees'):
        return None
    for role in xbrl.presentation_trees:
        if 'cashflow' in role.lower() or 'cash' in role.lower():
            defn = xbrl.presentation_trees[role].definition.lower()
            if 'cashflow' in defn or 'cash flow' in defn or 'cash flows' in defn:
                return role
    # Broader fallback
    for role in xbrl.presentation_trees:
        if 'cash' in role.lower():
            return role
    return None


def get_preferred_label_raw(xbrl: XBRL, concept: str, cf_role: str | None) -> str | None:
    """
    Get the raw preferredLabel URI for a concept from the presentation linkbase.

    Searches the CF-specific role first, then all other roles.
    Returns the URI string (e.g., 'http://www.xbrl.org/2003/role/negatedLabel')
    or None if no preferredLabel is specified.
    """
    if not hasattr(xbrl, 'presentation_trees') or not xbrl.presentation_trees:
        return None

    concept_variants = [
        concept,
        concept.replace(':', '_'),
        concept.replace('_', ':'),
    ]

    roles_to_search = []
    if cf_role and cf_role in xbrl.presentation_trees:
        roles_to_search.append(cf_role)
    roles_to_search.extend([r for r in xbrl.presentation_trees if r != cf_role])

    for role in roles_to_search:
        tree = xbrl.presentation_trees[role]
        for cv in concept_variants:
            if cv in tree.all_nodes:
                return tree.all_nodes[cv].preferred_label
    return None


def lookup_in_df(df: pd.DataFrame, calc_concept_id: str, period_col: str) -> dict:
    """
    Find a concept's row in the statement DataFrame.

    calc_concept_id uses underscore notation (e.g. us-gaap_NetIncomeLoss).
    The DataFrame uses the same notation. Returns a dict with the row's
    metadata, or defaults if not found.
    """
    # Try exact match first, then colon variant
    variants = [
        calc_concept_id,
        calc_concept_id.replace('_', ':', 1),  # us-gaap:NetIncomeLoss
    ]
    for v in variants:
        rows = df[df['concept'] == v]
        if not rows.empty:
            row = rows.iloc[0]
            return {
                'found': True,
                'concept': row['concept'],
                'label': row.get('label', ''),
                'raw_value': row.get(period_col),
                'preferred_sign': row.get('preferred_sign'),
                'weight_df': row.get('weight'),
                'balance': row.get('balance'),
            }
    return {
        'found': False,
        'concept': calc_concept_id,
        'label': '',
        'raw_value': None,
        'preferred_sign': None,
        'weight_df': None,
        'balance': None,
    }


def analyze_cashflow_signs(xbrl: XBRL, filing_year: int, filing_label: str) -> dict:
    """
    Perform sign analysis on the cashflow statement for one filing.

    KEY DESIGN: Uses the CALCULATION linkbase to enumerate the children of
    the operating CF subtotal, not the presentation parent_concept column.
    This is correct because in the presentation hierarchy, NetIncomeLoss (and
    other items) are children of abstract section headers, not the subtotal.
    In the calculation hierarchy they are direct children of the subtotal.

    Returns a result dict:
        filing_label, filing_year, status, error,
        operating_cf_concept, reported_value,
        calc_weighted_sum, calc_match, calc_discrepancy,
        pref_sign_sum, pref_sign_match, pref_sign_discrepancy,
        children: list of per-concept dicts,
        no_preferred_label: list of concepts with absent preferredLabel
    """
    result = {
        'filing_label': filing_label,
        'filing_year': filing_year,
        'status': 'ok',
        'error': None,
        'operating_cf_concept': None,
        'reported_value': None,
        'calc_weighted_sum': None,
        'calc_match': None,
        'calc_discrepancy': None,
        'pref_sign_sum': None,
        'pref_sign_match': None,
        'pref_sign_discrepancy': None,
        'children': [],
        'no_preferred_label': [],
    }

    try:
        cf_stmt = xbrl.statements.cashflow_statement()
        if cf_stmt is None:
            result['status'] = 'error'
            result['error'] = 'cashflow_statement() returned None'
            return result

        # Raw DataFrame - NO presentation transformation
        df = cf_stmt.to_dataframe()
        if df is None or df.empty:
            result['status'] = 'error'
            result['error'] = 'to_dataframe() returned empty DataFrame'
            return result

        period_cols = get_period_columns(df)
        if not period_cols:
            result['status'] = 'error'
            result['error'] = 'No period columns found in DataFrame'
            return result

        # Use the first (most recent) period column for verification
        primary_period_col = period_cols[0]

        # Find operating CF subtotal
        subtotal_row = find_subtotal_row(df, OPERATING_CF_CONCEPTS)
        if subtotal_row is None:
            result['status'] = 'error'
            result['error'] = (
                f'Operating CF subtotal not found. '
                f'Tried: {OPERATING_CF_CONCEPTS}. '
                f'Available: {df["concept"].tolist()[:20]}'
            )
            return result

        op_concept = subtotal_row['concept']
        reported_val = subtotal_row[primary_period_col]
        result['operating_cf_concept'] = op_concept
        result['reported_value'] = reported_val

        # Find CF calculation tree
        cf_calc_role, cf_calc_tree = find_cf_calc_role(xbrl)
        if cf_calc_tree is None:
            result['status'] = 'error'
            result['error'] = 'No cash flow calculation tree found'
            return result

        # Find operating CF subtotal node in calculation tree
        op_concept_variants = [
            op_concept,
            op_concept.replace(':', '_'),
            op_concept.replace('_', ':'),
        ]
        op_calc_node = None
        for variant in op_concept_variants:
            if variant in cf_calc_tree.all_nodes:
                op_calc_node = cf_calc_tree.all_nodes[variant]
                break

        if op_calc_node is None:
            result['status'] = 'warning'
            result['error'] = (
                f'Operating CF subtotal "{op_concept}" not found in calculation tree. '
                f'Tree has {len(cf_calc_tree.all_nodes)} nodes. '
                f'Cannot verify calculation.'
            )
            return result

        # Process each child from the calculation tree
        cf_pres_role = find_cf_presentation_role(xbrl)
        children_data = []
        calc_weighted_sum = 0.0
        pref_sign_sum = 0.0

        for child_id in op_calc_node.children:
            child_calc_node = cf_calc_tree.all_nodes.get(child_id)
            calc_weight = child_calc_node.weight if child_calc_node else None

            # Look up this concept in the DataFrame
            df_info = lookup_in_df(df, child_id, primary_period_col)
            raw_val = df_info['raw_value']
            preferred_sign = df_info['preferred_sign']

            # Get the raw preferredLabel URI from the presentation linkbase
            raw_preferred_label = get_preferred_label_raw(xbrl, child_id, cf_pres_role)
            preferred_label_absent = raw_preferred_label is None

            # Compute contributions
            if pd.notna(raw_val):
                raw_float = float(raw_val)
                # Calculation-weighted contribution (ground truth for matching)
                calc_contribution = raw_float * calc_weight if calc_weight is not None else raw_float
                calc_weighted_sum += calc_contribution

                # preferred_sign contribution (what edgartools applies in display)
                if pd.notna(preferred_sign):
                    pref_contribution = raw_float * float(preferred_sign)
                else:
                    pref_contribution = raw_float  # No transformation
                pref_sign_sum += pref_contribution
            else:
                calc_contribution = None
                pref_contribution = None

            # Detect alignment issues
            alignment_issues = []

            eff_calc_weight = calc_weight  # Already from calculation tree

            # Issue A: calc weight=-1 but preferred_sign is None
            # → concept subtracts in calculation but displayed without negation
            if eff_calc_weight is not None and eff_calc_weight < 0 and pd.isna(preferred_sign):
                alignment_issues.append(
                    'MISSING_NEGATION: calc_weight<0 but preferred_sign=None '
                    '→ display shows raw value; subtraction requires negation'
                )

            # Issue B: calc weight=-1 but preferred_sign=+1
            # → concept subtracts in calculation but display adds (no negation)
            if eff_calc_weight is not None and eff_calc_weight < 0 and preferred_sign == 1.0:
                alignment_issues.append(
                    'SIGN_MISMATCH: calc_weight<0 but preferred_sign=+1 '
                    '→ display does NOT negate; should be showing as outflow'
                )

            # Issue C: calc weight=+1 but preferred_sign=-1
            # → concept adds in calculation but display negates it
            if eff_calc_weight is not None and eff_calc_weight > 0 and preferred_sign == -1.0:
                alignment_issues.append(
                    'OVER_NEGATION: calc_weight>0 but preferred_sign=-1 '
                    '→ display negates value that should be additive'
                )

            # Issue D: preferredLabel present but it's a standard (non-negating) label
            # yet calc_weight=-1, indicating SEC filer forgot to use negatedLabel
            if (eff_calc_weight is not None and eff_calc_weight < 0 and
                    raw_preferred_label is not None and
                    'negated' not in raw_preferred_label.lower()):
                alignment_issues.append(
                    f'PRESENTATION_NOT_NEGATED: calc_weight<0 but preferredLabel='
                    f'"{raw_preferred_label}" is not a negated role '
                    f'→ edgartools preferred_sign=+1, item shown positive'
                )

            children_data.append({
                'concept': child_id,
                'label': df_info['label'],
                'found_in_df': df_info['found'],
                'raw_value': raw_val,
                'preferred_sign': preferred_sign,
                'pref_contribution': pref_contribution,
                'calc_weight': calc_weight,
                'calc_contribution': calc_contribution,
                'balance': df_info['balance'],
                'preferred_label_raw': raw_preferred_label,
                'preferred_label_absent': preferred_label_absent,
                'alignment_issues': alignment_issues,
            })

        result['children'] = children_data
        result['calc_weighted_sum'] = calc_weighted_sum
        result['pref_sign_sum'] = pref_sign_sum

        # Calculate discrepancies
        if pd.notna(reported_val):
            result['calc_discrepancy'] = abs(reported_val - calc_weighted_sum)
            result['calc_match'] = result['calc_discrepancy'] < MATCH_TOLERANCE
            result['pref_sign_discrepancy'] = abs(reported_val - pref_sign_sum)
            result['pref_sign_match'] = result['pref_sign_discrepancy'] < MATCH_TOLERANCE

        # List concepts with no preferredLabel
        result['no_preferred_label'] = [
            c for c in children_data if c['preferred_label_absent']
        ]

    except Exception as e:
        import traceback
        result['status'] = 'error'
        result['error'] = f'{type(e).__name__}: {e}\n{traceback.format_exc()}'

    return result


def print_filing_report(result: dict) -> None:
    """Pretty-print the sign analysis results for one filing."""
    yr = result['filing_year']
    label = result['filing_label']
    sep = '─' * 72

    print(f"\n{sep}")
    print(f"  AMD 10-K FY{yr}  |  {label}")
    print(sep)

    if result['status'] == 'error':
        print(f"  STATUS: ERROR — {result['error']}")
        return

    if result['status'] == 'warning':
        print(f"  STATUS: WARNING — {result['error']}")

    op_concept = result['operating_cf_concept']
    reported = result['reported_value']
    calc_sum = result['calc_weighted_sum']
    pref_sum = result['pref_sign_sum']

    print(f"  Operating CF subtotal concept : {op_concept}")
    if pd.notna(reported):
        print(f"  Reported subtotal (raw value) : {reported:>22,.0f}")
    print(f"  Calc-weighted sum             : {calc_sum:>22,.0f}"
          f"  → {'MATCH' if result['calc_match'] else 'MISMATCH'}")
    print(f"  preferred_sign sum            : {pref_sum:>22,.0f}"
          f"  → {'MATCH' if result['pref_sign_match'] else 'MISMATCH'}")

    if not result['calc_match'] and result['calc_discrepancy'] is not None:
        print(f"  Calc discrepancy              : {result['calc_discrepancy']:>22,.0f}")
    if not result['pref_sign_match'] and result['pref_sign_discrepancy'] is not None:
        print(f"  pref_sign discrepancy         : {result['pref_sign_discrepancy']:>22,.0f}")

    print()
    # Header for children table
    hdr = f"  {'Concept (short)':<42} {'raw_val':>15} {'p_sign':>7} {'c_wt':>5}"
    print(hdr)
    print(f"  {'─'*42} {'─'*15} {'─'*7} {'─'*5}")

    for c in result['children']:
        raw_val = c['raw_value']
        pref_sign = c['preferred_sign']
        c_wt = c['calc_weight']

        val_str = f"{raw_val:>15,.0f}" if pd.notna(raw_val) else f"{'N/A':>15}"
        sign_str = str(int(pref_sign)) if pd.notna(pref_sign) else 'None'
        wt_str = str(int(c_wt)) if c_wt is not None else 'N/A'

        # Shorten concept name for display
        short_concept = c['concept']
        if '_' in short_concept:
            # Take the part after the namespace prefix
            short_concept = short_concept.split('_', 1)[-1]
        if len(short_concept) > 40:
            short_concept = short_concept[:37] + '...'

        not_found = '' if c['found_in_df'] else ' [NOT IN DF]'
        print(f"  {short_concept:<42} {val_str} {sign_str:>7} {wt_str:>5}{not_found}")

        # Print issues indented
        for issue in c['alignment_issues']:
            print(f"    *** {issue}")

    # Summary
    all_issues = []
    for c in result['children']:
        for issue in c['alignment_issues']:
            all_issues.append((c['concept'], issue))

    no_pl = result.get('no_preferred_label', [])

    print()
    if all_issues:
        print(f"  SIGN ALIGNMENT ISSUES ({len(all_issues)}):")
        for concept, issue in all_issues:
            short = concept.split('_', 1)[-1] if '_' in concept else concept
            print(f"    [{short}]: {issue}")
    else:
        print("  No sign alignment issues detected.")

    if no_pl:
        print(f"\n  Concepts with NO preferredLabel in presentation linkbase ({len(no_pl)}):")
        for c in no_pl:
            short = c['concept'].split('_', 1)[-1] if '_' in c['concept'] else c['concept']
            print(f"    {short:<45} calc_wt={c['calc_weight']}, raw_val={c['raw_value']}")


def compare_across_years(results: list) -> None:
    """Print cross-year comparison of patterns."""
    print("\n" + "=" * 72)
    print("  CROSS-YEAR COMPARISON (2022-2025)")
    print("=" * 72)

    # Build per-year concept sets
    by_year = {}
    for r in results:
        yr = r['filing_year']
        by_year[yr] = {
            'concepts': set(c['concept'] for c in r['children']),
            'issue_concepts': set(c['concept'] for c in r['children'] if c['alignment_issues']),
            'no_pl_concepts': set(c['concept'] for c in r.get('no_preferred_label', [])),
            'match': r['calc_match'],
            'pref_match': r['pref_sign_match'],
        }

    years = sorted(by_year.keys())

    print("\n  Subtotal verification by year:")
    print(f"  {'Year':<6} {'Calc match':<12} {'prefSign match':<16} {'# children':<12} {'# issues'}")
    print(f"  {'─'*6} {'─'*12} {'─'*16} {'─'*12} {'─'*8}")
    for r in results:
        yr = r['filing_year']
        n_children = len(r['children'])
        n_issues = sum(len(c['alignment_issues']) for c in r['children'])
        calc_ok = 'YES' if r['calc_match'] else ('N/A' if r['calc_match'] is None else 'NO')
        pref_ok = 'YES' if r['pref_sign_match'] else ('N/A' if r['pref_sign_match'] is None else 'NO')
        print(f"  {yr:<6} {calc_ok:<12} {pref_ok:<16} {n_children:<12} {n_issues}")

    if len(years) >= 2:
        print("\n  Concept-level changes vs first year (post-Xilinx acquisition signals):")
        first_yr = years[0]
        first_concepts = by_year.get(first_yr, {}).get('concepts', set())

        for yr in years[1:]:
            curr_concepts = by_year.get(yr, {}).get('concepts', set())
            new_concepts = curr_concepts - first_concepts
            dropped = first_concepts - curr_concepts

            if new_concepts:
                print(f"\n  FY{yr} — {len(new_concepts)} NEW concept(s) vs FY{first_yr}:")
                for c in sorted(new_concepts):
                    short = c.split('_', 1)[-1] if '_' in c else c
                    print(f"    + {short}")

            if dropped:
                print(f"\n  FY{yr} — {len(dropped)} DROPPED concept(s) vs FY{first_yr}:")
                for c in sorted(dropped):
                    short = c.split('_', 1)[-1] if '_' in c else c
                    print(f"    - {short}")

            if not new_concepts and not dropped:
                print(f"\n  FY{yr}: Same operating CF children as FY{first_yr}")

        # Stable missing preferred_label concepts
        print("\n  Concepts consistently missing preferredLabel (all years):")
        no_pl_all_years = None
        for yr in years:
            no_pl = by_year.get(yr, {}).get('no_pl_concepts', set())
            if no_pl_all_years is None:
                no_pl_all_years = no_pl
            else:
                no_pl_all_years = no_pl_all_years & no_pl
        if no_pl_all_years:
            for c in sorted(no_pl_all_years):
                short = c.split('_', 1)[-1] if '_' in c else c
                print(f"    {short}")
        else:
            print("    None (or only in some years)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  AMD CASHFLOW SIGN INVESTIGATION")
    print("  10-K Filings: FY2022 through FY2025")
    print("=" * 72)
    print()
    print("  Sign system architecture:")
    print("  - preferredLabel: read from presentation linkbase arcs")
    print("    (parsers/presentation.py:118)")
    print("  - preferred_sign (-1/1/None): derived in xbrl.py:1055-1067")
    print("  - Applied at render time in rendering.py:1277-1296")
    print("  - Applied in DataFrame in statements.py:1231-1276 only when")
    print("    presentation=True")
    print("  - Calculation arc weight (+1/-1) is NOT used for sign flipping")
    print()

    amd = Company(AMD_TICKER)
    filings = amd.get_filings(form="10-K")

    # Filter to target years (period_of_report year)
    target_filings = []
    for filing in filings:
        period = str(filing.period_of_report)
        year = int(period[:4]) if period and len(period) >= 4 else None
        if year in TARGET_YEARS:
            target_filings.append((year, filing))

    print(f"  Found {len(target_filings)} AMD 10-K filing(s) for years {TARGET_YEARS}:")
    for year, filing in sorted(target_filings):
        print(f"    FY{year}: {filing.accession_no}  (period: {filing.period_of_report}, "
              f"filed: {filing.filing_date})")

    if not target_filings:
        print("  ERROR: No matching filings found for years 2022-2025.")
        sys.exit(1)

    # Sort by year ascending
    target_filings.sort(key=lambda x: x[0])

    all_results = []
    for year, filing in target_filings:
        label = f"{filing.accession_no} (filed {filing.filing_date})"
        print(f"\n  Loading XBRL for FY{year} ({filing.accession_no})...")
        try:
            xbrl = XBRL.from_filing(filing)
            result = analyze_cashflow_signs(xbrl, year, label)
        except Exception as e:
            import traceback
            result = {
                'filing_label': label,
                'filing_year': year,
                'status': 'error',
                'error': f'Failed to load XBRL: {type(e).__name__}: {e}',
                'operating_cf_concept': None,
                'reported_value': None,
                'calc_weighted_sum': None,
                'calc_match': None,
                'calc_discrepancy': None,
                'pref_sign_sum': None,
                'pref_sign_match': None,
                'pref_sign_discrepancy': None,
                'children': [],
                'no_preferred_label': [],
            }
        all_results.append(result)
        print_filing_report(result)

    compare_across_years(all_results)

    # Final verdict
    print("\n" + "=" * 72)
    print("  FINAL SUMMARY")
    print("=" * 72)
    total_issues = sum(
        sum(len(c['alignment_issues']) for c in r['children'])
        for r in all_results
    )
    failed_years = [r['filing_year'] for r in all_results if r['status'] == 'error']
    calc_mismatch = [r['filing_year'] for r in all_results if r['calc_match'] is False]
    pref_mismatch = [r['filing_year'] for r in all_results if r['pref_sign_match'] is False]

    print(f"  Filing years analyzed          : {[r['filing_year'] for r in all_results]}")
    print(f"  Errors (could not load)        : {failed_years}")
    print(f"  Calc-weighted sum mismatch     : {calc_mismatch}")
    print(f"  preferred_sign sum mismatch    : {pref_mismatch}")
    print(f"  Total sign alignment issues    : {total_issues}")

    if total_issues == 0 and not pref_mismatch and not failed_years:
        print("\n  RESULT: No sign issues detected across AMD 10-K filings 2022-2025.")
    elif pref_mismatch:
        print("\n  RESULT: preferred_sign sum does NOT match reported subtotal in some years.")
        print("  This means the display transformation does not reproduce the filed total.")
        print("  Root cause: concepts with calc_weight != preferred_sign direction.")
    else:
        print("\n  RESULT: Issues detected — see per-year reports above for details.")

    return all_results


if __name__ == "__main__":
    main()
