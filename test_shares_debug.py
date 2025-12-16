#!/usr/bin/env python3
"""
Test shares outstanding extraction with debug logging

Usage:
    python test_shares_debug.py GOOGL
    python test_shares_debug.py MSFT
"""

import argparse
from edgar import Company, set_identity

set_identity("Dev Gunning developer-gunning@gmail.com")


def test_shares_extraction(ticker: str):
    """Test shares outstanding extraction with detailed logging."""

    print(f"\n{'='*80}")
    print(f"TESTING SHARES OUTSTANDING EXTRACTION: {ticker}")
    print(f"{'='*80}\n")

    company = Company(ticker)

    try:
        facts = company.get_facts()

        # Strategy 1: Try the direct property
        print("Strategy 1: Direct property (facts.shares_outstanding)")
        try:
            shares = facts.shares_outstanding
            print(f"  Result: {shares}")
            if shares and shares > 0:
                print(f"  ✅ SUCCESS: {shares:,.0f} shares")
                return shares
            else:
                print(f"  ❌ FAILED: Got {shares}")
        except Exception as e:
            print(f"  ❌ ERROR: {e}")

        # Strategy 2: Try us-gaap concepts
        print("\nStrategy 2: Query by us-gaap concepts")

        share_concepts = [
            'us-gaap:CommonStockSharesOutstanding',
            'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic',
            'us-gaap:WeightedAverageNumberOfSharesOutstandingDiluted',
            'us-gaap:CommonStockSharesIssued'
        ]

        for i, concept in enumerate(share_concepts, 1):
            print(f"\n  Attempt {i}: {concept}")
            try:
                # Query without .execute()
                query_result = facts.query().by_concept(concept).latest(1)
                print(f"    Query returned: {type(query_result)}, length: {len(query_result) if query_result else 0}")

                if query_result and len(query_result) > 0:
                    fact = query_result[0]
                    print(f"    Fact object: {fact}")
                    print(f"    Has numeric_value: {hasattr(fact, 'numeric_value')}")

                    if hasattr(fact, 'numeric_value'):
                        val = fact.numeric_value
                        print(f"    Value: {val} (type: {type(val)})")

                        # Try to convert to float
                        try:
                            if val is None or (isinstance(val, str) and val.strip() == ''):
                                print(f"    ❌ Value is None or empty string")
                            else:
                                float_val = float(val)
                                print(f"    Float value: {float_val:,.0f}")
                                if float_val > 0:
                                    print(f"    ✅ SUCCESS: {float_val:,.0f} shares")
                                    return float_val
                                else:
                                    print(f"    ❌ Value not positive: {float_val}")
                        except Exception as e:
                            print(f"    ❌ Float conversion error: {e}")
                    else:
                        print(f"    ❌ No numeric_value attribute")
                else:
                    print(f"    ❌ Query returned empty result")

            except Exception as e:
                print(f"    ❌ ERROR: {e}")
                import traceback
                traceback.print_exc()

        print(f"\n❌ ALL STRATEGIES FAILED")
        return None

    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description='Test shares outstanding extraction')
    parser.add_argument('ticker', help='Stock ticker symbol')

    args = parser.parse_args()

    result = test_shares_extraction(args.ticker)

    print(f"\n{'='*80}")
    print(f"FINAL RESULT: {result:,.0f} shares" if result else "FINAL RESULT: None")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
