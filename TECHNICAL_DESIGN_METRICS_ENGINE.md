# Financial Statements & Metrics Engine - Technical Design

## Table of Contents
1. [Introduction](#introduction)
2. [EdgarTools Library Overview](#edgartools-library-overview)
3. [Solution Design](#solution-design)
4. [Pipeline Architecture](#pipeline-architecture)
5. [Database Schema](#database-schema)
6. [Additional Considerations](#additional-considerations)
7. [Future Improvements & Roadmap](#future-improvements--roadmap)

---

## Introduction

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
income_stmt = xbrl.statements.income_statement()

# 4. Convert to structured data
df = income_stmt.to_dataframe()

# 5. Access the data
print(df[['label', 'concept', 'value_0', 'level', 'order']])

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

| Method | Returns | Use Case |
|--------|---------|----------|
| `Company.get_filings(form='10-K')` | Filings list | Get historical filings |
| `filing.xbrl()` | XBRL object | Parse financial data |
| `xbrl.statements` | Statements object | Get all available statements/roles |
| `xbrl.statements.income_statement()` | Statement | Get income statement |
| `xbrl.statements.balance_sheet()` | Statement | Get balance sheet |
| `xbrl.statements.cash_flow_statement()` | Statement | Get cash flow statement |
| `statement.to_dataframe()` | DataFrame | Convert to pandas for processing |
| `xbrl.facts.query()` | FactQuery | Start fact filtering |
| `query.by_statement_type(type)` | FactQuery | Filter facts by statement |
| `query.by_concept(pattern)` | FactQuery | Filter facts by concept name |
| `query.by_fiscal_period("Q1"\|"Q2"\|"Q3"\|"Q4"\|"FY")` | FactQuery | Filter by fiscal period |
| `query.by_fiscal_year(year)` | FactQuery | Filter by fiscal year |
| `query.by_dimension(axis, member)` | FactQuery | Filter dimensional (segment) data |
| `query.exclude_dimensions()` | FactQuery | Get consolidated facts only |
| `query.to_dataframe()` | DataFrame | Get filtered facts as DataFrame |
| `XBRLS.from_filings(filings)` | XBRLS | Multi-period stitched view |
| `xbrls.get_statement(type, max_periods)` | Dict | Stitched statement across periods |
| `initialize_default_mappings()` | MappingStore | Get standardization mapping store |
| `store.get_standard_concept(concept)` | str\|None | Resolve concept to standard label |

#### Feature 4: XBRLS - Multi-Period Stitching
```python
from edgar import Company
from edgar.xbrl.stitching import XBRLS

# Get multiple quarterly filings
company = Company("AAPL")
filings = company.get_filings(form='10-Q').latest(8)  # Last 8 quarters

# Create stitched view (handles period normalization, concept changes over time)
xbrls = XBRLS.from_filings(filings, filter_amendments=True)

# Get income statement across all periods
stmt = xbrls.get_statement('IncomeStatement', max_periods=8, standard=True)

# Query facts across all periods
revenue_trend = (xbrls.facts.query()
                .by_concept('Revenues')
                .by_statement_type('IncomeStatement')
                .to_dataframe())

# Calculate TTM easily
q1_facts = xbrls.facts.query().by_fiscal_period("Q1").to_dataframe()
q2_facts = xbrls.facts.query().by_fiscal_period("Q2").to_dataframe()
q3_facts = xbrls.facts.query().by_fiscal_period("Q3").to_dataframe()
q4_facts = xbrls.facts.query().by_fiscal_period("Q4").to_dataframe()
# TTM = sum(Q1 + Q2 + Q3 + Q4 values for same fiscal year)
```

**Key Features:**
- Automatically deduplicates overlapping periods across filings
- Normalizes concepts that change over time (company switches XBRL tags)
- Intelligent period selection: `RECENT_PERIODS`, `THREE_YEAR_COMPARISON`, `QUARTERLY_TREND`
- **This replaces manual looping** over filings for multi-period extraction

**DataFrame Field Names (Important!):**
- `numeric_value` (not `value`) - The parsed float value
- `level` (not `depth`) - Hierarchy indentation level
- `period_key` - Format: `"duration_2024-01-01_2024-12-31"` or `"instant_2024-12-31"`
- `fiscal_period` - Values: `"FY"`, `"Q1"`, `"Q2"`, `"Q3"`, `"Q4"`

#### Feature 5: Standardization API
```python
from edgar.xbrl.standardization import initialize_default_mappings, MappingStore, StandardConcept

# Load the mapping store (100+ concepts → 500+ XBRL variants)
store = initialize_default_mappings(read_only=True)

# Resolve an XBRL concept to standard label
standard = store.get_standard_concept("us-gaap_Revenues")  # → "Revenue"
standard = store.get_standard_concept("tsla_AutomotiveRevenue")  # → "Automotive Revenue" (company-specific)

# Get all XBRL concepts that map to a standard label
concepts = store.get_company_concepts("Revenue")
# → {'us-gaap_Revenues', 'us-gaap_SalesRevenueNet', 'us-gaap_RevenueFromContractWithCustomer...'}

# StandardConcept enum (canonical metric names)
from edgar.xbrl.standardization import StandardConcept
print(StandardConcept.REVENUE.value)  # "Revenue"
print(StandardConcept.NET_INCOME.value)  # "Net Income"
print(StandardConcept.TOTAL_ASSETS.value)  # "Total Assets"
```

**Concept Resolution Priority (highest wins):**
1. **P4**: Entity-detected match (concept prefix matches company, e.g., `tsla_*` → Tesla mappings)
2. **P2**: Company-specific mapping (`company_mappings/{ticker}_mappings.json`)
3. **P1**: Core mapping (`concept_mappings.json`)

**Key Files:**
- `edgar/xbrl/standardization/concept_mappings.json` - 100+ standard labels → 500+ variants
- `edgar/xbrl/standardization/company_mappings/` - Per-company custom mappings (MSFT, TSLA, BRKA)
- `edgar/xbrl/standardization/core.py` - `MappingStore`, `StandardConcept` enum (100+ concepts)

**Recent Upgrades:**
- Revenue hierarchy (separates total revenue from product/service/contract components)
- SG&A hierarchy (separates total SG&A from selling/general/admin components)
- Cost of Revenue hierarchy (separates COGS from cost of services)
- Prevents duplicate labels when companies report both aggregates and components

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
  "period_key": "duration_2024-07-01_2024-09-28",
  "period_type": "Q",
  "fiscal_year": 2024,
  "fiscal_quarter": 4,
  "fiscal_period": "Q4",
  "line_items": [
    {
      "label": "Net sales",
      "standard_label": "Revenue",
      "concept": "us-gaap:Revenues",
      "value": 94930000000,
      "level": 1,
      "order": 1.0,
      "is_abstract": false
    },
    {
      "label": "Cost of sales",
      "standard_label": "Cost of Revenue",
      "concept": "us-gaap:CostOfRevenue",
      "value": 52836000000,
      "level": 2,
      "order": 2.0,
      "is_abstract": false
    },
    {
      "label": "Gross margin",
      "standard_label": "Gross Profit",
      "concept": "us-gaap:GrossProfit",
      "value": 42094000000,
      "level": 1,
      "order": 3.0,
      "is_abstract": false
    }
  ]
}
```

**Key Fields:**
- `period_key` - Precise period identifier for filtering (`duration_YYYY-MM-DD_YYYY-MM-DD` or `instant_YYYY-MM-DD`)
- `fiscal_period` - "FY", "Q1", "Q2", "Q3", "Q4" (from EdgarTools)
- `standard_label` - Normalized label from MappingStore (frontend can choose original or standard)
- `level` - Hierarchy depth (0 = abstract, 1 = top-level, 2+ = nested)

**TTM Calculation (Using XBRLS):**
```python
from edgar import Company
from edgar.xbrl.stitching import XBRLS

# Get last 4 quarters
company = Company("AAPL")
quarters = company.get_filings(form='10-Q').latest(4)
xbrls = XBRLS.from_filings(quarters, filter_amendments=True)

# Get stitched statement
stmt = xbrls.get_statement('IncomeStatement', max_periods=4, standard=True)

# TTM calculation for each line item
ttm_line_items = []
for item in stmt['data']:
    # Sum values across the 4 periods
    values = [item['values'].get(p) for p in stmt['periods'][:4]]
    values = [v for v in values if v is not None]

    if len(values) == 4:
        ttm_line_items.append({
            'label': item['label'],
            'standard_label': item.get('standard_label'),
            'concept': item['concept'],
            'value': sum(values),  # TTM = Q1 + Q2 + Q3 + Q4
            'level': item['level'],
            'order': item['order']
        })

# Store as separate statement with period_type = 'TTM'
```

**Cross-Company Comparison Strategy:**
```
1. Fetch statements for all companies
2. Align periods (match quarter end dates within tolerance)
3. Normalize line item labels using concept mapping
4. Render side-by-side table
```

### Feature 2: Metrics Engine with Three-Tier Resolution

#### Requirements
- Extract **specific key fundamental metrics** from XBRL
- Support user-selectable metrics catalog
- **Self-improving**: Learn from EdgarTools standardization + DLQ resolutions
- Store in database for fast retrieval
- Enable sparkline visualization
- Handle missing/unavailable metrics gracefully with dead letter queue

#### Design Approach: Three-Tier Resolution

```
┌─────────────────────────────────────────────────┐
│ Tier 1: Our Own DB Metric Mappings             │
│   - Custom company-specific mappings we've added│
│   - Fastest (no file I/O)                       │
│   - Priority: Check first                       │
└─────────────────────────────────────────────────┘
                    ↓ Not found
┌─────────────────────────────────────────────────┐
│ Tier 2: EdgarTools MappingStore                │
│   - 100+ concepts → 500+ variants               │
│   - Company mappings (MSFT, TSLA, BRKA)         │
│   - Resolution → Store back to Tier 1 (learn)   │
└─────────────────────────────────────────────────┘
                    ↓ Not found
┌─────────────────────────────────────────────────┐
│ Tier 3: Dead Letter Queue                      │
│   - Log for manual review                       │
│   - Human resolves → Add to Tier 1              │
│   - Optionally add to company_mappings JSON     │
└─────────────────────────────────────────────────┘
```

**Metrics Catalog (Aligned with StandardConcept):**

Use `StandardConcept` enum values as canonical metric names:

```python
from edgar.xbrl.standardization import StandardConcept

METRICS_CATALOG = {
    # Use StandardConcept values as keys (canonical names)
    StandardConcept.REVENUE.value: {  # "Revenue"
        'display_name': 'Revenue',
        'standard_concept': StandardConcept.REVENUE,
        'statement_types': ['IncomeStatement'],
        'period_type': 'duration',
        'category': 'income',
        'parent_metric': None,  # Top-level (no parent)
        'child_metrics': ['Product Revenue', 'Service Revenue', 'Contract Revenue']
    },

    StandardConcept.NET_INCOME.value: {  # "Net Income"
        'display_name': 'Net Income',
        'standard_concept': StandardConcept.NET_INCOME,
        'statement_types': ['IncomeStatement'],
        'period_type': 'duration',
        'category': 'income'
    },

    StandardConcept.TOTAL_ASSETS.value: {  # "Total Assets"
        'display_name': 'Total Assets',
        'standard_concept': StandardConcept.TOTAL_ASSETS,
        'statement_types': ['BalanceSheet'],
        'period_type': 'instant',
        'category': 'balance'
    },

    # Segment metrics - dimensional breakdown
    'revenue_by_segment': {
        'display_name': 'Revenue by Segment',
        'standard_concept': StandardConcept.REVENUE,
        'statement_types': ['SegmentDisclosure'],
        'has_dimensions': True,
        'dimension_axis': 'ProductOrServiceAxis',
        'category': 'segment',
        'period_type': 'duration'
    }
}
```

**Three-Tier Extraction Implementation:**

```python
from edgar.xbrl.standardization import initialize_default_mappings, StandardConcept

# Initialize MappingStore (singleton - load once)
MAPPING_STORE = initialize_default_mappings(read_only=True)

def extract_metric_three_tier(xbrl, metric_name, config, db):
    """
    Three-tier resolution:
    1. Check our DB mappings (Tier 1)
    2. Fall back to EdgarTools MappingStore (Tier 2)
    3. Dead letter queue if still not found (Tier 3)
    """

    # TIER 1: Check our own DB first
    db_mapping = db.query("""
        SELECT concept FROM metric_concept_mappings
        WHERE metric_name = %s AND company_id = %s
    """, (metric_name, xbrl.entity_info['cik']))

    if db_mapping:
        # Use our custom mapping
        concept = db_mapping[0]['concept']
        facts = extract_fact_by_concept(xbrl, concept, config)
        if facts:
            return {'found': True, 'value': facts, 'tier': 1, 'concept_used': concept}

    # TIER 2: Try EdgarTools MappingStore
    standard_concept = config.get('standard_concept')
    if standard_concept:
        # Get all concepts that map to this standard label
        mapped_concepts = MAPPING_STORE.get_company_concepts(standard_concept.value)

        for concept in mapped_concepts:
            facts = extract_fact_by_concept(xbrl, concept, config)
            if facts:
                # Success! Store this mapping back to Tier 1 (self-learning)
                db.insert("""
                    INSERT INTO metric_concept_mappings (metric_name, company_id, concept, source)
                    VALUES (%s, %s, %s, 'edgartools_mapping_store')
                    ON CONFLICT DO NOTHING
                """, (metric_name, xbrl.entity_info['cik'], concept))

                return {
                    'found': True,
                    'value': facts,
                    'tier': 2,
                    'concept_used': concept,
                    'learned': True  # Flag that we learned this mapping
                }

    # TIER 3: Not found - add to Dead Letter Queue
    db.insert("""
        INSERT INTO dead_letter_queue (company_id, metric_name, filing_accession, attempted_concepts, created_at)
        VALUES (%s, %s, %s, %s, NOW())
    """, (xbrl.entity_info['cik'], metric_name, filing.accession_number, list(mapped_concepts)))

    return {'found': False, 'tier': 3}


def extract_fact_by_concept(xbrl, concept, config):
    """Helper: Extract fact for a specific concept."""
    query = (xbrl.facts.query()
            .by_concept(concept, exact=True)
            .by_statement_type(config['statement_types'][0]))

    # Handle dimensional vs consolidated
    if not config.get('has_dimensions', False):
        query = query.exclude_dimensions()  # ← Critical for consolidated metrics
    else:
        query = query.by_dimension(config['dimension_axis'])

    facts = query.to_dataframe()

    if len(facts) > 0:
        return {
            'value': facts.iloc[0]['numeric_value'],
            'period_end': facts.iloc[0]['period_end'],
            'period_key': facts.iloc[0]['period_key']
        }
    return None
```

**DLQ Self-Improvement Loop:**

```python
# Weekly DLQ review (manual step)
def review_dead_letter_queue():
    """Human reviews DLQ and resolves mappings."""
    dlq_entries = db.query("SELECT * FROM dead_letter_queue WHERE resolved = FALSE")

    for entry in dlq_entries:
        # Human examines filing, picks correct concept
        # (Could be via UI, CSV export/import, etc.)
        correct_concept = human_input(f"What concept for {entry['metric_name']} in {entry['company_id']}?")

        if correct_concept:
            # Add to Tier 1
            db.insert("""
                INSERT INTO metric_concept_mappings (metric_name, company_id, concept, source)
                VALUES (%s, %s, %s, 'manual_dlq_resolution')
            """, (entry['metric_name'], entry['company_id'], correct_concept))

            # Optionally: write to company_mappings JSON for sharing
            write_to_company_mapping_json(entry['company_id'], entry['metric_name'], correct_concept)

            # Mark as resolved
            db.update("UPDATE dead_letter_queue SET resolved = TRUE WHERE id = %s", (entry['id'],))

            # Re-run extraction for this company
            reprocess_filing(entry['company_id'], entry['filing_accession'])
```

**Hierarchy-Aware Extraction (Prevents Double-Counting):**

See **Phase 2** in the Roadmap section below for full implementation of parent-wins logic using `exclude_dimensions()` and hierarchy rules.
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
│  │    - Apply standardization (MappingStore)               │ │
│  │    - Extract metrics using three-tier resolution        │ │
│  │    - Calculate derived metrics                          │ │
│  │    - Handle missing metrics (DLQ)                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           ↓                                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 4. TTM CALCULATION (using XBRLS stitching)             │ │
│  │    - XBRLS.from_filings(last 4 quarters)                │ │
│  │    - by_fiscal_period("Q1"|"Q2"|"Q3"|"Q4")              │ │
│  │    - Sum income statement/cash flow line items          │ │
│  │    - Use most recent quarter for balance sheet          │ │
│  │    - Store as separate statements (period_type='TTM')   │ │
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
from edgar.xbrl.stitching import XBRLS
from edgar.xbrl.standardization import initialize_default_mappings
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
        # Initialize MappingStore once (points to our own copy)
        self.mapping_store = initialize_default_mappings(read_only=True)

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
                # Get statement (using correct API)
                if stmt_type == 'IncomeStatement':
                    stmt = xbrl.statements.income_statement()
                elif stmt_type == 'BalanceSheet':
                    stmt = xbrl.statements.balance_sheet()
                elif stmt_type == 'CashFlowStatement':
                    stmt = xbrl.statements.cash_flow_statement()
                else:
                    continue

                # Convert to dataframe (with standardization)
                df = stmt.to_dataframe(standard=True)

                # Structure line items
                line_items = []
                for _, row in df.iterrows():
                    concept = row.get('concept', '')

                    # Apply standardization
                    standard_label = self.mapping_store.get_standard_concept(concept)

                    line_items.append({
                        'label': row.get('label', ''),
                        'standard_label': standard_label,  # Add standardized label
                        'concept': concept,
                        'value': float(row.get('value', 0)) if pd.notna(row.get('value')) else None,
                        'level': int(row.get('level', 0)),  # Correct field name
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

## Additional Considerations

### 1. What EdgarTools CAN'T Do Directly

These are areas where we must build our own logic in the pipeline:

#### A. TTM Calculation
**EdgarTools provides:** Quarterly and annual data via XBRL

**We must implement:**
- Sum last 4 quarters for income statement/cash flow metrics
- Use most recent quarter balance sheet for point-in-time metrics
- Use `XBRLS.from_filings()` + `by_fiscal_period()` for precise quarter selection

#### B. DB Storage / Serialization
**EdgarTools provides:** Rich Table objects, pandas DataFrames

**We must implement:**
- JSONB serialization for statements
- Database schema design
- Query optimization for frontend

#### C. Period Alignment Across Fiscal Calendars
**EdgarTools provides:** `fiscal_period` field ("Q1", "Q2", "Q3", "Q4", "FY")

**We must implement:**
- Tolerance-window logic for cross-company comparison (±45 days)
- Fiscal calendar normalization (Apple Sept vs Microsoft June)
- `period_key` indexing for fast queries

#### D. Derived Metrics (Ratios, Margins, Growth Rates)
**EdgarTools provides:** Base metrics from XBRL

**We must implement:**
- Ratio calculations (gross_margin = gross_profit / revenue)
- Growth rates (revenue_growth_yoy = (current - prior) / prior)
- Multi-metric formulas (ROIC, FCF yield, etc.)

#### E. Dimensional Rollups (Segment Aggregation)
**EdgarTools provides:** Individual segment facts via `by_dimension()`

**We must implement:**
- Aggregation logic (sum revenue across all products)
- Hierarchy understanding (Americas = US + Canada + LatAm)
- Rollup validation (segments sum to consolidated)

---

### 2. What EdgarTools DOES Provide (Leverage, Don't Reinvent!)

#### A. `concept_mappings.json` - Bootstrap Our Mapping
**What it provides:** 100+ standard labels → 500+ XBRL concept variants

**How to use:**
1. Copy to our repo as starting point
2. Track as git subfile for updates
3. Periodically diff against upstream for new mappings
4. Use `MappingStore` as live runtime fallback (Tier 2)

```bash
# Bootstrap (Day 1)
cp edgar/xbrl/standardization/concept_mappings.json pipeline/concept_mappings/

# Weekly sync (check for upstream updates)
diff edgar/xbrl/standardization/concept_mappings.json pipeline/concept_mappings/
```

#### B. `MappingStore` - Use as Live Fallback
**What it provides:** Runtime concept resolution with priority system

**How to use:** See Three-Tier Resolution in Feature 2 above

#### C. `company_mappings/` Pattern - Replicate for Our Universe
**What it provides:** Per-company custom concept mappings (MSFT, TSLA, BRKA templates)

**How to use:** See Phase 3 (Automated Company Mapping Generation) in Roadmap below

#### D. `StandardConcept` Enum - Use as Canonical Keys
**What it provides:** 100+ canonical metric names

**How to use:**
```python
# Our metrics_catalog keys should align with StandardConcept values
METRICS_CATALOG = {
    StandardConcept.REVENUE.value: {...},  # "Revenue"
    StandardConcept.NET_INCOME.value: {...},  # "Net Income"
}
```

#### E. Hierarchy Rules - Import to Prevent Double-Counting
**What it provides:** Parent-child relationships in `concept_mappings.json` comments + `company_mappings` hierarchy_rules

**How to use:** See Phase 2 (Hierarchy-Aware Extraction) in Roadmap below

#### F. `utils.py` Validation - Catch Conflicts
**What it provides:** `validate_mappings()`, `export_to_csv()`, `import_from_csv()`

**How to use:**
```python
from edgar.xbrl.standardization.utils import validate_mappings

report = validate_mappings(our_mapping_store)
if report.has_errors:
    for error in report.errors:
        print(f"CONFLICT: {error}")
```

---

### 3. DLQ → Self-Improvement Loop

**Complete feedback cycle:**

```
1. Extraction fails → INSERT INTO dead_letter_queue
2. Weekly DLQ review → Human picks correct concept
3. Add to metric_concept_mappings (Tier 1) → Self-learning
4. Optionally write to company_mappings/{ticker}_mappings.json → Share knowledge
5. Re-run extraction for company → Validate fix
6. Periodically compare against EdgarTools upstream → Discover new mappings
7. Optionally contribute findings back to EdgarTools → Open source contribution
```

**Implementation:**
```python
# Weekly review workflow
def review_and_resolve_dlq():
    dlq = db.query("SELECT * FROM dead_letter_queue WHERE resolved = FALSE")

    for entry in dlq:
        # Human examines filing, picks correct concept (via UI or CSV)
        correct_concept = get_human_resolution(entry)

        if correct_concept:
            # Add to Tier 1 (our DB)
            db.insert("metric_concept_mappings", {
                'metric_name': entry['metric_name'],
                'company_id': entry['company_id'],
                'concept': correct_concept,
                'source': 'manual_dlq_resolution'
            })

            # Optionally persist to company mapping JSON (for sharing)
            update_company_mapping_file(entry['company_id'], entry['metric_name'], correct_concept)

            # Mark resolved
            db.update("dead_letter_queue", {'id': entry['id']}, {'resolved': True})

            # Re-extract this company
            reprocess_filing(entry['company_id'], entry['filing_accession'])
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

---

## Future Improvements & Roadmap

### Phase 1: MVP (Months 1-2)
- ✅ Extract 3 core statements (Income, Balance, Cash Flow)
- ✅ Extract ~20 key metrics (revenue, net income, assets, debt, etc.)
- ✅ Calculate TTM
- ✅ Store in database
- ✅ Basic SvelteKit UI to display statements

### Phase 1.5: Bootstrap from EdgarTools Standardization (Day 1 - Critical!)
**Why this is immediate:** EdgarTools ships 100+ concepts → 500+ variants. Copy these files = 80%+ coverage before writing custom logic.

**Tasks:**
1. Copy `edgar/xbrl/standardization/concept_mappings.json` to our repo
2. Copy `edgar/xbrl/standardization/company_mappings/*.json` (MSFT, TSLA, BRKA templates)
3. Initialize `MappingStore` in pipeline pointing to our copy
4. Export to CSV for human review: `export_mappings_to_csv(store, "audit.csv")`
5. Set up weekly diff check against upstream EdgarTools

**Implementation:** See detailed execution in the plan file (`/root/.claude/plans/stateful-dazzling-music.md` lines 163-248)

**Outcome:** Day 1 coverage of ~500+ XBRL concept variants without writing mapping logic

### Phase 2: Hierarchy-Aware Extraction (Week 2)
**Why this matters:** Apple reports Revenue ($383B) + Product Revenue ($205B) + Service Revenue ($178B). Naively extracting all = $766B (double-counted!).

**Tasks:**
1. Load hierarchy rules from `concept_mappings.json` comments + `company_mappings` hierarchy_rules
2. Implement parent-wins logic: if parent concept found, don't sum children
3. Critical: Use `exclude_dimensions()` to get consolidated-only facts
4. Add `is_parent` and `parent_metric` columns to `company_metrics` table
5. Store child metrics separately when parent not reported

**Implementation:** See detailed code in the plan file (lines 252-410)

**Outcome:** Prevents revenue/expense double-counting; correctly handles hierarchical concepts

### Phase 3: Automated Company Mapping Generation (Week 3-4)
**Scale to S&P 500:** Auto-generate `company_mappings/{ticker}_mappings.json` for 500+ companies using fuzzy label matching.

**Tasks:**
1. Script to identify company-extension concepts (prefix ≠ `us-gaap/srt/dei`)
2. Fuzzy-match labels against `StandardConcept` enum using `SequenceMatcher`
3. Auto-accept confidence ≥ 0.75; flag 0.55-0.74 for review; reject < 0.55
4. Write to `company_mappings/{ticker}_mappings.json` with metadata
5. Weekly CSV export/import workflow for human review of flagged mappings
6. Re-run extraction after resolving DLQ entries

**Implementation:** See full automation script in the plan file (lines 415-623)

**Outcome:** Company-specific mappings for S&P 500/QQQ; self-improving via DLQ feedback

### Phase 4: Enhanced Metrics (Months 3-4)
- 📊 Expand to ~50 metrics
- 📊 Add derived metrics (margins, ratios)
- 📊 Segment/product revenue breakdown
- 📊 Geographic revenue breakdown
- 📊 Dead letter queue UI for manual review
- 📊 Concept mapping expansion

### Phase 3: Advanced Features (Months 5-6)
- 🎯 Peer comparison (automatic industry grouping)
- 🎯 Historical trend analysis
- 🎯 Anomaly detection (unusual metric changes)
- 🎯 Custom metric builder (user-defined formulas)
- 🎯 Metric alerts (notify when metric crosses threshold)

### Phase 4: AI-Enhanced (Months 7-9)
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

| Category | Current | Phase 2 | Phase 3 | Phase 4 |
|----------|---------|---------|---------|---------|
| Income Statement | 10 | 20 | 30 | 50 |
| Balance Sheet | 8 | 15 | 25 | 40 |
| Cash Flow | 6 | 12 | 20 | 35 |
| Ratios | 5 | 15 | 30 | 50 |
| Segment | 2 | 10 | 20 | 30 |
| Per-Share | 4 | 10 | 15 | 25 |
| **Total** | **35** | **82** | **140** | **230** |

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
  const statement = await db.query(`
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
  `, [ticker, statementType, periodType]);

  return json(statement);
}

// routes/api/metrics/[ticker]/+server.ts

export async function GET({ params, url }) {
  const { ticker } = params;
  const metricNames = url.searchParams.get('metrics')?.split(',') || [];
  const periods = parseInt(url.searchParams.get('periods') || '12');

  const metrics = await db.query(`
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
  `, [ticker, metricNames, periods]);

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
