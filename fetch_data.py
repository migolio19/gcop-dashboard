import yfinance as yf
import json
import datetime
import sys

SYMBOLS = {
    "GLD": "GLD",
    "SPY": "SPY",
    "SPX": "^SPX",
    "QQQ": "QQQ",
    "NDX": "^NDX"
}

MAX_EXPIRATIONS = 3

def fetch_symbol_data(symbol_name, ticker_symbol):
    try:
        print(f"Fetching {symbol_name} ({ticker_symbol})...")
        
        try:
            from curl_cffi import requests as curl_requests
            session = curl_requests.Session(impersonate="chrome")
            ticker = yf.Ticker(ticker_symbol, session=session)
        except ImportError:
            ticker = yf.Ticker(ticker_symbol)
        
        hist = ticker.history(period="5d")
        if hist.empty:
            print(f"  X No price data")
            return None
        
        current_price = float(hist['Close'].iloc[-1])
        print(f"  Price: ${current_price:.2f}")
        
        all_exps = ticker.options
        if not all_exps:
            print(f"  X No expirations")
            return None
        
        symbol_data = {
            "current_price": current_price,
            "expirations": {}
        }
        
        now = datetime.datetime.now()
        
        for exp in all_exps[:MAX_EXPIRATIONS]:
            try:
                print(f"    Expiration {exp}...")
                opt = ticker.option_chain(exp)
                
                calls = opt.calls[['strike', 'openInterest', 'impliedVolatility']].to_dict('records')
                puts = opt.puts[['strike', 'openInterest', 'impliedVolatility']].to_dict('records')
                
                calls = [{k: float(v) if v is not None else 0 for k, v in c.items()} for c in calls]
                puts = [{k: float(v) if v is not None else 0 for k, v in p.items()} for p in puts]
                
                exp_date_dt = datetime.datetime.strptime(exp, "%Y-%m-%d")
                T = max((exp_date_dt - now).days / 365.0, 2/365.0)
                
                symbol_data["expirations"][exp] = {
                    "T": float(T),
                    "calls": calls,
                    "puts": puts
                }
                print(f"      OK ({len(calls)} calls, {len(puts)} puts)")
                
            except Exception as e:
                print(f"      X {e}")
        
        if not symbol_data["expirations"]:
            return None
        
        return symbol_data
        
    except Exception as e:
        print(f"X Error: {e}")
        return None

def main():
    print("=" * 50)
    print(f"Fetching data at {datetime.datetime.now()}")
    print("=" * 50)
    
    result = {
        "last_updated": datetime.datetime.now().isoformat(),
        "symbols": {}
    }
    
    for symbol_name, ticker_symbol in SYMBOLS.items():
        data = fetch_symbol_data(symbol_name, ticker_symbol)
        if data:
            result["symbols"][symbol_name] = data
    
    if not result["symbols"]:
        print("\nX No data fetched!")
        sys.exit(1)
    
    with open("options_data.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print("=" * 50)
    print(f"Saved {len(result['symbols'])} symbols")
    print("=" * 50)

if __name__ == "__main__":
    main()
