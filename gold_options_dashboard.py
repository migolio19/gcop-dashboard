@st.cache_data(ttl=120)
def fetch_options_data(symbol, expiration_date=None):
    if symbol == "SPX":
        symbol = "^SPX"
    elif symbol == "NDX":
        symbol = "^NDX"
    
    try:
        # محاولة استخدام curl_cffi مع محاكاة المتصفح (الحل الرسمي لـ yfinance على السحابة)
        try:
            from curl_cffi import requests as curl_requests
            session = curl_requests.Session(impersonate="chrome")
            ticker = yf.Ticker(symbol, session=session)
        except ImportError:
            # fallback إلى requests العادي
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            })
            ticker = yf.Ticker(symbol, session=session)
        
        hist = ticker.history(period="5d")
        if hist.empty:
            hist = ticker.history(period="1mo")
        
        if hist.empty:
            st.error(f"⚠️ لا توجد بيانات للسعر للرمز {symbol}. تحقق من الاتصال أو الرمز.")
            return None, None, None, None
        
        current_price = hist['Close'].iloc[-1]
        all_expirations = ticker.options

        if not all_expirations:
            time.sleep(1)
            all_expirations = ticker.options
        
        if not all_expirations:
            st.warning(f"⚠️ لا توجد تواريخ انتهاء متاحة للرمز {symbol}. قد يكون السوق مغلقاً أو هناك قيود على Yahoo Finance.")
            return None, None, None, None

        if expiration_date is None or expiration_date not in all_expirations:
            expiration_date = all_expirations[0]

        opt = ticker.option_chain(expiration_date)
        calls = opt.calls.copy()
        puts = opt.puts.copy()

        df = pd.merge(calls[['strike','openInterest','impliedVolatility']],
                      puts[['strike','openInterest','impliedVolatility']],
                      on='strike', how='outer', suffixes=('_call','_put'))

        df.fillna({'openInterest_call': 0, 'openInterest_put': 0,
                   'impliedVolatility_call': 0.001, 'impliedVolatility_put': 0.001}, inplace=True)

        total_oi = df['openInterest_call'] + df['openInterest_put']
        df['weighted_IV'] = np.where(total_oi > 0,
                                     (df['openInterest_call'] * df['impliedVolatility_call'] +
                                      df['openInterest_put'] * df['impliedVolatility_put']) / total_oi,
                                     (df['impliedVolatility_call'] + df['impliedVolatility_put']) / 2)

        exp_date_dt = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
        now = datetime.datetime.now()
        T = max((exp_date_dt - now).days / 365.0, 2/365.0)
        return current_price, expiration_date, df, T
        
    except Exception as e:
        st.error(f"⚠️ حدث خطأ أثناء جلب البيانات: {str(e)}")
        return None, None, None, None
