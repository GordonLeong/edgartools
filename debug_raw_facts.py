"""
Debug raw facts data structure to understand why shares outstanding isn't found

Usage:
    python debug_raw_facts.py MSFT
"""
import argparse
from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")


def debug_raw_facts(ticker: str):
    """Inspect the raw facts object structure."""

    company = Company(ticker)
    print(f"\n{'='*80}")
    print(f"RAW FACTS INSPECTION: {ticker} ({company.name})")
    print(f"{'='*80}\n")

    try:
        facts = company.get_facts()

        # Show facts object type and structure
        print(f"Facts object type: {type(facts)}")
        print(f"Facts attributes: {dir(facts)}\n")

        # Try to access raw data
        if hasattr(facts, 'facts'):
            print(f"✓ Has 'facts' attribute")
            print(f"  Type: {type(facts.facts)}")

            # If it's a dict, show keys
            if isinstance(facts.facts, dict):
                print(f"  Keys: {list(facts.facts.keys())[:10]}")

                # Look for share-related concepts
                share_keys = [k for k in facts.facts.keys() if 'share' in k.lower() or 'stock' in k.lower()]
                print(f"\n  Share-related concepts ({len(share_keys)} found):")
                for key in share_keys[:20]:
                    print(f"    - {key}")

        # Check if it has a data attribute
        if hasattr(facts, 'data'):
            print(f"\n✓ Has 'data' attribute")
            print(f"  Type: {type(facts.data)}")

        # Try the query method directly with debugging
        print(f"\n{'='*80}")
        print("TESTING QUERY API")
        print(f"{'='*80}\n")

        concepts_to_test = [
            'us-gaap:CommonStockSharesOutstanding',
            'CommonStockSharesOutstanding',
            'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic',
            'WeightedAverageNumberOfSharesOutstandingBasic'
        ]

        for concept in concepts_to_test:
            print(f"\nTesting concept: {concept}")
            try:
                # Try without any filters
                result = facts.query().by_concept(concept).execute()
                print(f"  Result (no filters): {len(result) if result else 0} facts")

                if result and len(result) > 0:
                    print(f"  First fact: {result[0]}")
                    print(f"  Value: {result[0].numeric_value if hasattr(result[0], 'numeric_value') else 'N/A'}")
                    print(f"  Date: {result[0].end_date if hasattr(result[0], 'end_date') else 'N/A'}")

                # Try with latest
                result = facts.query().by_concept(concept).latest(1).execute()
                print(f"  Result (latest): {len(result) if result else 0} facts")

                if result and len(result) > 0:
                    print(f"  Value: {result[0].numeric_value if hasattr(result[0], 'numeric_value') else 'N/A'}")

            except Exception as e:
                print(f"  ❌ Error: {str(e)[:150]}")

        # Try to get facts using alternative access patterns
        print(f"\n{'='*80}")
        print("ALTERNATIVE ACCESS PATTERNS")
        print(f"{'='*80}\n")

        # Try direct attribute access
        try:
            if hasattr(facts, 'get_facts'):
                print("✓ Has get_facts() method")
                result = facts.get_facts()
                print(f"  Result type: {type(result)}")
        except Exception as e:
            print(f"❌ get_facts() error: {e}")

        # Try accessing by standard concept names
        try:
            # Check what methods are available
            methods = [m for m in dir(facts) if not m.startswith('_')]
            print(f"\nAvailable methods: {methods[:10]}...")

        except Exception as e:
            print(f"❌ Error: {e}")

    except Exception as e:
        print(f"❌ Error accessing facts: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description='Debug raw facts data structure')
    parser.add_argument('ticker', help='Company ticker symbol')

    args = parser.parse_args()
    debug_raw_facts(args.ticker)


if __name__ == "__main__":
    main()
