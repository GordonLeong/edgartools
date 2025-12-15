from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")

# Debug why FCF fails for MSFT but works for AAPL
for ticker in ["AAPL", "MSFT", "TSLA", "NFLX"]:
    print(f"\n{'=' * 80}")
    print(f"Debugging FCF for {ticker}")
    print('=' * 80)

    company = Company(ticker)
    financials = company.get_financials()

    if financials:
        # Try helper method
        try:
            fcf_helper = financials.get_free_cash_flow()
            print(f"Helper FCF: {fcf_helper}")
        except Exception as e:
            print(f"Helper FCF failed: {e}")

        # Get components
        ocf = financials.get_operating_cash_flow()
        capex = financials.get_capital_expenditures()

        print(f"Operating CF: {ocf} (type: {type(ocf)})")
        print(f"CapEx: {capex} (type: {type(capex)})")

        # Manual calculation
        if ocf and capex:
            manual_fcf = ocf - abs(capex)
            print(f"Manual FCF: {manual_fcf}")

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
