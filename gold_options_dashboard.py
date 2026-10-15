@st.cache_data(ttl=20, show_spinner=False)
def fetch_live_options_data(symbol, expiration_date=None):
    """جلب مباشر عبر بروكسي وسيط لتجاوز حجب Yahoo"""
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return None, None, None, None
    
    # قائمة البروكسيات - نجرب واحداً تلو الآخر
    proxies = [
        "https://corsproxy.io/?url=",
        "https://api.allorigins.win/raw?url=",
        "https://api.codetabs.com/v1/proxy?quest=",
    ]
    
    def try_fetch(yahoo_url):
        """يجرب كل البروكسيات + الاتصال المباشر"""
        # 1. محاولة مباشرة أولاً
        try:
            session = curl_requests.Session(impersonate="chrome120")
            r = session.get(yahoo_url, timeout=10)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        
        # 2. جرب البروكسيات
        for proxy in proxies:
            try:
                proxied = proxy + yahoo_url
                session = curl_requests.Session(impersonate="chrome120")
                r = session.get(proxied, timeout=15)
                if r.status_code == 200:
                    return r.json()
            except Exception:
                continue
        return None
    
    try:
        # ============ 1. السعر الحالي ============
        current_price = None
        for domain in ["query1", "query2"]:
            data = try_fetch(f"https://{domain}.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d")
            if data:
                result = data.get('chart', {}).get('result', [])
                if result:
                    meta = result[0].get('meta', {})
                    current_price = meta.get('regularMarketPrice')
                    if current_price:
                        break
        
        if not current_price:
            return None, None, None, None
        
        # ============ 2. تواريخ الانتهاء ============
        expirations = []
        for domain in ["query1", "query2"]:
            data = try_fetch(f"https://{domain}.finance.yahoo.com/v7/finance/options/{symbol}")
            if data:
                ts_list = data.get('optionChain', {}).get('result', [{}])[0].get('expirationDates', [])
                if ts_list:
                    expirations = [datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d') for ts in ts_list]
                    break
        
        if not expirations:
            return None, None, None, None
        
        if expiration_date is None or expiration_date not in expirations:
            expiration_date = expirations[0]
        
        # ============ 3. سلسلة الخيارات ============
        calls_data, puts_data = [], []
        for domain in ["query1", "query2"]:
            exp_ts = int(datetime.datetime.strptime(expiration_date, "%Y-%m-%d").timestamp())
            data = try_fetch(f"https://{domain}.finance.yahoo.com/v7/finance/options/{symbol}?date={exp_ts}")
            if data:
                result = data.get('optionChain', {}).get('result', [{}])[0]
                calls_data = result.get('options', [{}])[0].get('calls', [])
                puts_data = result.get('options', [{}])[0].get('puts', [])
                if calls_data and puts_data:
                    break
        
        if not calls_data or not puts_data:
            return None, None, None, None
        
        # ============ 4. بناء DataFrame ============
        calls_df = pd.DataFrame([{
            'strike': c.get('strike', 0),
            'openInterest': c.get('openInterest', 0) or 0,
            'impliedVolatility': c.get('impliedVolatility', 0.001) or 0.001,
        } for c in calls_data])
        
        puts_df = pd.DataFrame([{
            'strike': p.get('strike', 0),
            'openInterest': p.get('openInterest', 0) or 0,
            'impliedVolatility': p.get('impliedVolatility', 0.001) or 0.001,
        } for p in puts_data])
        
        df = pd.merge(
            calls_df[['strike', 'openInterest', 'impliedVolatility']],
            puts_df[['strike', 'openInterest', 'impliedVolatility']],
            on='strike', how='outer', suffixes=('_call', '_put')
        )
        
        df.fillna({'openInterest_call': 0, 'openInterest_put': 0,
                   'impliedVolatility_call': 0.001, 'impliedVolatility_put': 0.001}, inplace=True)
        
        total_oi = df['openInterest_call'] + df['openInterest_put']
        df['weighted_IV'] = np.where(total_oi > 0,
                                     (df['openInterest_call'] * df['impliedVolatility_call'] +
                                      df['openInterest_put'] * df['impliedVolatility_put']) / total_oi,
                                     (df['impliedVolatility_call'] + df['impliedVolatility_put']) / 2)
        
        exp_date_obj = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
        days_to_exp = max((exp_date_obj - datetime.datetime.now()).days, 1)
        T = days_to_exp / 365.0
        
        return float(current_price), expiration_date, df, float(T)
    except Exception:
        return None, None, None, None
