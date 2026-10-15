from curl_cffi import requests as curl_requests

def fetch_live_options_data(symbol, expiration_date=None):
    try:
        session = curl_requests.Session(impersonate="chrome120")
        
        # Get price
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d"
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return None, None, None, None
        data = r.json()
        ...
