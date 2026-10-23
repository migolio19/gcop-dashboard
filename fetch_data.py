import yfinance as yf
import pandas as pd
import numpy as np
import json
import datetime

SYMBOL = "GLD"
OUTPUT_JSON = "options_data.json"
OUTPUT_CSV = "mt4_gamma_levels.csv"

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
        calls = chain.calls
        puts = chain.puts

        # حساب قوة الغاما بناءً على حجم العقود المفتوحة (OI)
        calls['net_gamma'] = calls['openInterest'] * 100
        puts['net_gamma'] = puts['openInterest'] * -100

        df_calls = calls[['strike', 'openInterest', 'impliedVolatility', 'net_gamma']].rename(columns={'openInterest': 'oi_c', 'impliedVolatility': 'iv_c'})
        df_puts = puts[['strike', 'openInterest', 'impliedVolatility', 'net_gamma']].rename(columns={'openInterest': 'oi_p', 'impliedVolatility': 'iv_p', 'net_gamma': 'net_gamma_p'})

        df = pd.merge(df_calls, df_puts, on='strike', how='outer')
        df.fillna(0, inplace=True)

        # دمج الغاما (كول + بوت)
        df['net_gamma'] = df['net_gamma'] + df['net_gamma_p']
        
        # فلترة المستويات التي تحتوي على عقود فعلية (نتجاهل الأصفار)
        df_filtered = df[(df['oi_c'] > 0) | (df['oi_p'] > 0)]

        exp_obj = datetime.datetime.strptime(exp_date, "%Y-%m-%d")
        days_to_exp = max((exp_obj - datetime.datetime.now()).days, 1)
        T = days_to_exp / 365.0

        # 1. حفظ في JSON (لمنصة Streamlit)
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

        # 2. حساب معامل التحويل ليتطابق مع شارت XAUUSD الخاص بك
        gc = yf.Ticker("GC=F")
        gc_hist = gc.history(period='1d')
        gc_price = float(gc_hist['Close'].iloc[-1]) if not gc_hist.empty else 2350.0
        
        ratio = gc_price / current_price
        
        # 🔴 هام: إذا كان شارت ميتاتريدر الخاص بك يظهر 4000 (بينما السعر الحقيقي 2400)، 
        # يمكنك تعديل هذا الرقم يدوياً ليتطابق (مثلاً 1.66). اتركه 1.0 ليتطابق مع الأسعار الحقيقية.
        BROKER_ADJUSTMENT = 1.0 
        final_ratio = ratio * BROKER_ADJUSTMENT

        # أخذ أقوى 10 مستويات
        top_levels = df_filtered.reindex(df_filtered['net_gamma'].abs().sort_values(ascending=False).index).head(10)

        with open(OUTPUT_CSV, mode='w', newline='') as f:
            f.write("Price,GammaValue,Type,OriginalGLD\n")
            for _, row in top_levels.iterrows():
                strike = round(row['strike'], 2)
                gamma = round(row['net_gamma'], 2)
                lvl_type = "CALL" if gamma > 0 else "PUT"
                converted_strike = round(strike * final_ratio, 2)
                f.write(f"{converted_strike},{gamma},{lvl_type},{strike}\n")

        print(f"✅ Success. CSV Generated. Ratio: {final_ratio:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fetch_data()
