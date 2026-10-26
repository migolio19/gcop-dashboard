import yfinance as yf
import pandas as pd
import numpy as np
import json
import datetime
from scipy.stats import norm

SYMBOL = "GLD"
OUTPUT_JSON = "options_data.json"
OUTPUT_CSV = "mt4_gamma_levels.csv"

# دالة رياضية لحساب الغاما الحقيقية (Black-Scholes)
def calculate_gamma(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0: return 0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))

def fetch_data():
    try:
        ticker = yf.Ticker(SYMBOL)
        hist = ticker.history(period='1d')
        if hist.empty: hist = ticker.history(period='5d')
        current_price = float(hist['Close'].iloc[-1])

        all_exps = ticker.options
        if not all_exps:
            print("No expirations found")
            return

        exp_date = all_exps[0]
        chain = ticker.option_chain(exp_date)
        calls = chain.calls.copy()
        puts = chain.puts.copy()

        exp_obj = datetime.datetime.strptime(exp_date, "%Y-%m-%d")
        days_to_exp = max((exp_obj - datetime.datetime.now()).days, 1)
        T = days_to_exp / 365.0

        # 1. حساب غاما لكل عقد
        calls['gamma'] = [calculate_gamma(current_price, k, T, 0.05, iv if iv > 0 else 0.001) for k, iv in zip(calls['strike'], calls['impliedVolatility'])]
        puts['gamma'] = [calculate_gamma(current_price, k, T, 0.05, iv if iv > 0 else 0.001) for k, iv in zip(puts['strike'], puts['impliedVolatility'])]

        # 2. حساب الـ GEX (القيمة المطلقة * حجم العقود * 100)
        # TradingView غالباً يعتمد على هذا المقياس لإيجاد الجدران
        calls['gex'] = calls['gamma'] * calls['openInterest'] * 100
        puts['gex'] = puts['gamma'] * puts['openInterest'] * 100 * -1

        # 3. دمج البيانات
        df_calls = calls[['strike', 'openInterest', 'gex']].rename(columns={'openInterest':'oi_c', 'gex':'gex_c'})
        df_puts = puts[['strike', 'openInterest', 'gex']].rename(columns={'openInterest':'oi_p', 'gex':'gex_p'})
        
        df = pd.merge(df_calls, df_puts, on='strike', how='outer').fillna(0)
        
        df['net_gex'] = df['gex_c'] + df['gex_p']
        # لحساب أقوى الجدران، نجمع القيمة المطلقة للكول والبوت
        df['total_gex_wall'] = df['gex_c'].abs() + df['gex_p'].abs()

        # 4. حفظ في JSON (لمنصة Streamlit)
        data = {
            "last_updated": datetime.datetime.now().isoformat(),
            "symbols": {
                SYMBOL: {
                    "current_price": current_price,
                    "expirations": {
                        exp_date: {
                            "T": float(T),
                            "calls": calls[['strike', 'openInterest', 'impliedVolatility']].fillna(0).to_dict('records'),
                            "puts": puts[['strike', 'openInterest', 'impliedVolatility']].fillna(0).to_dict('records')
                        }
                    }
                }
            }
        }
        with open(OUTPUT_JSON, 'w') as f:
            json.dump(data, f, indent=2)

        # 5. تصدير ملف CSV لميتاتريدر (أقوى 10 جدران بناءً على total_gex_wall)
        top_levels = df.sort_values(by='total_gex_wall', ascending=False).head(10)
        
        gc = yf.Ticker("GC=F")
        gc_hist = gc.history(period='1d')
        gc_price = float(gc_hist['Close'].iloc[-1]) if not gc_hist.empty else 2400.0
        ratio = gc_price / current_price

        with open(OUTPUT_CSV, mode='w', newline='') as f:
            f.write("Price,GammaValue,Type,OriginalGLD\n")
            for _, row in top_levels.iterrows():
                strike = round(row['strike'], 2)
                # القوة تعتمد على مجموع الغاما
                strength = round(row['total_gex_wall'], 2)
                
                # تحديد النوع بناءً على أيهما أقوى (الكول أم البوت)
                lvl_type = "CALL" if row['gex_c'] > abs(row['gex_p']) else "PUT"
                
                converted_strike = round(strike * ratio, 2)
                f.write(f"{converted_strike},{strength},{lvl_type},{strike}\n")

        print(f"✅ Success. CSV Generated. Ratio: {ratio:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fetch_data()
