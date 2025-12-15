from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")

company = Company("GOOGL")
financials = company.get_financials()
income_stmt = financials.income_statement()

# Get standardized statement
df = income_stmt.render(standard=True).to_dataframe()

# Show all revenue-related and profit-related rows
print("INCOME STATEMENT LABELS (Standardized):")
print("=" * 80)
for idx, row in df.iterrows():
    label = row['label']
    if any(keyword in label.lower() for keyword in ['revenue', 'gross', 'profit', 'cost', 'income', 'margin']):
        print(f"{label}")

print("\n\nFULL FIRST 30 ROWS:")
print("=" * 80)
print(df[['label', 'concept']].head(30).to_string(index=False))
