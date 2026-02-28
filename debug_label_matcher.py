"""
Label Matcher Debugger - Diagnose metric extraction issues

Usage:
    python debug_label_matcher.py AAPL
    python debug_label_matcher.py MSFT --metric fcf
    python debug_label_matcher.py GOOGL --statement income
"""
import argparse
import pandas as pd
from typing import List, Dict, Optional
from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")


class LabelMatcher:
    """Debug tool to identify label mismatches and suggest fixes."""

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
                      'Cash from Operations', 'Net Cash from Operating'],
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
                      'Additions to Property and Equipment'],
            'statement': 'cashflow',
            'keywords': ['capital', 'expenditure', 'property', 'plant', 'equipment', 'acquire']
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
                      'Total Equity', 'Equity'],
            'statement': 'balance',
            'keywords': ['equity', 'stockholders', 'shareholders']
        }
    }

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.company = Company(ticker)
        self.financials = self._get_financials()

    def _get_financials(self):
        """Get financials, filtering out amendments."""
        filings = self.company.get_filings(form="10-K", amendments=False)
        if not filings or len(filings) == 0:
            return None

        latest_filing = filings.latest(1)
        if hasattr(latest_filing, 'obj'):
            tenk = latest_filing.obj()
            return tenk.financials if hasattr(tenk, 'financials') else None
        else:
            return self.company.get_financials()

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

        if not stmt:
            return None

        try:
            df = stmt.render(standard=True).to_dataframe()
            return df
        except:
            return None

    def debug_metric(self, metric: str):
        """Debug why a specific metric isn't extracting."""
        if metric not in self.METRIC_PATTERNS:
            print(f"Unknown metric: {metric}")
            print(f"Available metrics: {', '.join(self.METRIC_PATTERNS.keys())}")
            return

        patterns = self.METRIC_PATTERNS[metric]
        statement_type = patterns['statement']
        target_labels = patterns['labels']
        keywords = patterns['keywords']

        print(f"\n{'=' * 80}")
        print(f"DEBUGGING: {metric.upper()} for {self.ticker}")
        print(f"{'=' * 80}")
        print(f"Statement: {statement_type}")
        print(f"Looking for labels: {target_labels[:3]}... ({len(target_labels)} total)")
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
                print(f"✓ FOUND: '{row['label']}'")
                print(f"  Concept: {row['concept']}")
                # Show value if available
                period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                if period_cols:
                    val = row[period_cols[0]]
                    print(f"  Value: {val}")
        else:
            print("❌ No exact matches found")

        # Check for partial matches
        print(f"\n{'=' * 80}")
        print("PARTIAL MATCHES (keyword search):")
        print('=' * 80)

        # Create keyword pattern
        keyword_pattern = '|'.join(keywords)
        partial_matches = df[df['label'].str.contains(keyword_pattern, case=False, na=False, regex=True)]

        if not partial_matches.empty:
            print(f"Found {len(partial_matches)} potential matches:\n")
            for idx, row in partial_matches.head(10).iterrows():
                label = row['label']
                # Check if this is close to what we want
                similarity_score = sum(kw in label.lower() for kw in keywords) / len(keywords)

                status = "🟢 HIGH" if similarity_score >= 0.5 else "🟡 MEDIUM" if similarity_score >= 0.3 else "⚪ LOW"
                print(f"{status} '{label}'")
                print(f"       Concept: {row['concept']}")

                # Show value
                period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                if period_cols:
                    val = row[period_cols[0]]
                    if pd.notna(val):
                        print(f"       Value: {val}")
                print()
        else:
            print("❌ No partial matches found")

        # Suggest additions
        print(f"\n{'=' * 80}")
        print("SUGGESTED ADDITIONS TO EXTRACTION PATTERNS:")
        print('=' * 80)

        if not partial_matches.empty:
            # Get unique labels not already in our patterns
            existing_labels_lower = [lbl.lower() for lbl in target_labels]
            new_suggestions = []

            for label in partial_matches['label'].unique():
                if label.lower() not in existing_labels_lower:
                    new_suggestions.append(label)

            if new_suggestions:
                print("Add these labels to the extraction pattern:\n")
                for label in new_suggestions[:5]:  # Top 5 suggestions
                    print(f"  '{label}',")
            else:
                print("✓ All relevant labels already in pattern")
        else:
            print("⚠️  No suggestions - may need manual inspection")

    def show_all_labels(self, statement_type: str = 'income', filter_keyword: str = None):
        """Show all labels in a statement, optionally filtered."""
        df = self.get_statement_labels(statement_type)
        if df is None or df.empty:
            print(f"❌ Could not load {statement_type} statement")
            return

        print(f"\n{'=' * 80}")
        print(f"{statement_type.upper()} STATEMENT - ALL LABELS ({self.ticker})")
        print('=' * 80)

        if filter_keyword:
            df = df[df['label'].str.contains(filter_keyword, case=False, na=False)]
            print(f"Filtered by keyword: '{filter_keyword}'")
            print('=' * 80)

        period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
        period_col = period_cols[0] if period_cols else None

        for idx, row in df.iterrows():
            label = row['label']
            concept = row['concept']

            # Show value if available
            if period_col:
                val = row[period_col]
                if pd.notna(val) and val != '':
                    print(f"{label}")
                    print(f"  └─ {concept} = {val}")
                else:
                    print(f"{label}")
                    print(f"  └─ {concept}")
            else:
                print(f"{label}")
                print(f"  └─ {concept}")
            print()

    def debug_all_metrics(self):
        """Debug all metrics to find any issues."""
        print(f"\n{'=' * 80}")
        print(f"COMPREHENSIVE METRIC DEBUGGING FOR {self.ticker}")
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
                results[metric_name] = f'✓ Found ({exact_matches.iloc[0]["label"]})'
            else:
                # Check for partial match
                keyword_pattern = '|'.join(patterns['keywords'])
                partial_matches = df[df['label'].str.contains(keyword_pattern, case=False, na=False, regex=True)]

                if not partial_matches.empty:
                    best_match = partial_matches.iloc[0]['label']
                    results[metric_name] = f'⚠️  Partial ({best_match})'
                else:
                    results[metric_name] = '❌ Not found'

        # Print summary
        print("\nMETRIC EXTRACTION SUMMARY:")
        print('-' * 80)
        for metric, status in results.items():
            print(f"{metric:30s}: {status}")


def main():
    parser = argparse.ArgumentParser(description='Debug financial metric label extraction')
    parser.add_argument('ticker', help='Company ticker symbol')
    parser.add_argument('--metric', help='Specific metric to debug (e.g., fcf, capex, gross_profit)')
    parser.add_argument('--statement', choices=['income', 'balance', 'cashflow'],
                       help='Show all labels in a statement')
    parser.add_argument('--filter', help='Filter labels by keyword')
    parser.add_argument('--all', action='store_true', help='Debug all metrics')

    args = parser.parse_args()

    matcher = LabelMatcher(args.ticker)

    if args.all:
        matcher.debug_all_metrics()
    elif args.metric:
        matcher.debug_metric(args.metric)
    elif args.statement:
        matcher.show_all_labels(args.statement, args.filter)
    else:
        # Default: debug all metrics
        matcher.debug_all_metrics()


if __name__ == "__main__":
    main()
