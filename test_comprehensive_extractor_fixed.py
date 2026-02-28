import pandas as pd
from typing import Optional, Dict, List
from edgar import Company, set_identity
from edgar.xbrl.standardization import StandardConcept

set_identity("Dev Gunning developer-gunning@gmail.com")


class ComprehensiveMetricsExtractor:
    """
    Extract comprehensive financial metrics using:
    1. Helper methods (where they exist - handle label variations)
    2. Fallback to standardized rendered statements
    3. XBRLS for multi-period data
    """

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.company = Company(ticker)

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

    def _extract_from_statement(self, statement, labels: List[str]) -> Optional[float]:
        """Fallback: Extract from standardized rendered statement."""
        if not statement:
            return None

        try:
            df = statement.render(standard=True).to_dataframe()
            if df.empty:
                return None

            # Get first period column
            period_cols = [col for col in df.columns
                          if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
            if not period_cols:
                return None

            period_col = period_cols[0]

            # Try each label
            for label in labels:
                # Try exact match first
                matches = df[df['label'] == label]
                if not matches.empty:
                    return self._to_float(matches.iloc[0][period_col])

                # Then partial match (case-insensitive)
                matches = df[df['label'].str.contains(label, case=False, na=False, regex=False)]
                if not matches.empty:
                    return self._to_float(matches.iloc[0][period_col])

            return None
        except Exception as e:
            #print(f"  Warning: Error extracting from statement: {e}")
            return None

    def extract_annual_metrics(self) -> Dict:
        """Extract annual metrics (latest 10-K)."""
        # CRITICAL FIX: Filter out amendments to avoid incomplete XBRL
        filings = self.company.get_filings(form="10-K", amendments=False)
        if not filings or len(filings) == 0:
            return {}

        # Get financials from latest NON-AMENDED filing
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
            'period_type': 'annual'
        }

        # 1. Use helper methods (handle label variations automatically)
        metrics['revenue'] = self._to_float(financials.get_revenue())
        metrics['net_income'] = self._to_float(financials.get_net_income())
        metrics['operating_cash_flow'] = self._to_float(financials.get_operating_cash_flow())

        # FCF helper might fail on type issues
        try:
            fcf = financials.get_free_cash_flow()
            metrics['free_cash_flow'] = self._to_float(fcf)
        except (TypeError, AttributeError):
            ocf = self._to_float(financials.get_operating_cash_flow())
            capex = self._to_float(financials.get_capital_expenditures())
            if ocf is not None and capex is not None:
                metrics['free_cash_flow'] = ocf - abs(capex)
            else:
                metrics['free_cash_flow'] = None

        metrics['capex'] = self._to_float(financials.get_capital_expenditures())
        metrics['total_assets'] = self._to_float(financials.get_total_assets())
        metrics['total_liabilities'] = self._to_float(financials.get_total_liabilities())
        metrics['stockholders_equity'] = self._to_float(financials.get_stockholders_equity())
        metrics['current_assets'] = self._to_float(financials.get_current_assets())
        metrics['current_liabilities'] = self._to_float(financials.get_current_liabilities())

        # 2. Fallback to statement extraction for metrics without helpers
        income_stmt = financials.income_statement()
        balance_sheet = financials.balance_sheet()

        # Gross Profit - try multiple label variations
        metrics['gross_profit'] = self._extract_from_statement(
            income_stmt, [
                'Gross Profit',
                'Gross Margin',
                'Total Gross Profit',
                'Gross Income'
            ]
        )

        # Operating Income - multiple variations
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

        # Cost of Revenue
        metrics['cost_of_revenue'] = self._extract_from_statement(
            income_stmt, [
                'Total Cost of Revenue',
                'Cost of Revenue',
                'Cost of Goods Sold',
                'Cost of Sales',
                'Cost of Goods and Services Sold'
            ]
        )

        # 3. Calculate derived metrics
        self._calculate_margins(metrics)
        self._calculate_ratios(metrics)

        # 4. Get shares outstanding for per-share metrics - FIXED API
        shares = self._get_shares_outstanding()
        if shares:
            metrics['shares_outstanding'] = shares
            if metrics.get('net_income'):
                metrics['eps'] = metrics['net_income'] / shares
            if metrics.get('free_cash_flow'):
                metrics['fcf_per_share'] = metrics['free_cash_flow'] / shares

        return metrics

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
        # ROE
        if metrics.get('net_income') and metrics.get('stockholders_equity'):
            if metrics['stockholders_equity'] != 0:
                metrics['roe'] = metrics['net_income'] / metrics['stockholders_equity']

        # ROIC (simplified)
        if metrics.get('operating_income') and metrics.get('total_assets'):
            if metrics['total_assets'] != 0:
                metrics['roic'] = metrics['operating_income'] / metrics['total_assets']

        # Current ratio
        if metrics.get('current_assets') and metrics.get('current_liabilities'):
            if metrics['current_liabilities'] != 0:
                metrics['current_ratio'] = metrics['current_assets'] / metrics['current_liabilities']

    def _get_shares_outstanding(self) -> Optional[float]:
        """Get shares outstanding from Company Facts API - FIXED."""
        try:
            facts = self.company.get_facts()

            # EntityFacts uses .query() API, not .get_facts()
            share_concepts = [
                'us-gaap:CommonStockSharesOutstanding',
                'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic',
            ]

            for concept in share_concepts:
                try:
                    # Query for the concept
                    query_result = facts.query().by_concept(concept).latest(1).execute()

                    if query_result and len(query_result) > 0:
                        return self._to_float(query_result[0].numeric_value)
                except:
                    continue

            return None
        except Exception as e:
            #print(f"  Warning: Could not get shares outstanding: {e}")
            return None


def format_number(val, key):
    """Format numbers for display."""
    if val is None:
        return "N/A"
    if isinstance(val, float):
        if key.endswith('margin') or key.endswith('ratio') or key in ['roe', 'roic']:
            return f"{val:>10.2%}"
        elif key.endswith('_growth'):
            return f"{val:>10.2f}%"
        elif abs(val) > 1_000_000:
            return f"${val:>15,.0f}"
        else:
            return f"{val:>15.4f}"
    return str(val)


# =============================================================================
# USAGE EXAMPLES
# =============================================================================

if __name__ == "__main__":

    # Test on multiple companies to ensure generalization
    test_tickers = ["AAPL", "MSFT", "GOOGL", "TSLA", "JPM"]

    print("=" * 80)
    print("TESTING EXTRACTION ON MULTIPLE COMPANIES")
    print("=" * 80)

    all_results = []

    for ticker in test_tickers:
        print(f"\n{'=' * 80}")
        print(f"Testing: {ticker}")
        print('=' * 80)

        try:
            extractor = ComprehensiveMetricsExtractor(ticker)

            # Extract annual metrics
            annual = extractor.extract_annual_metrics()

            if annual:
                # Display key metrics
                key_metrics = [
                    'revenue', 'gross_profit', 'operating_income', 'net_income',
                    'free_cash_flow', 'gross_margin', 'operating_margin',
                    'net_margin', 'roe', 'eps'
                ]

                print(f"\nCompany: {annual.get('company_name', 'N/A')}")
                for key in key_metrics:
                    val = annual.get(key)
                    print(f"  {key:25s}: {format_number(val, key)}")

                all_results.append(annual)
                print(f"✓ {ticker} extraction successful")
            else:
                print(f"✗ {ticker} no financials available")

        except Exception as e:
            print(f"✗ {ticker} extraction failed: {e}")
            import traceback
            traceback.print_exc()

    # Create comparison table
    if all_results:
        print("\n" + "=" * 80)
        print("COMPARISON TABLE (All Companies)")
        print("=" * 80)

        comparison_df = pd.DataFrame(all_results)
        display_cols = ['ticker', 'revenue', 'net_income', 'free_cash_flow',
                       'gross_margin', 'operating_margin', 'net_margin', 'roe']

        # Filter to existing columns
        display_cols = [col for col in display_cols if col in comparison_df.columns]

        print(comparison_df[display_cols].to_string(index=False))

        # Save to CSV
        comparison_df.to_csv('financial_metrics_comparison.csv', index=False)
        print("\n✓ Saved to financial_metrics_comparison.csv")
