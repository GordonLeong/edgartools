from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")

# Debug why FCF fails for MSFT but works for AAPL
for ticker in ["AAPL", "MSFT", "TSLA", "NFLX"]:
    print(f"\n{'=' * 80}")
    print(f"Debugging FCF for {ticker}")
    print('=' * 80)

    company = Company(ticker)

    # IMPORTANT: Filter out amendments like the main extractor does
    filings = company.get_filings(form="10-K", amendments=False)
    if filings and len(filings) > 0:
        latest_filing = filings.latest(1)
        if hasattr(latest_filing, 'obj'):
            tenk = latest_filing.obj()
            financials = tenk.financials if hasattr(tenk, 'financials') else None
        else:
            financials = company.get_financials()
    else:
        financials = company.get_financials()

    if financials:
        # Try helper method
        try:
            fcf_helper = financials.get_free_cash_flow()
            print(f"Helper FCF: {fcf_helper}")
        except Exception as e:
            print(f"Helper FCF failed: {e}")

        # Get components
        ocf_raw = financials.get_operating_cash_flow()
        capex_raw = financials.get_capital_expenditures()

        print(f"Operating CF raw: {repr(ocf_raw)} (type: {type(ocf_raw)})")
        print(f"CapEx raw: {repr(capex_raw)} (type: {type(capex_raw)})")

        # Convert to float safely
        def to_float(val):
            if val is None or (isinstance(val, str) and val.strip() == ''):
                return None
            try:
                return float(val)
            except:
                return None

        ocf = to_float(ocf_raw)
        capex = to_float(capex_raw)

        print(f"Operating CF converted: {ocf}")
        print(f"CapEx converted: {capex}")

        # Manual calculation
        if ocf is not None and capex is not None:
            manual_fcf = ocf - abs(capex)
            print(f"Manual FCF: {manual_fcf}")
        else:
            print(f"Cannot calculate FCF: OCF={ocf}, CapEx={capex}")

        # Check cashflow statement labels
        cf_stmt = financials.cashflow_statement()
        if cf_stmt:
            df = cf_stmt.render(standard=True).to_dataframe()
            print("\nCapEx-related labels:")
            capex_labels = df[df['label'].str.contains('capital|property|plant|equipment|capex', case=False, na=False)]
            for idx, row in capex_labels.head(5).iterrows():
                period_cols = [col for col in df.columns if col not in ['concept', 'label', 'level', 'abstract', 'dimension']]
                val = row[period_cols[0]] if period_cols else None
                print(f"  {row['label']}: {val}")
