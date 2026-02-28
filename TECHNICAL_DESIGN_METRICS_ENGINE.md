# Financial Statements & Metrics Engine - Technical Design

## Table of Contents

1. [Introduction](#introduction)
2. [EdgarTools Library Overview](#edgartools-library-overview)
3. [Solution Design](#solution-design)
4. [Current Useful Baseline (Keep + Improve)](#current-useful-baseline-keep--improve)
5. [Pipeline Architecture](#pipeline-architecture)
6. [Database Schema](#database-schema)
7. [Code Deletion Plan (Out of Scope: html_ingest)](#code-deletion-plan-out-of-scope-html_ingest)
8. [Debugging and DLQ Operations](#debugging-and-dlq-operations)
9. [Additional Considerations](#additional-considerations)
10. [Pipeline Deployment Workstreams](#pipeline-deployment-workstreams)
11. [Execution Backlog (Now / Next / Later)](#execution-backlog-now--next--later)
12. [Future Improvements & Roadmap](#future-improvements--roadmap)

---



### Project Overview

Build a financial data platform that provides:

1. **Comparable Financial Statements** - Income Statement, Balance Sheet, Cash Flow Statement with TTM/Quarterly/Annual views
2. **Metrics Engine** - Key fundamental metrics and KPIs extracted from XBRL data, stored in database, rendered with sparklines

### Architecture Pattern

```
┌─────────────────────────────────────────────────┐
│ Python Pipeline (EdgarTools)                    │
│ - Runs daily/weekly batch processing            │
│ - Extracts XBRL data from SEC filings           │
│ - Processes and stores in database              │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ PostgreSQL Database                             │
│ - Stores rendered statements (JSONB)            │
│ - Stores individual XBRL facts                  │
│ - Stores calculated metrics (TTM)               │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ SvelteKit Backend + Frontend                    │
│ - Fast DB queries (no EdgarTools dependency)    │
│ - Renders statements and metrics                │
│ - Sparklines visualization                      │
└─────────────────────────────────────────────────┘
```

### Key Design Principles

- **Immutable Data**: SEC filings never change after submission
- **Pre-computation**: Calculate TTM and metrics in pipeline, not on-demand
- **Separation of Concerns**: Python for XBRL parsing, SvelteKit for presentation
- **Performance**: Store rendered statements to avoid reconstruction

---

## EdgarTools Library Overview

### Installation & Setup

```bash
pip install edgartools
```

```python
from edgar import Company, Filing, set_identity

# Required: Set user identity for SEC API compliance
set_identity("Your Name your.email@company.com")
```

### Core Concepts

#### 1. Company - Primary Entry Point

```python
from edgar import Company

# Get company by ticker or CIK
company = Company("AAPL")

# Company metadata
print(company.name)           # "Apple Inc."
print(company.cik)            # 320193
print(company.sic)            # 3571 (industry code)
print(company.fiscal_year_end) # "0924" (Sept 24)

# Get latest filings
filings = company.get_filings(form='10-K')  # Annual reports
filings = company.get_filings(form='10-Q')  # Quarterly reports

# Get specific filing
latest_10k = filings.latest(1)
```

#### 2. Filing - Individual SEC Filing

```python
from edgar import Filing

# Get a specific filing
filing = company.get_filings(form='10-Q').latest(1)

# Filing metadata
print(filing.accession_number)  # "0000320193-24-000123"
print(filing.filing_date)       # "2024-11-01"
print(filing.period_of_report)  # "2024-09-28" (quarter end date)
print(filing.form)              # "10-Q"

# Access different data sources
xbrl = filing.xbrl()           # XBRL financial data
html = filing.html()           # HTML document
text = filing.text()           # Plain text
attachments = filing.attachments  # All attachments
```

#### 3. XBRL - Financial Data Parser

```python
# Parse XBRL from filing
xbrl = filing.xbrl()

# Get all available statements/roles
all_statements = xbrl.statements
# Returns list of dicts:
# [
#   {
#     'role': 'http://www.apple.com/role/ConsolidatedStatementsOfOperations',
#     'definition': 'Consolidated Statements of Operations',
#     'type': 'IncomeStatement',
#     'element_count': 45,
#     'primary_concept': 'us-gaap:IncomeStatementAbstract'
#   },
#   ...
# ]

# Get specific statement
income_stmt = xbrl.get_income_statement()
balance_sheet = xbrl.get_balance_sheet()
cash_flow = xbrl.get_cash_flow_statement()

# Render statement (for display)
table = income_stmt.render()  # Returns Rich Table object
df = income_stmt.to_dataframe()  # Returns pandas DataFrame
```

### Key Features for Our Use Case

#### Feature 1: Get Statements with Structure Preserved

```python
# The statement preserves the XBRL presentation order
income_stmt = xbrl.get_income_statement()

# Access line items (in order from XBRL presentation linkbase)
df = income_stmt.to_dataframe()

# DataFrame columns:
# - label: "Revenue", "Cost of Revenue", etc.
# - concept: "us-gaap:Revenues", "us-gaap:CostOfRevenue"
# - value_[period]: Values for each period
# - depth: Nesting level (0 = top-level, 1 = indented, etc.)
# - order: Display order from presentation linkbase
```

#### Feature 2: Filter Facts by Statement Type/Role

```python
# Get ALL facts
all_facts = xbrl.facts

# Query builder for filtering
query = xbrl.facts.query()

# Filter by statement type
income_facts = query.by_statement_type('IncomeStatement').to_dataframe()

# Filter by concept (with regex)
revenue_facts = query.by_concept('Revenue').to_dataframe()

# Filter by label
revenue_facts = query.by_label('Revenue', exact=True).to_dataframe()

# Combine filters
filtered = (xbrl.facts.query()
           .by_statement_type('IncomeStatement')
           .by_concept('Revenue')
           .to_dataframe())
```

#### Feature 3: Get Segment/Dimensional Data

```python
# Facts with dimensions (segments, products, geographies)
segment_facts = xbrl.facts.query().to_dataframe()

# Filter to only dimensional facts
dimensional_facts = segment_facts[segment_facts['dimensions'].notna()]

# Example dimensional fact:
# concept: us-gaap:Revenues
# value: 50000000
# dimensions: {'ProductOrServiceAxis': 'iPhone', 'StatementGeographyAxis': 'Americas'}
# statement_type: 'SegmentDisclosure'
```

#### Feature 4: Access Multiple Periods

```python
# Get historical filings
filings_10q = company.get_filings(form='10-Q').latest(8)  # Last 8 quarters

# Process each filing
for filing in filings_10q:
    xbrl = filing.xbrl()
    income_stmt = xbrl.get_income_statement()

    # Each filing has its own periods
    # 10-Q typically has: current quarter, YTD, prior year quarter, prior year YTD
    df = income_stmt.to_dataframe()
```

#### Feature 5: Fact-Level Data Access

```python
# Get specific fact value
facts_df = xbrl.facts.query().to_dataframe()

# Each fact has:
# - concept: XBRL concept name (e.g., 'us-gaap:Revenues')
# - label: Human-readable label
# - value: Numeric value
# - period_start: Period start date (for duration facts)
# - period_end: Period end date
# - period_type: 'instant' or 'duration'
# - decimals: Precision indicator
# - units: Usually 'USD' or 'shares'
# - statement_type: Which statement it belongs to
# - dimensions: Segment/product/geography breakdown (if applicable)
```

### Complete Example: Extract Full Income Statement

```python
from edgar import Company, set_identity
import pandas as pd

set_identity("Your Name email@example.com")

# 1. Get company and filing
company = Company("AAPL")
filing = company.get_filings(form='10-K').latest(1)

# 2. Parse XBRL
xbrl = filing.xbrl()

# 3. Get income statement
income_stmt = xbrl.get_income_statement()

# 4. Convert to structured data
df = income_stmt.to_dataframe()

# 5. Access the data
print(df[['label', 'concept', 'value_0', 'depth', 'order']])

# Output (example):
#                        label                    concept     value_0  depth  order
# 0                    Revenue         us-gaap:Revenues   383285000      0    1.0
# 1          Cost of Revenue        us-gaap:CostOfRevenue  214137000      1    2.0
# 2              Gross Profit           us-gaap:GrossProfit 169148000      0    3.0
# 3        Operating Expenses  us-gaap:OperatingExpenses   52584000      0    4.0
# 4          Operating Income    us-gaap:OperatingIncome  116564000      0    5.0
# ...

# 6. Save to database (structure preserved!)
statement_data = {
    'company_id': 'AAPL',
    'filing_accession': filing.accession_number,
    'statement_type': 'IncomeStatement',
    'period_end_date': filing.period_of_report,
    'period_type': 'A',  # Annual
    'line_items': df.to_dict('records')  # Save as JSON
}
```

### Important Methods Reference

| Method                             | Returns      | Use Case                           |
| ---------------------------------- | ------------ | ---------------------------------- |
| `Company.get_filings(form='10-K')` | Filings list | Get historical filings             |
| `filing.xbrl()`                    | XBRL object  | Parse financial data               |
| `xbrl.statements`                  | List[Dict]   | Get all available statements/roles |
| `xbrl.get_income_statement()`      | Statement    | Get income statement               |
| `xbrl.get_balance_sheet()`         | Statement    | Get balance sheet                  |
| `xbrl.get_cash_flow_statement()`   | Statement    | Get cash flow statement            |
| `statement.to_dataframe()`         | DataFrame    | Convert to pandas for processing   |
| `xbrl.facts.query()`               | FactQuery    | Start fact filtering               |
| `query.by_statement_type(type)`    | FactQuery    | Filter facts by statement          |
| `query.by_concept(pattern)`        | FactQuery    | Filter facts by concept name       |
| `query.to_dataframe()`             | DataFrame    | Get filtered facts as DataFrame    |

---

## Solution Design

### Feature 1: Comparable Financial Statements

#### Requirements

- Display Income Statement, Balance Sheet, Cash Flow Statement
- Support **TTM** (Trailing Twelve Months), **Quarterly**, and **Annual** views
- Enable **cross-company comparison** (AAPL vs MSFT vs GOOGL)
- Preserve statement structure and ordering from XBRL

#### Design Approach

**Storage Strategy:**

- Store full rendered statements as JSONB in database
- Preserve line item order from XBRL presentation linkbase
- Store multiple periods per company
- Pre-calculate TTM values

**Data Flow:**

```
SEC Filing → EdgarTools XBRL Parser → Statement Object → Database (JSONB)
                                                              ↓
                                                  SvelteKit Backend Query
                                                              ↓
                                                     Frontend Rendering
```

**Statement Structure (Stored in DB):**

```json
{
	"company_id": "AAPL",
	"statement_type": "IncomeStatement",
	"period_end_date": "2024-09-28",
	"period_type": "Q",
	"fiscal_year": 2024,
	"fiscal_quarter": 4,
	"line_items": [
		{
			"label": "Net sales",
			"concept": "us-gaap:Revenues",
			"value": 94930000000,
			"depth": 0,
			"order": 1.0,
			"is_abstract": false
		},
		{
			"label": "Cost of sales",
			"concept": "us-gaap:CostOfRevenue",
			"value": 52836000000,
			"depth": 1,
			"order": 2.0,
			"is_abstract": false
		},
		{
			"label": "Gross margin",
			"concept": "us-gaap:GrossProfit",
			"value": 42094000000,
			"depth": 0,
			"order": 3.0,
			"is_abstract": false
		}
	]
}
```

**TTM Calculation:**

```
TTM (Q4 2024) = Q4 2024 + Q3 2024 + Q2 2024 + Q1 2024

For each line item:
- Sum the values from last 4 quarters
- Store as separate statement with period_type = 'TTM'
- Update whenever new quarter is filed
```

**Cross-Company Comparison Strategy:**

```
1. Fetch statements for all companies
2. Align periods (match quarter end dates within tolerance)
3. Normalize line item labels using concept mapping
4. Render side-by-side table
```

### Feature 2: Metrics Engine

#### Requirements

- Extract **specific key fundamental metrics** from XBRL
- Support user-selectable metrics catalog
- Store in database for fast retrieval
- Enable sparkline visualization
- Handle missing/unavailable metrics gracefully

#### Design Approach

**Metrics Catalog:**
Define ~50-100 key metrics with concept mappings:

```python
METRICS_CATALOG = {
    # Income Statement Metrics
    'revenue': {
        'display_name': 'Revenue',
        'concepts': [
            'us-gaap:Revenues',
            'us-gaap:SalesRevenueNet',
            'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax',
            'us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax'
        ],
        'statement_types': ['IncomeStatement'],
        'period_type': 'duration',
        'category': 'income'
    },
    'net_income': {
        'display_name': 'Net Income',
        'concepts': [
            'us-gaap:NetIncomeLoss',
            'us-gaap:ProfitLoss',
            'us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic'
        ],
        'statement_types': ['IncomeStatement'],
        'period_type': 'duration',
        'category': 'income'
    },

    # Balance Sheet Metrics
    'total_assets': {
        'display_name': 'Total Assets',
        'concepts': ['us-gaap:Assets'],
        'statement_types': ['BalanceSheet'],
        'period_type': 'instant',
        'category': 'balance'
    },
    'total_debt': {
        'display_name': 'Total Debt',
        'concepts': [
            'us-gaap:LongTermDebt',
            'us-gaap:DebtCurrent',
            'us-gaap:LongTermDebtAndCapitalLeaseObligations'
        ],
        'statement_types': ['BalanceSheet'],
        'period_type': 'instant',
        'category': 'balance',
        'calculation': 'sum'  # Sum multiple concepts
    },

    # Cash Flow Metrics
    'operating_cash_flow': {
        'display_name': 'Operating Cash Flow',
        'concepts': [
            'us-gaap:NetCashProvidedByUsedInOperatingActivities'
        ],
        'statement_types': ['CashFlowStatement'],
        'period_type': 'duration',
        'category': 'cashflow'
    },

    # Derived Metrics
    'gross_margin': {
        'display_name': 'Gross Margin %',
        'calculation': 'gross_profit / revenue * 100',
        'depends_on': ['gross_profit', 'revenue'],
        'category': 'ratio'
    },

    # Segment Metrics
    'segment_revenue': {
        'display_name': 'Revenue by Segment',
        'concepts': ['us-gaap:Revenues'],
        'statement_types': ['SegmentDisclosure'],
        'has_dimensions': True,
        'dimension_axis': 'ProductOrServiceAxis',
        'category': 'segment'
    }
}
```

**Extraction Strategy:**

```python
def extract_metric(xbrl, metric_config):
    """Extract a single metric from XBRL"""

    # Try each concept in order of preference
    for concept in metric_config['concepts']:
        # Filter to specific statement types
        query = xbrl.facts.query().by_concept(concept)

        for stmt_type in metric_config['statement_types']:
            query = query.by_statement_type(stmt_type)

        facts = query.to_dataframe()

        # Filter to non-dimensional facts (unless metric expects dimensions)
        if not metric_config.get('has_dimensions', False):
            facts = facts[facts['dimensions'].isna()]

        if len(facts) > 0:
            # Found it! Return the fact
            return {
                'metric_name': metric_config['display_name'],
                'value': facts.iloc[0]['value'],
                'concept_used': concept,
                'period_end': facts.iloc[0]['period_end'],
                'found': True
            }

    # Not found - return None
    return {
        'metric_name': metric_config['display_name'],
        'found': False,
        'attempted_concepts': metric_config['concepts']
    }
```

**Dead Letter Queue:**
Track metrics that couldn't be extracted for manual review:

```python
# When metric not found
if not metric_result['found']:
    dead_letter_queue.add({
        'company_id': ticker,
        'metric_name': metric_name,
        'filing_accession': filing.accession_number,
        'attempted_concepts': metric_result['attempted_concepts'],
        'all_available_concepts': list(xbrl.facts.query().to_dataframe()['concept'].unique()),
        'timestamp': datetime.now()
    })
```

---

## Current Useful Baseline (Keep + Improve)

The existing codebase already has useful assets that should be retained and iterated on while deploying the full pipeline:

1. Keep and improve `data-pipeline/data-engine/metrics-engine/metrics_debugger.py` as the primary debugging CLI.
2. Keep and improve `data-pipeline/data-engine/metrics-engine/metrics_extractor.py` for phase-1 metric extraction logic.
3. Refactor `data-pipeline/data-engine/metrics-engine/financial-highlights.py` into production pipeline modules (not an ad-hoc script).
4. Reuse `src/lib/config/metricDefinitions.ts` as the phase-1 supported metric contract.
5. Reuse `src/lib/services/metricCalculator.ts` for derived metric and growth parity.
6. Keep provider abstraction in `src/lib/services/metricDataProvider.ts` and replace backend incrementally.

---

## Pipeline Architecture

### Pipeline Components

```
┌──────────────────────────────────────────────────────────────┐
│                    INGESTION PIPELINE                         │
│                  (Python + EdgarTools)                        │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 1. DISCOVERY                                            │ │
│  │    - Check for new filings (daily)                      │ │
│  │    - Track processed filings in DB                      │ │
│  │    - Queue unprocessed filings                          │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 2. EXTRACTION                                           │ │
│  │    - Download filing from SEC                           │ │
│  │    - Parse XBRL using EdgarTools                        │ │
│  │    - Extract statements                                 │ │
│  │    - Extract facts                                      │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 3. TRANSFORMATION                                       │ │
│  │    - Convert statements to JSON structure               │ │
│  │    - Extract metrics using catalog                      │ │
│  │    - Calculate derived metrics                          │ │
│  │    - Handle missing metrics (DLQ)                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 4. TTM CALCULATION                                      │ │
│  │    - Fetch last 4 quarters                              │ │
│  │    - Sum income statement line items                    │ │
│  │    - Average balance sheet line items                   │ │
│  │    - Sum cash flow line items                           │ │
│  │    - Store as separate statements                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 5. STORAGE                                              │ │
│  │    - Insert/update statements table                     │ │
│  │    - Insert facts to xbrl_facts table                   │ │
│  │    - Insert metrics to company_metrics table            │ │
│  │    - Log errors to dead_letter_queue                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Pipeline Implementation

```python
# pipeline.py

from edgar import Company, set_identity
import pandas as pd
from datetime import datetime, timedelta
import json
from database import db  # Your DB connection
from metrics_catalog import METRICS_CATALOG

set_identity("Pipeline pipeline@yourcompany.com")

class FinancialDataPipeline:

    def __init__(self, db_connection):
        self.db = db_connection
        self.metrics_catalog = METRICS_CATALOG

    def run_daily(self, tickers):
        """Run daily ingestion for list of tickers"""
        for ticker in tickers:
            try:
                self.process_company(ticker)
            except Exception as e:
                self.log_error(ticker, str(e))

    def process_company(self, ticker):
        """Process all filings for a company"""

        # 1. Get company
        company = Company(ticker)

        # 2. Get recent filings (10-K and 10-Q)
        filings_10k = company.get_filings(form='10-K').latest(5)  # Last 5 years
        filings_10q = company.get_filings(form='10-Q').latest(20)  # Last 5 years

        all_filings = list(filings_10k) + list(filings_10q)

        # 3. Process each filing
        for filing in all_filings:
            if self.is_already_processed(filing.accession_number):
                continue

            self.process_filing(ticker, filing)

        # 4. Calculate TTM for recent quarters
        self.calculate_ttm_statements(ticker)

    def process_filing(self, ticker, filing):
        """Process a single filing"""

        print(f"Processing {ticker} - {filing.form} - {filing.filing_date}")

        # 1. Parse XBRL
        xbrl = filing.xbrl()

        # 2. Extract and store statements
        self.extract_statements(ticker, filing, xbrl)

        # 3. Extract and store metrics
        self.extract_metrics(ticker, filing, xbrl)

        # 4. Mark as processed
        self.mark_processed(filing.accession_number)

    def extract_statements(self, ticker, filing, xbrl):
        """Extract and store all financial statements"""

        statement_types = {
            'IncomeStatement': 'income_statement',
            'BalanceSheet': 'balance_sheet',
            'CashFlowStatement': 'cash_flow_statement'
        }

        for stmt_type, table_name in statement_types.items():
            try:
                # Get statement
                if stmt_type == 'IncomeStatement':
                    stmt = xbrl.get_income_statement()
                elif stmt_type == 'BalanceSheet':
                    stmt = xbrl.get_balance_sheet()
                elif stmt_type == 'CashFlowStatement':
                    stmt = xbrl.get_cash_flow_statement()
                else:
                    continue

                # Convert to dataframe
                df = stmt.to_dataframe()

                # Structure line items
                line_items = []
                for _, row in df.iterrows():
                    line_items.append({
                        'label': row.get('label', ''),
                        'concept': row.get('concept', ''),
                        'value': float(row.get('value', 0)) if pd.notna(row.get('value')) else None,
                        'depth': int(row.get('depth', 0)),
                        'order': float(row.get('order', 0)),
                        'is_abstract': bool(row.get('is_abstract', False))
                    })

                # Determine period type
                period_type = 'A' if '10-K' in filing.form else 'Q'

                # Store in database
                self.db.insert_statement({
                    'company_id': ticker,
                    'filing_accession': filing.accession_number,
                    'statement_type': stmt_type,
                    'period_end_date': filing.period_of_report,
                    'period_type': period_type,
                    'fiscal_year': self.get_fiscal_year(filing),
                    'fiscal_quarter': self.get_fiscal_quarter(filing) if period_type == 'Q' else None,
                    'line_items': json.dumps(line_items),
                    'filing_date': filing.filing_date,
                    'role_uri': stmt.role_or_type if hasattr(stmt, 'role_or_type') else None
                })

            except Exception as e:
                print(f"Error extracting {stmt_type} for {ticker}: {e}")

    def extract_metrics(self, ticker, filing, xbrl):
        """Extract metrics from XBRL using catalog"""

        for metric_name, config in self.metrics_catalog.items():

            # Skip derived metrics (calculated later)
            if 'calculation' in config and 'depends_on' in config:
                continue

            result = self.extract_single_metric(xbrl, metric_name, config)

            if result['found']:
                # Store metric
                self.db.insert_metric({
                    'company_id': ticker,
                    'filing_accession': filing.accession_number,
                    'metric_name': metric_name,
                    'display_name': config['display_name'],
                    'value': result['value'],
                    'period_end_date': result['period_end'],
                    'period_type': 'A' if '10-K' in filing.form else 'Q',
                    'xbrl_concept': result['concept_used'],
                    'category': config['category']
                })
            else:
                # Add to dead letter queue
                self.db.insert_dead_letter({
                    'company_id': ticker,
                    'filing_accession': filing.accession_number,
                    'metric_name': metric_name,
                    'attempted_concepts': json.dumps(result['attempted_concepts']),
                    'created_at': datetime.now()
                })

    def extract_single_metric(self, xbrl, metric_name, config):
        """Extract a single metric value"""

        # Handle segment metrics differently
        if config.get('has_dimensions', False):
            return self.extract_dimensional_metric(xbrl, config)

        # Try each concept
        for concept in config['concepts']:
            # Build query
            query = xbrl.facts.query().by_concept(concept)

            # Filter by statement type if specified
            if 'statement_types' in config:
                for stmt_type in config['statement_types']:
                    query = query.by_statement_type(stmt_type)

            # Get facts
            facts = query.to_dataframe()

            # Filter out dimensional facts (we want consolidated numbers)
            if len(facts) > 0:
                facts_no_dims = facts[facts['dimensions'].isna()]

                if len(facts_no_dims) > 0:
                    # Use the most recent period
                    fact = facts_no_dims.iloc[0]

                    return {
                        'found': True,
                        'value': fact['value'],
                        'concept_used': concept,
                        'period_end': fact['period_end']
                    }

        # Not found
        return {
            'found': False,
            'attempted_concepts': config['concepts']
        }

    def calculate_ttm_statements(self, ticker):
        """Calculate TTM statements from last 4 quarters"""

        # Get last 4 quarters
        quarters = self.db.query("""
            SELECT * FROM statements
            WHERE company_id = %s
              AND period_type = 'Q'
              AND statement_type = 'IncomeStatement'
            ORDER BY period_end_date DESC
            LIMIT 4
        """, (ticker,))

        if len(quarters) < 4:
            return  # Not enough data

        # Calculate TTM for each line item
        # This requires aligning line items across quarters by concept
        ttm_line_items = self.sum_quarterly_line_items(quarters)

        # Store TTM statement
        self.db.insert_statement({
            'company_id': ticker,
            'statement_type': 'IncomeStatement',
            'period_end_date': quarters[0]['period_end_date'],
            'period_type': 'TTM',
            'line_items': json.dumps(ttm_line_items),
            'filing_date': quarters[0]['filing_date']
        })

    def sum_quarterly_line_items(self, quarters):
        """Sum line items across 4 quarters to get TTM"""

        # Parse all line items
        all_line_items = {}
        for q in quarters:
            items = json.loads(q['line_items'])
            for item in items:
                concept = item['concept']
                if concept not in all_line_items:
                    all_line_items[concept] = {
                        'label': item['label'],
                        'concept': concept,
                        'depth': item['depth'],
                        'order': item['order'],
                        'is_abstract': item['is_abstract'],
                        'values': []
                    }
                all_line_items[concept]['values'].append(item['value'])

        # Sum values
        ttm_items = []
        for concept, data in all_line_items.items():
            # Only sum if we have 4 values
            if len(data['values']) == 4 and None not in data['values']:
                ttm_value = sum(data['values'])
                ttm_items.append({
                    'label': data['label'],
                    'concept': concept,
                    'value': ttm_value,
                    'depth': data['depth'],
                    'order': data['order'],
                    'is_abstract': data['is_abstract']
                })

        # Sort by order
        ttm_items.sort(key=lambda x: x['order'])
        return ttm_items


# Run the pipeline
if __name__ == '__main__':
    tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA']

    pipeline = FinancialDataPipeline(db)
    pipeline.run_daily(tickers)
```

### Scheduling

```python
# Use APScheduler or cron

from apscheduler.schedulers.blocking import BlockingScheduler

scheduler = BlockingScheduler()

@scheduler.scheduled_job('cron', hour=18)  # Run at 6 PM daily
def daily_ingestion():
    tickers = get_tickers_from_config()
    pipeline = FinancialDataPipeline(db)
    pipeline.run_daily(tickers)

scheduler.start()
```

---

## Database Schema

### Complete Schema

```sql
-- Table 1: Rendered Financial Statements
CREATE TABLE statements (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(10) NOT NULL,
    filing_accession VARCHAR(20) NOT NULL,
    statement_type VARCHAR(50) NOT NULL,  -- 'IncomeStatement', 'BalanceSheet', etc.
    period_end_date DATE NOT NULL,
    period_type VARCHAR(10) NOT NULL,     -- 'Q', 'A', 'TTM'
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,               -- 1, 2, 3, 4 (NULL for annual)

    -- Full statement structure as JSON
    line_items JSONB NOT NULL,

    -- Metadata
    role_uri TEXT,
    filing_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(company_id, statement_type, period_end_date, period_type)
);

CREATE INDEX idx_statements_lookup ON statements(company_id, statement_type, period_type, period_end_date DESC);
CREATE INDEX idx_statements_period ON statements(period_end_date DESC);
CREATE INDEX idx_statements_company ON statements(company_id);


-- Table 2: XBRL Facts (for advanced queries and segment data)
CREATE TABLE xbrl_facts (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(10) NOT NULL,
    filing_accession VARCHAR(20) NOT NULL,

    -- Fact identification
    concept VARCHAR(200) NOT NULL,
    label TEXT,

    -- Value
    value DECIMAL(20,2),

    -- Period
    period_start DATE,
    period_end DATE,
    period_type VARCHAR(10),  -- 'instant' or 'duration'

    -- Context
    statement_type VARCHAR(50),
    role_uri TEXT,
    role_definition TEXT,

    -- Dimensions (for segment data)
    dimension_name VARCHAR(200),
    dimension_value VARCHAR(200),
    dimensions JSONB,  -- Full dimension structure

    -- Metadata
    decimals INTEGER,
    units VARCHAR(50),

    created_at TIMESTAMP DEFAULT NOW(),

    INDEX idx_facts_company_concept (company_id, concept),
    INDEX idx_facts_statement (statement_type),
    INDEX idx_facts_dimensions (dimension_name, dimension_value),
    INDEX idx_facts_period (period_end)
);


-- Table 3: Company Metrics (extracted and calculated)
CREATE TABLE company_metrics (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(10) NOT NULL,
    filing_accession VARCHAR(20),

    metric_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    value DECIMAL(20,2),

    period_end_date DATE NOT NULL,
    period_type VARCHAR(10) NOT NULL,  -- 'Q', 'A', 'TTM'
    fiscal_year INTEGER,
    fiscal_quarter INTEGER,

    -- Traceability
    xbrl_concept VARCHAR(200),  -- Which concept was used
    category VARCHAR(50),       -- 'income', 'balance', 'cashflow', 'ratio', 'segment'

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(company_id, metric_name, period_end_date, period_type),
    INDEX idx_metrics_lookup (company_id, metric_name, period_type, period_end_date DESC)
);


-- Table 4: Dead Letter Queue (metrics that couldn't be extracted)
CREATE TABLE dead_letter_queue (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(10) NOT NULL,
    filing_accession VARCHAR(20) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    attempted_concepts TEXT[],  -- Array of concepts tried
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,

    INDEX idx_dlq_unresolved (company_id, metric_name) WHERE NOT resolved
);


-- Table 5: Processing Log
CREATE TABLE processing_log (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(10),
    filing_accession VARCHAR(20),
    status VARCHAR(20),  -- 'processing', 'completed', 'failed'
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    INDEX idx_processing_status (status, started_at)
);


-- Table 6: Metrics Catalog (configuration)
CREATE TABLE metrics_catalog (
    metric_name VARCHAR(100) PRIMARY KEY,
    display_name VARCHAR(200),
    concept_list TEXT[],  -- Array of XBRL concepts
    statement_types TEXT[],
    category VARCHAR(50),
    calculation_formula TEXT,
    has_dimensions BOOLEAN DEFAULT FALSE,
    dimension_axis VARCHAR(200),
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Example Queries

```sql
-- Get income statement for specific company and period
SELECT line_items
FROM statements
WHERE company_id = 'AAPL'
  AND statement_type = 'IncomeStatement'
  AND period_type = 'TTM'
ORDER BY period_end_date DESC
LIMIT 1;

-- Get segment revenue for all companies
SELECT
    company_id,
    dimension_value as segment,
    value as revenue,
    period_end_date
FROM xbrl_facts
WHERE concept LIKE '%Revenue%'
  AND dimension_name = 'ProductOrServiceAxis'
  AND statement_type = 'SegmentDisclosure'
ORDER BY company_id, period_end_date DESC;

-- Get quarterly metrics for sparkline
SELECT
    period_end_date,
    value
FROM company_metrics
WHERE company_id = 'AAPL'
  AND metric_name = 'revenue'
  AND period_type = 'Q'
ORDER BY period_end_date DESC
LIMIT 12;

-- Get cross-company comparison
SELECT
    company_id,
    jsonb_array_elements(line_items)->>'label' as line_item,
    jsonb_array_elements(line_items)->>'value' as value
FROM statements
WHERE company_id IN ('AAPL', 'MSFT', 'GOOGL')
  AND statement_type = 'IncomeStatement'
  AND period_type = 'TTM'
  AND period_end_date >= '2024-01-01';
```

---

## Code Deletion Plan (Out of Scope: html_ingest)

The pipeline cleanup must remove non-essential files while explicitly keeping `data-pipeline/html_ingest/**` untouched.

1. Maintain explicit delete candidates in `data-pipeline/data-engine/metrics-engine/metrics-engine-plan/delete_list.md`.
2. Do not touch `data-pipeline/html_ingest/**`.
3. Proposed delete candidates:
   - `data-pipeline/experiments/add_stamp_backup.py`
   - `data-pipeline/experiments/comptest_v2.py`
   - `data-pipeline/experiments/debugallfacts.py`
   - `data-pipeline/experiments/debugfacts.py`
   - `data-pipeline/experiments/debugfcf.py`
   - `data-pipeline/experiments/debugger.py`
   - `data-pipeline/experiments/unified_debug.py`
   - `data-pipeline/experiments/financial_metrics_scaled.csv`
   - `data-pipeline/data-engine/metrics-engine/financial_metrics_scaled.csv`
   - All `__pycache__/**` and `.DS_Store` under `data-pipeline/experiments/**` and `data-pipeline/data-engine/**`
4. Keep `data-pipeline/experiments/test_comprehensive_extractor.py` only if migrated into main test tree; otherwise remove after extracting useful cases.

---

## Debugging and DLQ Operations

The pipeline should treat debugging and DLQ handling as first-class operations.

### Failure Record Contract

Each failure record should include:

- `run_id`
- `ticker`
- `form`
- `filing_accession`
- `report_period`
- `statement_type`
- `metric_id`
- `failure_type`
- `attempted_labels`
- `attempted_concepts`
- `raw_context`
- `severity`
- `status`
- `first_seen_at`
- `last_seen_at`
- `resolution_note`

### Debugger Command Additions

Extend `metrics_debugger.py` with:

- `coverage report` for statement/metric completeness
- `integrity check` for accounting and period consistency
- `dlq list`
- `dlq show`
- `dlq replay`
- `run diff` for comparing pipeline runs

### Mandatory Validation Checks

- Balance sheet equation check
- FCF reconciliation (`operating_cash_flow - abs(capex)`)
- Duplicate accession-period conflicts
- Period continuity gaps
- Sign convention sanity checks
- Shares and per-share sanity checks

### Debug Artifact Outputs

Emit JSONL artifacts per run for:

- statement extraction traces
- metric extraction traces
- failed lookups and fallback attempts
- validation outcomes
- DLQ entries and replay results

---

## Additional Considerations

### 1. What EdgarTools CAN'T Help With

#### A. TTM Calculation

**Problem:** XBRL only contains quarterly and annual data. TTM must be calculated.

**Solution:**

```python
# Implemented in pipeline
def calculate_ttm(ticker, statement_type):
    # Get last 4 quarters
    # Sum income statement items
    # Average balance sheet items (for point-in-time metrics)
    # Store as separate TTM statement
```

#### B. Concept Standardization/Mapping

**Problem:** Companies use different XBRL concepts for the same line item.

**Current State in EdgarTools:**

- EdgarTools has basic standardization in `/edgar/xbrl/standardization/core.py`
- Has label mapping for common concepts
- NOT comprehensive for all metrics

**Solution:**

1. **Extract EdgarTools standardization as starting point:**

   ```bash
   # Copy from edgartools codebase
   cp edgar/xbrl/standardization/concept_mappings.json ./our_repo/
   ```

2. **Build our own comprehensive mapping:**

   ```python
   # concept_mappings.json
   {
     "Revenue": [
       "us-gaap:Revenues",
       "us-gaap:SalesRevenueNet",
       "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
       "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
       "us-gaap:RegulatedAndUnregulatedOperatingRevenue"
     ],
     "Net Income": [
       "us-gaap:NetIncomeLoss",
       "us-gaap:ProfitLoss",
       "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
       "us-gaap:NetIncomeLossAvailableToCommonStockholdersDiluted"
     ]
     // ... expand over time
   }
   ```

3. **Use Dead Letter Queue to discover missing mappings:**

   ```sql
   -- Query DLQ to find patterns
   SELECT
       metric_name,
       array_agg(DISTINCT attempted_concepts) as concepts_tried,
       COUNT(*) as occurrences
   FROM dead_letter_queue
   WHERE NOT resolved
   GROUP BY metric_name
   ORDER BY occurrences DESC;
   ```

4. **Manual review process:**
   - Review DLQ weekly
   - Research correct concepts using SEC EDGAR
   - Add to concept_mappings.json
   - Reprocess failed extractions

#### C. Company-Specific Line Item Labels

**Problem:** Each company names line items differently in their presentation.

**Example:**

- Apple: "Net sales"
- Microsoft: "Total revenue"
- Google: "Revenues"
  All map to: `us-gaap:Revenues`

**Solution:**
Store both original label AND standardized concept:

```json
{
	"label": "Net sales", // Company's original label
	"concept": "us-gaap:Revenues", // Standardized concept
	"standardized_label": "Revenue" // Our normalized label for comparison
}
```

#### D. Period Alignment for Cross-Company Comparison

**Problem:** Companies have different fiscal year ends.

**Example:**

- Apple: FY ends Sept 30 (Q4 ends ~Sept 28)
- Microsoft: FY ends June 30 (Q4 ends ~June 30)
- Calendar companies: Q4 ends Dec 31

**Solution:**

```python
def align_periods(companies, tolerance_days=45):
    """
    Align periods within tolerance window
    E.g., Q4 2024 for all companies = periods ending between Sept 15 - Oct 15
    """
    period_buckets = defaultdict(list)

    for company in companies:
        for period in company.periods:
            # Find bucket
            bucket_key = find_nearest_quarter_end(period.end_date)
            period_buckets[bucket_key].append({
                'company': company.ticker,
                'period_end': period.end_date,
                'data': period.data
            })

    return period_buckets
```

#### E. Derived Metrics

**Problem:** Many important metrics aren't in XBRL directly (ratios, margins, growth rates).

**Solution:** Calculate in pipeline after extracting base metrics:

```python
DERIVED_METRICS = {
    'gross_margin': 'gross_profit / revenue * 100',
    'operating_margin': 'operating_income / revenue * 100',
    'net_margin': 'net_income / revenue * 100',
    'roe': 'net_income / shareholders_equity * 100',
    'debt_to_equity': 'total_debt / shareholders_equity',
    'current_ratio': 'current_assets / current_liabilities',
    'revenue_growth_yoy': '(revenue_current - revenue_prior_year) / revenue_prior_year * 100'
}

def calculate_derived_metric(formula, metric_values):
    # Parse formula
    # Substitute values
    # Calculate
    # Store
```

### 2. Error Handling & Data Quality

#### A. Missing Data Handling

```python
# Store NULL values explicitly
# Track data quality metrics
# Alert on unexpected missingness

data_quality_metrics = {
    'completeness': 0.95,  # 95% of expected metrics found
    'missing_critical': ['revenue', 'net_income'],  # Critical metrics missing
    'missing_optional': ['segment_revenue']  # Optional metrics missing
}
```

#### B. XBRL Parse Failures

```python
try:
    xbrl = filing.xbrl()
except Exception as e:
    # Log to processing_log
    # Alert if critical company
    # Retry later
    db.insert_processing_log({
        'company_id': ticker,
        'filing_accession': filing.accession_number,
        'status': 'failed',
        'error_message': str(e)
    })
```

#### C. Validation Rules

```python
# Sanity checks on extracted data
def validate_statement(statement_data):
    checks = []

    # Check: Assets = Liabilities + Equity (for balance sheet)
    if statement_type == 'BalanceSheet':
        assets = get_line_item_value(statement_data, 'us-gaap:Assets')
        liabilities = get_line_item_value(statement_data, 'us-gaap:Liabilities')
        equity = get_line_item_value(statement_data, 'us-gaap:StockholdersEquity')

        if abs(assets - (liabilities + equity)) > 1000:  # Tolerance for rounding
            checks.append({
                'rule': 'balance_sheet_equation',
                'passed': False,
                'message': f'Assets ({assets}) != Liabilities ({liabilities}) + Equity ({equity})'
            })

    # Check: Revenue > 0 (for income statement)
    if statement_type == 'IncomeStatement':
        revenue = get_line_item_value(statement_data, 'us-gaap:Revenues')
        if revenue <= 0:
            checks.append({
                'rule': 'positive_revenue',
                'passed': False,
                'message': f'Revenue is not positive: {revenue}'
            })

    return checks
```

### 3. Performance Optimizations

#### A. Batch Processing

```python
# Process multiple companies in parallel
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(process_company, ticker) for ticker in tickers]
    results = [f.result() for f in futures]
```

#### B. Caching

```python
# Cache parsed XBRL objects to avoid re-parsing
from functools import lru_cache

@lru_cache(maxsize=100)
def get_xbrl_cached(accession_number):
    filing = get_filing_by_accession(accession_number)
    return filing.xbrl()
```

#### C. Incremental Processing

```python
# Only process new filings
def get_unprocessed_filings(ticker):
    processed_accessions = db.query(
        "SELECT DISTINCT filing_accession FROM statements WHERE company_id = %s",
        (ticker,)
    )

    all_filings = get_all_filings(ticker)

    return [f for f in all_filings if f.accession_number not in processed_accessions]
```

### 4. Foreseeable Data Gaps and Integrity Risks (Additions)

1. Enum mismatch bug: `"Quarterly"` is currently written while `period_enum` expects `Q1..Q4`.
   - Reference: `data-pipeline/data-engine/metrics-engine/financial-highlights.py` (`period="Quarterly"`)
   - Reference: `src/migrations/011_period_enum_financial_statements.sql` (`period_enum`)
2. Fiscal quarter formula bug in current ingestion logic.
   - Reference: `data-pipeline/data-engine/metrics-engine/financial-highlights.py` (`fiscal_quarter =(month)-1//3+1`)
3. SQL migration syntax issue (`//` comment in SQL).
   - Reference: `src/migrations/010_create_companies_table.sql`
4. Period column selection can include non-period columns in stitched DataFrames.
   - Reference: `data-pipeline/data-engine/metrics-engine/financial-highlights.py` (`period_columns = [col for col in is_df.columns if col != "label"]`)
5. `filing_accession` is not persisted in the current ingestion write path despite schema support.
   - Reference: `src/migrations/011_period_enum_financial_statements.sql` (`filing_accession text`)
6. Provider period label is hardcoded to `Q1` in mapping path.
   - Reference: `src/lib/services/metricDataProvider.ts` (`const periodLabel = period === 'quarterly' ? ('Q1' as const) : ('Annual' as const);`)
7. App still defaults to HuggingFace provider while pipeline provider is pending.
   - Reference: `src/lib/services/metricDataProvider.ts` (`let currentProvider: MetricDataProvider = new HuggingFaceProvider();`)
8. Formula parity risk between extractor and frontend calculator if derived metrics are computed in two places without shared logic.
   - Reference: `data-pipeline/data-engine/metrics-engine/metrics_extractor.py`
   - Reference: `src/lib/services/metricCalculator.ts`

---

## Pipeline Deployment Workstreams

Deploying the full pipeline requires parallel workstreams with clear interfaces:

1. Workstream A: Schema and storage contracts
2. Workstream B: Discovery and processed-filing ledger
3. Workstream C: Statement extraction and normalization
4. Workstream D: Metrics extraction and derived metric parity
5. Workstream E: TTM computation and persistence
6. Workstream F: DLQ and integrity validation
7. Workstream G: On-demand run orchestration and CLI
8. Workstream H: Scheduled execution and run monitoring
9. Workstream I: Serving layer (JSONL first, DB next)
10. Workstream J: Provider cutover and HuggingFace deprecation

---

## Execution Backlog (Now / Next / Later)

### Now

- [ ] `PIPE-NOW-BUG-01` Fix SQL comment syntax in `src/migrations/010_create_companies_table.sql`. (1h)
- [ ] `PIPE-NOW-BUG-02` Fix period enum writes to `Q1..Q4` in `data-pipeline/data-engine/metrics-engine/financial-highlights.py`. (1h)
- [ ] `PIPE-NOW-BUG-03` Fix fiscal quarter math in `data-pipeline/data-engine/metrics-engine/financial-highlights.py`. (1h)
- [ ] `PIPE-NOW-BUG-04` Fix period-column filtering in `data-pipeline/data-engine/metrics-engine/financial-highlights.py`. (1h)
- [ ] `PIPE-NOW-BUG-05` Persist `filing_accession` on `financial_statements` writes. (1h)
- [ ] `PIPE-NOW-BUG-06` Fix hardcoded quarter label mapping in `src/lib/services/metricDataProvider.ts`. (1h)
- [ ] `PIPE-NOW-BUG-07` Align derived metric formulas with `src/lib/services/metricCalculator.ts` for phase-1 IDs. (1.5h)
- [ ] `PIPE-NOW-01` Create `delete_list.md` with approved remove candidates and explicit `html_ingest` exclusion. (1h)
- [ ] `PIPE-NOW-02` Remove approved non-essential experiment/generated files from delete list. (1h)
- [ ] `PIPE-NOW-03` Split current ingestion script into modules: `config`, `discovery`, `extract_statements`, `store`, `runner`. (2h)
- [ ] `PIPE-NOW-04` Add `processed_filings` ledger table or JSONL ledger with idempotent checks. (1.5h)
- [ ] `PIPE-NOW-05` Add on-demand statement pipeline CLI: `run --ticker --form --limit --mode`. (1.5h)
- [ ] `PIPE-NOW-06` Implement normalized statement JSON output contract and persist to JSONL local store. (1.5h)
- [ ] `PIPE-NOW-07` Add integrity checks for statements and emit structured failures. (1.5h)
- [ ] `PIPE-NOW-08` Implement on-demand key-metrics extraction run (same filing set as statements). (1.5h)
- [ ] `PIPE-NOW-09` Persist phase-1 key metrics from `src/lib/config/metricDefinitions.ts` to JSONL + optional DB target. (1.5h)
- [ ] `PIPE-NOW-10` Add TTM calculator for phase-1 statement and metric fields from last 4 quarters. (2h)
- [ ] `PIPE-NOW-11` Add debugger subcommands for `coverage report` and `integrity check`. (1.5h)
- [ ] `PIPE-NOW-12` Add minimal runbook docs for on-demand run, outputs, and failure triage. (1h)
- [ ] `PIPE-NOW-13` Add smoke tests: one ticker 10-Q + 10-K end-to-end run produces statement + metric artifacts. (2h)

### Next

- [ ] `PIPE-NEXT-01` Create full planned DB tables: `statements`, `xbrl_facts`, `company_metrics`, `dead_letter_queue`, `processing_log`, `metrics_catalog`. (2h)
- [ ] `PIPE-NEXT-02` Implement statement JSONB writer (`statements.line_items`) and role/metadata persistence. (1.5h)
- [ ] `PIPE-NEXT-03` Implement `xbrl_facts` writer with dimensional facts support. (2h)
- [ ] `PIPE-NEXT-04` Implement `company_metrics` writer with concept traceability. (1.5h)
- [ ] `PIPE-NEXT-05` Implement DLQ writer + status lifecycle updates (`open`, `replayed`, `resolved`). (1.5h)
- [ ] `PIPE-NEXT-06` Implement run log writer for started/completed/failed runs. (1h)
- [ ] `PIPE-NEXT-07` Build metrics catalog bootstrap from phase-1 metric IDs and extraction mappings. (1.5h)
- [ ] `PIPE-NEXT-08` Add incremental discovery pass for unprocessed filings by accession. (1.5h)
- [ ] `PIPE-NEXT-09` Add retry policy and replay mechanism for failed filings only. (1.5h)
- [ ] `PIPE-NEXT-10` Add scheduled runner (`cron`/APScheduler) with lock to avoid concurrent runs. (1.5h)
- [ ] `PIPE-NEXT-11` Implement `EdgarPipelineProvider` in `src/lib/services/metricDataProvider.ts`, local JSONL-first read path. (2h)
- [ ] `PIPE-NEXT-12` Add route-level fallback order: pipeline local -> pipeline DB -> HuggingFace adapter. (1.5h)
- [ ] `PIPE-NEXT-13` Add parity-check job comparing HF adapter vs pipeline for phase-1 metrics on pilot ticker set. (2h)
- [ ] `PIPE-NEXT-14` Add deployment packaging (`pyproject` entrypoint + env var validation + health command). (1.5h)
- [ ] `PIPE-NEXT-15` Add operational docs: runbook, rollback, and cutover criteria for provider default switch. (1.5h)

### Later

1. Make pipeline provider default across app after parity and reliability thresholds are met.
2. Deprecate and remove HuggingFace adapter once fallback is no longer required.
3. Build DLQ triage UI and review workflow.
4. Expand supported metrics beyond phase 1 in controlled batches.
5. Add advanced segment/geography metrics and cross-company alignment enhancements.
6. Add quality score dashboards and alerting for completeness/integrity drift.
7. Optimize scaling (parallelism, caching, queue workers) after baseline reliability is stable.

---

## Future Improvements & Roadmap

### Phase 1: MVP 

- ✅ Extract 3 core statements (Income, Balance, Cash Flow)
- ✅ Extract ~20 key metrics (revenue, net income, assets, debt, etc.)
- ✅ Calculate TTM
- ✅ Store in database
- ✅ Basic SvelteKit UI to display statements

### Phase 2: Enhanced Metrics 

- 📊 Expand to ~50 metrics
- 📊 Add derived metrics (margins, ratios)
- 📊 Segment/product revenue breakdown
- 📊 Geographic revenue breakdown
- 📊 Dead letter queue UI for manual review
- 📊 Concept mapping expansion

### Phase 3: Advanced Features 

- 🎯 Peer comparison (automatic industry grouping)
- 🎯 Historical trend analysis
- 🎯 Anomaly detection (unusual metric changes)
- 🎯 Custom metric builder (user-defined formulas)
- 🎯 Metric alerts (notify when metric crosses threshold)

### Phase 4: AI-Enhanced 

- 🤖 LLM-based concept mapping discovery
- 🤖 Automatic DLQ resolution suggestions
- 🤖 Natural language queries ("Show me Apple's revenue growth vs Microsoft")
- 🤖 Narrative generation ("Apple's gross margin improved 2% YoY due to...")
- 🤖 Prediction models (forecast next quarter metrics)

### Specific Enhancement Ideas

#### 1. Smart Concept Mapping Discovery

```python
# Use LLM to suggest mappings
def suggest_concept_mapping(metric_name, attempted_concepts, all_available_concepts):
    """
    Use GPT-4 to suggest which concept matches the metric we're looking for
    Or potentially traditional ML in future
    """
    prompt = f"""
    We're trying to extract the metric "{metric_name}" from a 10-K filing.

    We tried these concepts but didn't find data: {attempted_concepts}

    Here are all available concepts in this filing: {all_available_concepts[:100]}

    Which concept should we use for "{metric_name}"?
    Return the exact concept name, or "NOT_FOUND" if none match.
    """

    response = openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )

    suggested_concept = response.choices[0].message.content
    return suggested_concept
```

#### 2. Automated Quality Checks

```python
# Use calculation linkbase for validation
def validate_using_calculation_linkbase(xbrl, statement_type):
    """
    XBRL has calculation trees that define which concepts sum to which
    Use this to validate our extracted statements
    """
    calc_trees = xbrl.calculation_trees

    validation_errors = []

    for role, tree in calc_trees.items():
        for node_id, node in tree.all_nodes.items():
            # Get parent value
            parent_value = get_fact_value(xbrl, node_id)

            # Get children values
            children_sum = sum(
                get_fact_value(xbrl, child_id) * weight
                for child_id, weight in node.children
            )

            # Compare
            if abs(parent_value - children_sum) > tolerance:
                validation_errors.append({
                    'concept': node_id,
                    'expected': parent_value,
                    'calculated': children_sum,
                    'difference': parent_value - children_sum
                })

    return validation_errors
```

#### 3. Metric Importance Scoring

```python
# Track which metrics users actually use
CREATE TABLE metric_usage (
    metric_name VARCHAR(100),
    company_id VARCHAR(10),
    view_count INTEGER,
    last_viewed_at TIMESTAMP
);

# Prioritize ingestion of popular metrics
# Deprioritize rarely-used metrics
```

#### 4. Cross-Filing Consistency Checks

```python
# Validate that values are consistent across related filings
def check_cross_filing_consistency(ticker, metric_name):
    """
    E.g., Q1+Q2+Q3+Q4 revenue should equal annual revenue (within rounding)
    """
    annual = get_metric_value(ticker, metric_name, period_type='A', year=2024)
    quarterly = [
        get_metric_value(ticker, metric_name, period_type='Q', quarter=q, year=2024)
        for q in [1, 2, 3, 4]
    ]

    if abs(annual - sum(quarterly)) > tolerance:
        alert_inconsistency(ticker, metric_name, annual, sum(quarterly))
```

#### 5. Industry Benchmarking

```python
# Automatic peer group identification
def get_peer_companies(ticker):
    """
    Use SIC code, market cap, and business description to find peers
    """
    company = Company(ticker)
    sic = company.sic

    # Find companies with same SIC
    peers = db.query(
        "SELECT ticker FROM companies WHERE sic = %s AND ticker != %s",
        (sic, ticker)
    )

    return peers

# Calculate industry averages
def get_industry_percentiles(metric_name, industry_sic):
    values = db.query("""
        SELECT value FROM company_metrics m
        JOIN companies c ON m.company_id = c.ticker
        WHERE m.metric_name = %s
          AND c.sic = %s
          AND m.period_type = 'TTM'
        ORDER BY m.period_end_date DESC
        LIMIT 1
    """, (metric_name, industry_sic))

    return {
        'p25': np.percentile(values, 25),
        'median': np.percentile(values, 50),
        'p75': np.percentile(values, 75)
    }
```

### Metrics Catalog Expansion Plan

| Category         | Current | Phase 2 | Phase 3 | Phase 4 |
| ---------------- | ------- | ------- | ------- | ------- |
| Income Statement | 10      | 20      | 30      | 50      |
| Balance Sheet    | 8       | 15      | 25      | 40      |
| Cash Flow        | 6       | 12      | 20      | 35      |
| Ratios           | 5       | 15      | 30      | 50      |
| Segment          | 2       | 10      | 20      | 30      |
| Per-Share        | 4       | 10      | 15      | 25      |
| **Total**        | **35**  | **82**  | **140** | **230** |

### Technology Stack Evolution

```
Phase 1 (MVP):
- Python + EdgarTools
- PostgreSQL
- SvelteKit
- Basic charts

Phase 2:
+ Redis caching
+ Background job queue (Celery/RQ)
+ Time-series database (TimescaleDB extension)

Phase 3:
+ Elasticsearch (for concept search)
+ Data warehouse (Clickhouse/DuckDB)
+ Advanced visualizations (D3.js)

Phase 4:
+ Vector database (for semantic search)
+ LLM integration (GPT-4)
+ Real-time updates (WebSockets)
+ ML models (scikit-learn/PyTorch)
```

---

## Appendix

### A. Common XBRL Concepts Reference

```python
# Core Income Statement
INCOME_STATEMENT_CONCEPTS = {
    'revenue': ['us-gaap:Revenues', 'us-gaap:SalesRevenueNet'],
    'cost_of_revenue': ['us-gaap:CostOfRevenue', 'us-gaap:CostOfGoodsAndServicesSold'],
    'gross_profit': ['us-gaap:GrossProfit'],
    'operating_expenses': ['us-gaap:OperatingExpenses'],
    'operating_income': ['us-gaap:OperatingIncomeLoss'],
    'interest_expense': ['us-gaap:InterestExpense'],
    'tax_expense': ['us-gaap:IncomeTaxExpenseBenefit'],
    'net_income': ['us-gaap:NetIncomeLoss', 'us-gaap:ProfitLoss']
}

# Core Balance Sheet
BALANCE_SHEET_CONCEPTS = {
    'cash': ['us-gaap:CashAndCashEquivalentsAtCarryingValue'],
    'accounts_receivable': ['us-gaap:AccountsReceivableNetCurrent'],
    'inventory': ['us-gaap:InventoryNet'],
    'current_assets': ['us-gaap:AssetsCurrent'],
    'ppe': ['us-gaap:PropertyPlantAndEquipmentNet'],
    'total_assets': ['us-gaap:Assets'],
    'accounts_payable': ['us-gaap:AccountsPayableCurrent'],
    'current_liabilities': ['us-gaap:LiabilitiesCurrent'],
    'long_term_debt': ['us-gaap:LongTermDebt'],
    'total_liabilities': ['us-gaap:Liabilities'],
    'shareholders_equity': ['us-gaap:StockholdersEquity']
}

# Core Cash Flow
CASH_FLOW_CONCEPTS = {
    'operating_cash_flow': ['us-gaap:NetCashProvidedByUsedInOperatingActivities'],
    'capex': ['us-gaap:PaymentsToAcquirePropertyPlantAndEquipment'],
    'investing_cash_flow': ['us-gaap:NetCashProvidedByUsedInInvestingActivities'],
    'financing_cash_flow': ['us-gaap:NetCashProvidedByUsedInFinancingActivities'],
    'free_cash_flow': ['us-gaap:FreeCashFlow']  # Sometimes calculated, not reported
}
```

### B. SvelteKit API Example

```typescript
// routes/api/statements/[ticker]/+server.ts

export async function GET({ params, url }) {
	const { ticker } = params;
	const statementType = url.searchParams.get('type') || 'IncomeStatement';
	const periodType = url.searchParams.get('period') || 'TTM';

	// Query database
	const statement = await db.query(
		`
    SELECT
      period_end_date,
      line_items,
      fiscal_year,
      fiscal_quarter
    FROM statements
    WHERE company_id = $1
      AND statement_type = $2
      AND period_type = $3
    ORDER BY period_end_date DESC
    LIMIT 1
  `,
		[ticker, statementType, periodType]
	);

	return json(statement);
}

// routes/api/metrics/[ticker]/+server.ts

export async function GET({ params, url }) {
	const { ticker } = params;
	const metricNames = url.searchParams.get('metrics')?.split(',') || [];
	const periods = parseInt(url.searchParams.get('periods') || '12');

	const metrics = await db.query(
		`
    SELECT
      metric_name,
      display_name,
      value,
      period_end_date,
      period_type
    FROM company_metrics
    WHERE company_id = $1
      AND metric_name = ANY($2)
    ORDER BY period_end_date DESC
    LIMIT $3
  `,
		[ticker, metricNames, periods]
	);

	return json(metrics);
}
```

---

## Conclusion

This technical design provides a comprehensive blueprint for building a financial statements and metrics engine using EdgarTools as the XBRL parsing foundation. The key insights are:

1. **EdgarTools handles XBRL complexity** - Use it for parsing, not for storage/presentation
2. **Store rendered statements** - Pre-compute and cache in database for fast queries
3. **Build concept mapping layer** - EdgarTools provides basic standardization; expand it
4. **Dead letter queue is essential** - Track what can't be extracted, review regularly
5. **TTM must be calculated** - Not in XBRL, sum last 4 quarters
6. **Pipeline separation** - Python for ingestion, SvelteKit for presentation
7. **Start small, expand incrementally** - 35 metrics → 230 metrics over time

The architecture is designed to scale from MVP to advanced AI-enhanced platform while maintaining simplicity and performance.
