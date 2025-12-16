"""
Comprehensive Financial Metrics Extractor V2
Fixes:
1. Better FCF extraction
2. Shares outstanding debugging
3. Unit scaling (millions/billions)
4. Type safety
"""
import pandas as pd
from typing import Optional, Dict, List, Tuple
from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")


class FinancialMetricsExtractor:
    """Extract standardized financial metrics with proper unit handling."""

    def __init__(self, ticker: str, unit: str = 'millions'):
        """
        Initialize extractor.

        Args:
            ticker: Company ticker symbol
            unit: Display unit ('raw', 'thousands', 'millions', 'billions')
        """
        self.ticker = ticker
        self.company = Company(ticker)
        self.unit = unit
        self.scale_factor = {
            'raw': 1,
            'thousands': 1_000,
            'millions': 1_000_000,
            'billions': 1_000_000_000
        }[unit]

    def _to_float(self, value) -> Optional[float]:
        """Safely convert any value to float or None."""
        if value is None or (isinstance(value, str) and value.strip() == ''):
            return None
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def _scale_value(self, value: Optional[float]) -> Optional[float]:
        """Scale value to selected unit."""
        if value is None:
            return None
        return value / self.scale_factor

    def _extract_from_statement(self, statement, labels: List[str]) -> Optional[float]:
        """Extract from standardized rendered statement."""
        if not statement:
            return None

        try:
            df = statement.render(standard=True).to_dataframe()
            if df.empty:
                return None

            period_cols = [col for col in df.columns
                          if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
            if not period_cols:
                return None

            period_col = period_cols[0]

            for label in labels:
                # Exact match
                matches = df[df['label'] == label]
                if not matches.empty:
                    return self._to_float(matches.iloc[0][period_col])

                # Partial match
                matches = df[df['label'].str.contains(label, case=False, na=False, regex=False)]
                if not matches.empty:
                    return self._to_float(matches.iloc[0][period_col])

            return None
        except:
            return None

    def extract_annual_metrics(self) -> Dict:
        """Extract annual metrics with proper unit scaling."""
        # Filter out amendments
        filings = self.company.get_filings(form="10-K", amendments=False)
        if not filings or len(filings) == 0:
            return {}

        latest_filing = filings.latest(1)
        if hasattr(latest_filing, 'obj'):
            tenk = latest_filing.obj()
            financials = tenk.financials if hasattr(tenk, 'financials') else None
        else:
            financials = self.company.get_financials()

        if not financials:
            return {}

        metrics = {
            'ticker': self.ticker,
            'company_name': self.company.name,
            'period_type': 'annual',
            'unit': self.unit
        }

        # Extract raw values first
        raw_metrics = self._extract_raw_metrics(financials)

        # Scale all monetary values
        monetary_keys = [
            'revenue', 'gross_profit', 'operating_income', 'net_income',
            'free_cash_flow', 'capex', 'operating_cash_flow',
            'total_assets', 'total_liabilities', 'stockholders_equity',
            'current_assets', 'current_liabilities', 'cost_of_revenue'
        ]

        for key in monetary_keys:
            if key in raw_metrics:
                metrics[key] = self._scale_value(raw_metrics[key])

        # Per-share values stay as-is (already small)
        if 'eps' in raw_metrics:
            metrics['eps'] = raw_metrics['eps']
        if 'fcf_per_share' in raw_metrics:
            metrics['fcf_per_share'] = raw_metrics['fcf_per_share']

        # Ratios stay as-is (percentages)
        ratio_keys = ['gross_margin', 'operating_margin', 'net_margin',
                      'fcf_margin', 'roe', 'roic', 'current_ratio']
        for key in ratio_keys:
            if key in raw_metrics:
                metrics[key] = raw_metrics[key]

        # Shares outstanding (in actual shares, not scaled)
        if 'shares_outstanding' in raw_metrics:
            metrics['shares_outstanding'] = raw_metrics['shares_outstanding']

        return metrics

    def _extract_raw_metrics(self, financials) -> Dict:
        """Extract raw unscaled metrics."""
        metrics = {}

        # 1. Use helper methods
        metrics['revenue'] = self._to_float(financials.get_revenue())
        metrics['net_income'] = self._to_float(financials.get_net_income())

        # Operating cash flow - with fallback if helper returns empty string
        metrics['operating_cash_flow'] = self._to_float(financials.get_operating_cash_flow())
        if metrics['operating_cash_flow'] is None:
            # Fallback: extract directly from cash flow statement
            cf_stmt = financials.cashflow_statement()
            metrics['operating_cash_flow'] = self._extract_from_statement(
                cf_stmt, [
                    'Net Cash from Operating Activities',
                    'Net Cash Provided by Operating Activities',
                    'Cash from Operating Activities',
                    'Operating Cash Flow',
                    'Cash Flow from Operations'
                ]
            )

        # CapEx - with fallback for different label variations
        metrics['capex'] = self._to_float(financials.get_capital_expenditures())
        if metrics['capex'] is None:
            cf_stmt = financials.cashflow_statement()
            metrics['capex'] = self._extract_from_statement(
                cf_stmt, [
                    'Payments for Property, Plant and Equipment',  # MSFT, NFLX
                    'Capital Expenditures',
                    'Purchases of Property, Plant and Equipment',
                    'Additions to Property and Equipment',
                    'Payments to Acquire Property',
                    'Capital Additions'
                ]
            )

        # FCF - improved extraction
        metrics['free_cash_flow'] = self._extract_fcf(financials)

        metrics['total_assets'] = self._to_float(financials.get_total_assets())
        metrics['total_liabilities'] = self._to_float(financials.get_total_liabilities())
        metrics['stockholders_equity'] = self._to_float(financials.get_stockholders_equity())
        metrics['current_assets'] = self._to_float(financials.get_current_assets())
        metrics['current_liabilities'] = self._to_float(financials.get_current_liabilities())

        # 2. Fallback extraction
        income_stmt = financials.income_statement()

        # Cost of Revenue first
        metrics['cost_of_revenue'] = self._extract_from_statement(
            income_stmt, [
                'Total Cost of Revenue',
                'Cost of Revenue',
                'Cost of Goods Sold',
                'Cost of Sales',
                'Cost of Goods and Services Sold'
            ]
        )

        # Gross Profit (extract or calculate)
        metrics['gross_profit'] = self._extract_from_statement(
            income_stmt, [
                'Gross Profit',
                'Gross Margin',
                'Total Gross Profit',
                'Gross Income'
            ]
        )

        if metrics['gross_profit'] is None and metrics.get('revenue') and metrics.get('cost_of_revenue'):
            metrics['gross_profit'] = metrics['revenue'] - metrics['cost_of_revenue']

        # Operating Income
        metrics['operating_income'] = self._extract_from_statement(
            income_stmt, [
                'Operating Income',
                'Operating Income (Loss)',
                'Income from Operations',
                'Income (Loss) from Operations',
                'Operating Profit',
                'Income from operations'
            ]
        )

        # 3. Calculate derived metrics
        self._calculate_margins(metrics)
        self._calculate_ratios(metrics)

        # 4. Shares and per-share metrics
        shares = self._get_shares_outstanding()
        if shares:
            metrics['shares_outstanding'] = shares
            if metrics.get('net_income'):
                metrics['eps'] = metrics['net_income'] / shares
            if metrics.get('free_cash_flow'):
                metrics['fcf_per_share'] = metrics['free_cash_flow'] / shares

        return metrics

    def _extract_fcf(self, financials) -> Optional[float]:
        """Improved FCF extraction with multiple fallbacks."""
        # Try 1: Helper method
        try:
            fcf = financials.get_free_cash_flow()
            fcf_float = self._to_float(fcf)
            if fcf_float is not None:
                return fcf_float
        except:
            pass

        # Try 2: Manual calculation from already-extracted values (preferred)
        # These were extracted with fallbacks in _extract_raw_metrics
        # Note: We can't use self.metrics here as it doesn't exist yet
        # So we extract them again with fallbacks
        cf_stmt = financials.cashflow_statement()

        ocf = self._to_float(financials.get_operating_cash_flow())
        if ocf is None and cf_stmt:
            ocf = self._extract_from_statement(
                cf_stmt, [
                    'Net Cash from Operating Activities',
                    'Net Cash Provided by Operating Activities',
                    'Cash from Operating Activities'
                ]
            )

        capex = self._to_float(financials.get_capital_expenditures())
        if capex is None and cf_stmt:
            capex = self._extract_from_statement(
                cf_stmt, [
                    'Payments for Property, Plant and Equipment',
                    'Capital Expenditures',
                    'Purchases of Property, Plant and Equipment'
                ]
            )

        if ocf is not None and capex is not None:
            return ocf - abs(capex)

        # Try 3: Direct extraction from cash flow statement
        if cf_stmt:
            fcf_direct = self._extract_from_statement(
                cf_stmt, [
                    'Free Cash Flow',
                    'Unlevered Free Cash Flow',
                    'Free Cash Flow Before Dividends'
                ]
            )
            if fcf_direct is not None:
                return fcf_direct

        return None

    def _get_shares_outstanding(self) -> Optional[float]:
        """Get shares outstanding with improved debugging."""
        try:
            facts = self.company.get_facts()

            share_concepts = [
                'us-gaap:CommonStockSharesOutstanding',
                'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic',
                'us-gaap:WeightedAverageNumberOfSharesOutstandingDiluted',
                'us-gaap:CommonStockSharesIssued'
            ]

            for concept in share_concepts:
                try:
                    # Strategy 1: Try latest without frequency filter (most permissive)
                    query_result = None
                    try:
                        query_result = facts.query().by_concept(concept).latest(1).execute()
                    except:
                        pass

                    # Strategy 2: Fall back to annual if needed
                    if not query_result or len(query_result) == 0:
                        try:
                            query_result = facts.query().by_concept(concept).annual().latest(1).execute()
                        except:
                            pass

                    # Strategy 3: Try quarterly
                    if not query_result or len(query_result) == 0:
                        try:
                            query_result = facts.query().by_concept(concept).quarterly().latest(1).execute()
                        except:
                            pass

                    if query_result and len(query_result) > 0:
                        val = self._to_float(query_result[0].numeric_value)
                        if val and val > 0:
                            return val
                except:
                    pass

            return None
        except:
            return None

    def _calculate_margins(self, metrics: Dict):
        """Calculate profit margins."""
        revenue = metrics.get('revenue')
        if revenue and revenue != 0:
            if metrics.get('gross_profit'):
                metrics['gross_margin'] = metrics['gross_profit'] / revenue
            if metrics.get('operating_income'):
                metrics['operating_margin'] = metrics['operating_income'] / revenue
            if metrics.get('net_income'):
                metrics['net_margin'] = metrics['net_income'] / revenue
            if metrics.get('free_cash_flow'):
                metrics['fcf_margin'] = metrics['free_cash_flow'] / revenue

    def _calculate_ratios(self, metrics: Dict):
        """Calculate financial ratios."""
        if metrics.get('net_income') and metrics.get('stockholders_equity'):
            if metrics['stockholders_equity'] != 0:
                metrics['roe'] = metrics['net_income'] / metrics['stockholders_equity']

        if metrics.get('operating_income') and metrics.get('total_assets'):
            if metrics['total_assets'] != 0:
                metrics['roic'] = metrics['operating_income'] / metrics['total_assets']

        if metrics.get('current_assets') and metrics.get('current_liabilities'):
            if metrics['current_liabilities'] != 0:
                metrics['current_ratio'] = metrics['current_assets'] / metrics['current_liabilities']


def format_value(val, key, unit='millions'):
    """Format values with proper units and precision."""
    if val is None:
        return "N/A"

    # Percentages and ratios
    if key.endswith('margin') or key.endswith('ratio') or key in ['roe', 'roic']:
        return f"{val:>8.2%}"

    # Growth rates
    if key.endswith('_growth'):
        return f"{val:>8.2f}%"

    # Per-share metrics (keep full precision)
    if key.endswith('_per_share') or key == 'eps':
        return f"${val:>8.2f}"

    # Monetary values (already scaled)
    if isinstance(val, float) and abs(val) > 0.01:
        if unit == 'millions':
            return f"${val:>10,.1f}M"
        elif unit == 'billions':
            return f"${val:>10,.2f}B"
        elif unit == 'thousands':
            return f"${val:>10,.0f}K"
        else:  # raw
            return f"${val:>15,.0f}"

    return str(val)


# =============================================================================
# USAGE
# =============================================================================

if __name__ == "__main__":
    test_tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "NFLX"]

    print("=" * 80)
    print("FINANCIAL METRICS EXTRACTION (in Millions)")
    print("=" * 80)

    all_results = []

    for ticker in test_tickers:
        print(f"\n{ticker}:")
        print("-" * 80)

        try:
            extractor = FinancialMetricsExtractor(ticker, unit='millions')
            metrics = extractor.extract_annual_metrics()

            if metrics:
                key_metrics = [
                    'revenue', 'gross_profit', 'operating_income', 'net_income',
                    'free_cash_flow', 'gross_margin', 'operating_margin',
                    'net_margin', 'roe', 'eps'
                ]

                for key in key_metrics:
                    val = metrics.get(key)
                    print(f"  {key:20s}: {format_value(val, key, 'millions')}")

                all_results.append(metrics)
                print(f"✓ Success")
            else:
                print(f"✗ No data")

        except Exception as e:
            print(f"✗ Error: {e}")

    # Create comparison DataFrame
    if all_results:
        print("\n" + "=" * 80)
        print("COMPARISON TABLE")
        print("=" * 80)

        df = pd.DataFrame(all_results)

        # Display with proper formatting
        display_cols = ['ticker', 'revenue', 'net_income', 'free_cash_flow',
                       'gross_margin', 'net_margin', 'roe', 'eps']
        display_cols = [col for col in display_cols if col in df.columns]

        print(df[display_cols].to_string(index=False, float_format=lambda x: f'{x:.2f}'))

        # Save to CSV with unit metadata
        df.to_csv('financial_metrics_scaled.csv', index=False)
        print("\n✓ Saved to financial_metrics_scaled.csv")
