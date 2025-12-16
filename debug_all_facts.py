#!/usr/bin/env python3
"""
Comprehensive debugger to list ALL facts available in a filing's statements.
This helps identify exactly what labels/concepts companies are using.

Usage:
    python debug_all_facts.py MSFT
    python debug_all_facts.py AAPL --statement income
    python debug_all_facts.py TSLA --filter shares
"""

import argparse
from edgar import Company, set_identity
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

# Set user identity for SEC requests
set_identity("Dev Gunning developer-gunning@gmail.com")

console = Console()


def debug_statement_facts(statement, statement_name: str, filter_term: str = None):
    """Show all facts available in a statement."""

    if statement is None or statement.empty:
        console.print(f"[yellow]No {statement_name} statement available[/yellow]")
        return

    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]{statement_name.upper()} STATEMENT - ALL FACTS[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")

    # Get all rows from the statement
    df = statement

    # Create table
    table = Table(
        title=f"{statement_name} Statement Facts",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta"
    )

    table.add_column("Label", style="cyan", no_wrap=False, width=50)
    table.add_column("Latest Value", style="green", justify="right", width=15)
    table.add_column("Concept", style="yellow", no_wrap=False, width=40)

    # Track facts found
    facts_found = 0
    filtered_out = 0

    for idx, row in df.iterrows():
        label = str(idx)

        # Get the latest value (rightmost column)
        latest_value = None
        for col in reversed(df.columns):
            if row[col] is not None and str(row[col]).strip():
                latest_value = row[col]
                break

        # Try to get concept from the dataframe if available
        concept = ""
        if hasattr(df, 'attrs') and 'concepts' in df.attrs:
            concept = df.attrs['concepts'].get(label, "")

        # Apply filter if specified
        if filter_term:
            search_text = f"{label} {concept}".lower()
            if filter_term.lower() not in search_text:
                filtered_out += 1
                continue

        # Format value
        if latest_value is not None:
            try:
                if isinstance(latest_value, (int, float)):
                    value_str = f"{latest_value:,.0f}"
                else:
                    value_str = str(latest_value)
            except:
                value_str = str(latest_value)
        else:
            value_str = "[dim]N/A[/dim]"

        table.add_row(label, value_str, concept)
        facts_found += 1

    console.print(table)
    console.print(f"\n[bold]Total facts found: {facts_found}[/bold]")
    if filter_term:
        console.print(f"[dim]Filtered out: {filtered_out}[/dim]")


def debug_entity_facts(company, filter_term: str = None):
    """Show facts from entity facts API (contains shares outstanding)."""

    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]ENTITY FACTS (Company Facts API)[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")

    try:
        facts = company.get_facts()

        # Create table for shares-related facts
        table = Table(
            title="Entity Facts",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )

        table.add_column("Concept", style="cyan", no_wrap=False, width=60)
        table.add_column("Latest Value", style="green", justify="right", width=15)
        table.add_column("Date", style="yellow", width=12)

        # Common share concepts to check
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
            if filter_term and filter_term.lower() not in concept.lower():
                continue

            try:
                result = facts.query().by_concept(concept).annual().latest(1).execute()
                if result and len(result) > 0:
                    fact = result[0]
                    value_str = f"{fact.numeric_value:,.0f}" if fact.numeric_value else "N/A"
                    date_str = fact.end_date if hasattr(fact, 'end_date') else "N/A"
                    table.add_row(concept, value_str, str(date_str))
                    facts_found += 1
            except Exception as e:
                console.print(f"[dim]Error querying {concept}: {e}[/dim]")

        if facts_found > 0:
            console.print(table)
            console.print(f"\n[bold]Total facts found: {facts_found}[/bold]")
        else:
            console.print("[yellow]No matching facts found in Entity Facts API[/yellow]")

    except Exception as e:
        console.print(f"[red]Error accessing entity facts: {e}[/red]")


def debug_xbrl_concepts(filing, filter_term: str = None):
    """Show all concepts available in the XBRL filing."""

    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]XBRL CONCEPTS (from filing)[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")

    try:
        xbrl = filing.xbrl()

        if not xbrl:
            console.print("[yellow]No XBRL data available[/yellow]")
            return

        # Create table
        table = Table(
            title="XBRL Concepts",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta"
        )

        table.add_column("Concept", style="cyan", no_wrap=False, width=60)
        table.add_column("Label", style="green", no_wrap=False, width=40)
        table.add_column("Value", style="yellow", justify="right", width=15)

        facts_found = 0

        # Get facts from XBRL
        if hasattr(xbrl, 'facts'):
            for fact in xbrl.facts[:100]:  # Limit to first 100 to avoid overwhelming output
                concept = fact.concept if hasattr(fact, 'concept') else ""
                label = fact.label if hasattr(fact, 'label') else ""
                value = fact.value if hasattr(fact, 'value') else ""

                # Apply filter if specified
                if filter_term:
                    search_text = f"{concept} {label}".lower()
                    if filter_term.lower() not in search_text:
                        continue

                # Format value
                if value:
                    try:
                        value_str = f"{float(value):,.0f}" if value else "N/A"
                    except:
                        value_str = str(value)[:20]
                else:
                    value_str = "N/A"

                table.add_row(concept, label, value_str)
                facts_found += 1

        if facts_found > 0:
            console.print(table)
            console.print(f"\n[bold]Showing first {facts_found} facts[/bold]")
        else:
            console.print("[yellow]No matching XBRL facts found[/yellow]")

    except Exception as e:
        console.print(f"[red]Error accessing XBRL data: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(description='Debug all facts in a filing')
    parser.add_argument('ticker', help='Stock ticker symbol (e.g., MSFT, AAPL)')
    parser.add_argument('--statement', choices=['income', 'balance', 'cashflow', 'all'],
                       default='all', help='Which statement to debug')
    parser.add_argument('--filter', help='Filter facts by keyword (e.g., "shares", "equity")')
    parser.add_argument('--entity-facts', action='store_true',
                       help='Also show entity facts from company facts API')
    parser.add_argument('--xbrl', action='store_true',
                       help='Also show XBRL concepts from filing')

    args = parser.parse_args()

    console.print(Panel(
        f"[bold cyan]Debugging All Facts for {args.ticker}[/bold cyan]",
        expand=False
    ))

    # Get company and filing
    company = Company(args.ticker)
    filings = company.get_filings(form="10-K", amendments=False).latest(1)

    if not filings:
        console.print("[red]No 10-K filings found[/red]")
        return

    filing = filings[0]

    console.print(f"\n[bold]Company:[/bold] {company.name}")
    console.print(f"[bold]Filing:[/bold] {filing.form} - {filing.filing_date}")
    if args.filter:
        console.print(f"[bold]Filter:[/bold] '{args.filter}'")

    # Get financials
    try:
        financials = filing.obj()

        # Debug statements
        if args.statement in ['income', 'all']:
            income_stmt = financials.income_statement()
            debug_statement_facts(income_stmt, "Income", args.filter)

        if args.statement in ['balance', 'all']:
            balance_stmt = financials.balance_sheet()
            debug_statement_facts(balance_stmt, "Balance Sheet", args.filter)

        if args.statement in ['cashflow', 'all']:
            cashflow_stmt = financials.cashflow_statement()
            debug_statement_facts(cashflow_stmt, "Cash Flow", args.filter)

        # Debug entity facts if requested
        if args.entity_facts or args.filter in ['share', 'shares', 'equity', 'stock']:
            debug_entity_facts(company, args.filter)

        # Debug XBRL concepts if requested
        if args.xbrl:
            debug_xbrl_concepts(filing, args.filter)

    except Exception as e:
        console.print(f"\n[red]Error accessing financials: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())


if __name__ == "__main__":
    main()
