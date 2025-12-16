"""
Unified Metrics Debugger - Comprehensive debugging for financial metric extraction

This tool combines:
- Label matching (exact/partial matches for known metrics)
- Statement inspection (show ALL available facts in statements)
- Entity facts inspection (shares outstanding from Company Facts API)
- XBRL concept debugging

Usage:
    python debug_metrics.py MSFT                      # Debug all metrics
    python debug_metrics.py AAPL --metric fcf         # Debug specific metric
    python debug_metrics.py GOOGL --statement income  # Show all income statement facts
    python debug_metrics.py TSLA --filter share       # Filter facts by keyword
    python debug_metrics.py NFLX --entity-facts       # Show company facts API data
"""
import argparse
import pandas as pd
from typing import List, Dict, Optional
from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")


class MetricsDebugger:
    """Unified debugger for financial metric extraction issues."""

    # Define what we're looking for in each metric
    METRIC_PATTERNS = {
        'revenue': {
            'labels': ['Revenue', 'Contract Revenue', 'Total Revenue', 'Net Revenue', 'Sales Revenue'],
            'statement': 'income',
            'keywords': ['revenue', 'sales']
        },
        'gross_profit': {
            'labels': ['Gross Profit', 'Gross Margin', 'Total Gross Profit', 'Gross Income'],
            'statement': 'income',
            'keywords': ['gross', 'profit', 'margin']
        },
        'operating_income': {
            'labels': ['Operating Income', 'Operating Income (Loss)', 'Income from Operations',
                      'Income (Loss) from Operations', 'Operating Profit', 'Income from operations'],
            'statement': 'income',
            'keywords': ['operating', 'income', 'operations']
        },
        'net_income': {
            'labels': ['Net Income', 'Net Income (Loss)', 'Net Earnings', 'Profit or Loss',
                      'Net Income Attributable to Common'],
            'statement': 'income',
            'keywords': ['net', 'income', 'earnings', 'profit']
        },
        'cost_of_revenue': {
            'labels': ['Total Cost of Revenue', 'Cost of Revenue', 'Cost of Goods Sold',
                      'Cost of Sales', 'Cost of Goods and Services Sold'],
            'statement': 'income',
            'keywords': ['cost', 'revenue', 'goods', 'sales']
        },
        'operating_cash_flow': {
            'labels': ['Net Cash from Operating Activities', 'Operating Cash Flow',
                      'Cash from Operations', 'Net Cash from Operating',
                      'Net Cash Provided by Operating Activities',
                      'Cash Flow from Operations'],
            'statement': 'cashflow',
            'keywords': ['cash', 'operating', 'activities']
        },
        'fcf': {
            'labels': ['Free Cash Flow', 'Unlevered Free Cash Flow', 'Free Cash Flow Before Dividends'],
            'statement': 'cashflow',
            'keywords': ['free', 'cash', 'flow']
        },
        'capex': {
            'labels': ['Capital Expenditures', 'Property, Plant and Equipment',
                      'Payments to Acquire Property', 'Acquisitions of Property',
                      'Capex', 'Payments for Property, Plant and Equipment',
                      'Purchases of Property, Plant and Equipment',
                      'Additions to Property and Equipment',
                      'Payments to Acquire Property and Equipment'],
            'statement': 'cashflow',
            'keywords': ['capital', 'expenditure', 'property', 'plant', 'equipment', 'acquire', 'payments']
        },
        'total_assets': {
            'labels': ['Total Assets', 'Assets'],
            'statement': 'balance',
            'keywords': ['total', 'assets']
        },
        'total_liabilities': {
            'labels': ['Total Liabilities', 'Liabilities'],
            'statement': 'balance',
            'keywords': ['total', 'liabilities']
        },
        'stockholders_equity': {
            'labels': ["Total Stockholders' Equity", 'Stockholders Equity', 'Shareholders Equity',
                      'Total Equity', 'Equity', 'Total Shareholders Equity'],
            'statement': 'balance',
            'keywords': ['equity', 'stockholders', 'shareholders']
        },
        'shares_outstanding': {
            'labels': ['Common Stock, Shares Outstanding', 'Shares Outstanding',
                      'Common Shares Outstanding', 'Outstanding Shares'],
            'statement': 'balance',
            'keywords': ['shares', 'outstanding', 'common', 'stock']
        }
    }

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.company = Company(ticker)
        self.filing = None
        self.financials = self._get_financials()

    def _get_financials(self):
        """Get financials, filtering out amendments."""
        filings = self.company.get_filings(form="10-K", amendments=False)
        if not filings or len(filings) == 0:
            return None

        # latest(1) returns a single filing, not a list
        self.filing = filings.latest(1)
        if hasattr(self.filing, 'obj'):
            tenk = self.filing.obj()
            return tenk.financials if hasattr(tenk, 'financials') else None
        return None

    def get_statement_labels(self, statement_type: str) -> Optional[pd.DataFrame]:
        """Get all labels from a statement."""
        if not self.financials:
            return None

        if statement_type == 'income':
            stmt = self.financials.income_statement()
        elif statement_type == 'balance':
            stmt = self.financials.balance_sheet()
        elif statement_type == 'cashflow':
            stmt = self.financials.cashflow_statement()
        else:
            return None

        if stmt is None:
            return None

        try:
            df = stmt.render(standard=True).to_dataframe()
            return df
        except:
            return None

    def show_all_facts(self, statement_type: str = 'all', filter_keyword: str = None):
        """Show ALL facts in statements with their values and concepts."""

        statements = {
            'income': 'INCOME STATEMENT',
            'balance': 'BALANCE SHEET',
            'cashflow': 'CASH FLOW STATEMENT'
        }

        if statement_type == 'all':
            for stmt_type in ['income', 'balance', 'cashflow']:
                self._show_statement_facts(stmt_type, statements[stmt_type], filter_keyword)
        else:
            self._show_statement_facts(statement_type, statements[statement_type], filter_keyword)

    def _show_statement_facts(self, statement_type: str, title: str, filter_keyword: str = None):
        """Show facts from a specific statement."""
        df = self.get_statement_labels(statement_type)
        if df is None or df.empty:
            print(f"❌ Could not load {statement_type} statement\n")
            return

        print(f"\n{'=' * 80}")
        print(f"{title} ({self.ticker})")
        if filter_keyword:
            print(f"Filter: '{filter_keyword}'")
        print('=' * 80)

        # Filter if keyword provided
        if filter_keyword:
            df = df[df['label'].str.contains(filter_keyword, case=False, na=False)]
            if df.empty:
                print(f"No facts matching '{filter_keyword}'\n")
                return

        # Get latest period column
        period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
        period_col = period_cols[0] if period_cols else None

        facts_shown = 0
        for idx, row in df.iterrows():
            label = row['label']
            concept = row.get('concept', 'N/A')

            # Show value if available
            if period_col and period_col in row:
                val = row[period_col]
                if pd.notna(val) and val != '':
                    try:
                        # Format numbers nicely
                        if isinstance(val, (int, float)):
                            val_str = f"{val:,.0f}"
                        else:
                            val_str = str(val)
                    except:
                        val_str = str(val)

                    print(f"📊 {label}")
                    print(f"   └─ Concept: {concept}")
                    print(f"   └─ Value: {val_str}")
                else:
                    print(f"📊 {label}")
                    print(f"   └─ Concept: {concept}")
            else:
                print(f"📊 {label}")
                print(f"   └─ Concept: {concept}")

            print()
            facts_shown += 1

        print(f"Total facts shown: {facts_shown}\n")

    def show_entity_facts(self, filter_keyword: str = None):
        """Show facts from Company Facts API (shares outstanding, etc)."""
        print(f"\n{'=' * 80}")
        print(f"ENTITY FACTS - Company Facts API ({self.ticker})")
        print('=' * 80)

        try:
            facts = self.company.get_facts()

            # Share-related concepts to check
            share_concepts = [
                'us-gaap:CommonStockSharesOutstanding',
                'us-gaap:CommonStockSharesIssued',
                'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic',
                'us-gaap:WeightedAverageNumberOfSharesOutstandingDiluted',
                'us-gaap:CommonStockSharesAuthorized',
                'us-gaap:StockholdersEquity',
                'us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'
            ]

            facts_found = 0

            for concept in share_concepts:
                # Apply filter if specified
                if filter_keyword and filter_keyword.lower() not in concept.lower():
                    continue

                try:
                    # Try multiple query strategies
                    result = None
                    query_type = None

                    # Strategy 1: Latest without filtering by frequency
                    try:
                        result = facts.query().by_concept(concept).latest(1).execute()
                        query_type = "latest (any frequency)"
                    except:
                        pass

                    # Strategy 2: Try annual if latest didn't work
                    if not result or len(result) == 0:
                        try:
                            result = facts.query().by_concept(concept).annual().latest(1).execute()
                            query_type = "annual"
                        except:
                            pass

                    # Strategy 3: Try quarterly
                    if not result or len(result) == 0:
                        try:
                            result = facts.query().by_concept(concept).quarterly().latest(1).execute()
                            query_type = "quarterly"
                        except:
                            pass

                    if result and len(result) > 0:
                        fact = result[0]
                        value_str = f"{fact.numeric_value:,.0f}" if fact.numeric_value else "N/A"
                        date_str = fact.end_date if hasattr(fact, 'end_date') else "N/A"

                        print(f"📌 {concept}")
                        print(f"   └─ Value: {value_str}")
                        print(f"   └─ Date: {date_str}")
                        print(f"   └─ Query: {query_type}")
                        print()
                        facts_found += 1
                except Exception as e:
                    # Show error for debugging
                    print(f"⚠️  {concept}: {str(e)[:100]}")
                    pass

            if facts_found == 0:
                print("⚠️  No share-related facts found in Entity Facts API\n")
            else:
                print(f"Total entity facts found: {facts_found}\n")

        except Exception as e:
            print(f"❌ Error accessing entity facts: {e}\n")

    def debug_metric(self, metric: str):
        """Debug why a specific metric isn't extracting."""
        if metric not in self.METRIC_PATTERNS:
            print(f"❌ Unknown metric: {metric}")
            print(f"Available metrics: {', '.join(self.METRIC_PATTERNS.keys())}")
            return

        patterns = self.METRIC_PATTERNS[metric]
        statement_type = patterns['statement']
        target_labels = patterns['labels']
        keywords = patterns['keywords']

        print(f"\n{'=' * 80}")
        print(f"DEBUGGING METRIC: {metric.upper()} ({self.ticker})")
        print(f"{'=' * 80}")
        print(f"Statement: {statement_type}")
        print(f"Target labels: {target_labels[:3]}... ({len(target_labels)} total)")
        print(f"Keywords: {keywords}")

        # Get statement data
        df = self.get_statement_labels(statement_type)
        if df is None or df.empty:
            print(f"\n❌ ERROR: Could not load {statement_type} statement")
            return

        # Check for exact matches
        print(f"\n{'=' * 80}")
        print("EXACT MATCHES:")
        print('=' * 80)
        exact_matches = df[df['label'].isin(target_labels)]
        if not exact_matches.empty:
            for idx, row in exact_matches.iterrows():
                print(f"✅ FOUND: '{row['label']}'")
                print(f"   Concept: {row['concept']}")

                # Show value if available
                period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                if period_cols:
                    val = row[period_cols[0]]
                    if pd.notna(val):
                        print(f"   Value: {val:,.0f}" if isinstance(val, (int, float)) else f"   Value: {val}")
                print()
        else:
            print("❌ No exact matches found\n")

        # Check for partial matches
        print(f"{'=' * 80}")
        print("PARTIAL MATCHES (keyword search):")
        print('=' * 80)

        keyword_pattern = '|'.join(keywords)
        partial_matches = df[df['label'].str.contains(keyword_pattern, case=False, na=False, regex=True)]

        if not partial_matches.empty:
            print(f"Found {len(partial_matches)} potential matches:\n")
            for idx, row in partial_matches.head(10).iterrows():
                label = row['label']
                similarity_score = sum(kw in label.lower() for kw in keywords) / len(keywords)

                status = "🟢 HIGH" if similarity_score >= 0.5 else "🟡 MEDIUM" if similarity_score >= 0.3 else "⚪ LOW"
                print(f"{status} '{label}'")
                print(f"       Concept: {row['concept']}")

                # Show value
                period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                if period_cols:
                    val = row[period_cols[0]]
                    if pd.notna(val):
                        val_str = f"{val:,.0f}" if isinstance(val, (int, float)) else str(val)
                        print(f"       Value: {val_str}")
                print()
        else:
            print("❌ No partial matches found\n")

        # Suggest additions
        print(f"{'=' * 80}")
        print("SUGGESTED LABELS TO ADD:")
        print('=' * 80)

        if not partial_matches.empty:
            existing_labels_lower = [lbl.lower() for lbl in target_labels]
            new_suggestions = []

            for label in partial_matches['label'].unique():
                if label.lower() not in existing_labels_lower:
                    new_suggestions.append(label)

            if new_suggestions:
                print("Consider adding these to the extraction pattern:\n")
                for label in new_suggestions[:5]:
                    print(f"  '{label}',")
                print()
            else:
                print("✅ All relevant labels already covered\n")
        else:
            print("⚠️  No suggestions available\n")

    def debug_all_metrics(self):
        """Quick summary of all metrics."""
        print(f"\n{'=' * 80}")
        print(f"METRIC EXTRACTION SUMMARY ({self.ticker})")
        print('=' * 80)

        if self.filing:
            print(f"Filing: {self.filing.form} - {self.filing.filing_date}")
            print('=' * 80)

        results = {}

        for metric_name, patterns in self.METRIC_PATTERNS.items():
            statement_type = patterns['statement']
            target_labels = patterns['labels']

            df = self.get_statement_labels(statement_type)
            if df is None:
                results[metric_name] = '❌ Statement unavailable'
                continue

            # Check if any label matches
            exact_matches = df[df['label'].isin(target_labels)]
            if not exact_matches.empty:
                results[metric_name] = f'✅ Found: {exact_matches.iloc[0]["label"]}'
            else:
                # Check for partial match
                keyword_pattern = '|'.join(patterns['keywords'])
                partial_matches = df[df['label'].str.contains(keyword_pattern, case=False, na=False, regex=True)]

                if not partial_matches.empty:
                    best_match = partial_matches.iloc[0]['label']
                    results[metric_name] = f'⚠️  Partial: {best_match}'
                else:
                    results[metric_name] = '❌ Not found'

        # Print summary
        print()
        for metric, status in results.items():
            print(f"{metric:25s}: {status}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Unified debugger for financial metric extraction',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python debug_metrics.py MSFT                      # Summary of all metrics
  python debug_metrics.py AAPL --metric fcf         # Debug specific metric
  python debug_metrics.py GOOGL --facts income      # Show all income facts
  python debug_metrics.py TSLA --filter share       # Filter facts by keyword
  python debug_metrics.py NFLX --entity-facts       # Show Company Facts API data
        """
    )

    parser.add_argument('ticker', help='Company ticker symbol')
    parser.add_argument('--metric', help='Debug specific metric (fcf, capex, gross_profit, etc.)')
    parser.add_argument('--facts', choices=['income', 'balance', 'cashflow', 'all'],
                       help='Show ALL facts in statement(s)')
    parser.add_argument('--filter', help='Filter facts by keyword')
    parser.add_argument('--entity-facts', action='store_true',
                       help='Show entity facts from Company Facts API')
    parser.add_argument('--all', action='store_true', help='Full debug: all metrics + all facts')

    args = parser.parse_args()

    debugger = MetricsDebugger(args.ticker)

    if args.all:
        # Comprehensive debug
        debugger.debug_all_metrics()
        debugger.show_all_facts('all', args.filter)
        debugger.show_entity_facts(args.filter)
    elif args.metric:
        debugger.debug_metric(args.metric)
    elif args.facts:
        debugger.show_all_facts(args.facts, args.filter)
    elif args.entity_facts:
        debugger.show_entity_facts(args.filter)
    else:
        # Default: show summary
        debugger.debug_all_metrics()


if __name__ == "__main__":
    main()
