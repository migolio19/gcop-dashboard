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
        current_price = ticker.fast_info.last_price
        if not current_price:
            current_price = ticker.history(period='1d')['Close'].iloc[-1]
            
        all_exps = ticker.options
        if not all_exps:
            print("No expirations found")
            return
            
        exp_date = all_exps[0]
        chain = ticker.option_chain(exp_date)
        calls = chain.calls
        puts = chain.puts
        
        exp_obj = datetime.datetime.strptime(exp_date, "%Y-%m-%d")
        days_to_exp = max((exp_obj - datetime.datetime.now()).days, 1)
        T = days_to_exp / 365.0
        
        df = pd.merge(calls[['strike', 'openInterest', 'impliedVolatility']],
                      puts[['strike', 'openInterest', 'impliedVolatility']],
                      on='strike', how='outer', suffixes=('_call', '_put'))
        
        df.fillna({'openInterest_call': 0, 'openInterest_put': 0,
                   'impliedVolatility_call': 0.001, 'impliedVolatility_put': 0.001}, inplace=True)
                   
        # 1. حفظ في JSON (لمنصة Streamlit)
        data = {
            "last_updated": datetime.datetime.now().isoformat(),
            "symbols": {
                SYMBOL: {
                    "current_price": float(current_price),
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
            
        # 2. تصدير ملف CSV (لميتاتريدر) مع حساب معامل التحويل لـ GC=F
        gc_ticker = yf.Ticker("GC=F")
        gc_price = gc_ticker.fast_info.last_price
        if not gc_price:
            gc_price = gc_ticker.history(period='1d')['Close'].iloc[-1]
            
        ratio = gc_price / current_price if current_price else 1.0
        
        df['net_gamma'] = (df['openInterest_call'] - df['openInterest_put']) * 100
        top_levels = df.reindex(df['net_gamma'].abs().sort_values(ascending=False).index).head(10)
        
        with open(OUTPUT_CSV, mode='w', newline='') as f:
            f.write("Price,GammaValue,Type,OriginalGLD\n")
            for _, row in top_levels.iterrows():
                strike = round(row['strike'], 2)
                gamma = round(row['net_gamma'], 2)
                lvl_type = "CALL" if gamma > 0 else "PUT"
                # تحويل السعر ليطابق أسعار الذهب الآجل (حوالي 4000)
                converted_strike = round(strike * ratio, 2) 
                f.write(f"{converted_strike},{gamma},{lvl_type},{strike}\n")
                
        print(f"✅ Successfully generated JSON and CSV. Conversion Ratio: {ratio:.2f}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fetch_data()
