import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fundamental_fetcher import FundamentalFetcher

def main():
    os.makedirs('tests/fixtures', exist_ok=True)

    basket = ['SAKSOFT', 'GREENPLY', 'ALGOQUANT', 'EMAMILTD', 'HDFCBANK']
    fetcher = FundamentalFetcher()

    output = {}
    print('Dumping fundamental fixtures...')
    for sym in basket:
        print(f'Fetching {sym}...')
        try:
            data = fetcher.fetch(sym)
            output[sym] = data
        except Exception as e:
            print(f'Error fetching {sym}: {e}')

    with open('tests/fixtures/golden_fundamentals.json', 'w') as f:
        json.dump(output, f, indent=2)

    print('Done. Wrote', len(output), 'records to tests/fixtures/golden_fundamentals.json')

if __name__ == '__main__':
    main()
