import yfinance as yf
import pandas as pd
import numpy as np
import json
import datetime

SYMBOL = "GLD"
OUTPUT_JSON = "options_data.json"
OUTPUT_CSV = "mt4_gamma_levels.csv"

# 🔴 ضع هنا السعر الذي يظهر في شارت ميتاتريدر الخاص بك (مثلاً 4000 أو 2400)
# إذا تغير السعر لاحقاً بشكل كبير، يمكنك تعديله
CURRENT_MT4_PRICE = 4000.0 

def fetch_data():
    try:
        ticker = yf.Ticker(SYMBOL)
        hist = ticker.history(period='1d')
        if hist.empty: hist = ticker.history(period='5d')
        current_gld_price = float(hist['Close'].iloc[-1])

        # حساب معامل التحويل بدقة (سعر شارتك مقسوماً على سعر GLD)
        final_ratio = CURRENT_MT4_PRICE / current_gld_price

        all_exps = ticker.options
        if not all_exps:
            print("No expirations found")
            return

        exp_date = all_exps[0]
        chain = ticker.option_chain(exp_date)
        calls = chain.calls
        puts = chain.puts

        # حساب غاما حقيقية بناءً على حجم التداول
        calls['net_gamma'] = calls['openInterest'] * 100
        puts['net_gamma'] = puts['openInterest'] * -100

        df_calls = calls[['strike', 'openInterest', 'impliedVolatility', 'net_gamma']].rename(columns={'openInterest': 'oi_c', 'impliedVolatility': 'iv_c'})
        df_puts = puts[['strike', 'openInterest', 'impliedVolatility', 'net_gamma']].rename(columns={'openInterest': 'oi_p', 'impliedVolatility': 'iv_p', 'net_gamma': 'net_gamma_p'})

        df = pd.merge(df_calls, df_puts, on='strike', how='outer')
        df.fillna(0, inplace=True)

        df['net_gamma'] = df['net_gamma'] + df['net_gamma_p']
        
        # فلترة المستويات التي تحتوي على عقود حقيقية فقط
        df_filtered = df[(df['oi_c'] > 0) | (df['oi_p'] > 0)]

        exp_obj = datetime.datetime.strptime(exp_date, "%Y-%m-%d")
        days_to_exp = max((exp_obj - datetime.datetime.now()).days, 1)
        T = days_to_exp / 365.0

        # 1. حفظ في JSON (لمنصة Streamlit)
        data = {
            "last_updated": datetime.datetime.now().isoformat(),
            "symbols": {
                SYMBOL: {
                    "current_price": current_gld_price,
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

        # 2. توليد ملف CSV لميتاتريدر
        top_levels = df_filtered.reindex(df_filtered['net_gamma'].abs().sort_values(ascending=False).index).head(10)

        with open(OUTPUT_CSV, mode='w', newline='') as f:
            f.write("Price,GammaValue,Type,OriginalGLD\n")
            for _, row in top_levels.iterrows():
                strike = round(row['strike'], 2)
                gamma = round(row['net_gamma'], 2)
                lvl_type = "CALL" if gamma > 0 else "PUT"
                converted_strike = round(strike * final_ratio, 2) # التحويل للسعر الذي تراه في شارتك
                f.write(f"{converted_strike},{gamma},{lvl_type},{strike}\n")

        print(f"✅ Success. Chart Price: {CURRENT_MT4_PRICE}, GLD Price: {current_gld_price}, Ratio: {final_ratio:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fetch_data()
