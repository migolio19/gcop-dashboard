import streamlit as st
import pandas as pd
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go
import datetime
from streamlit_autorefresh import st_autorefresh
import zoneinfo
import json
import hashlib
import time
import urllib.request
import os
from collections import deque
import csv

st.set_page_config(page_title="رادار عادل للخيارات الكمية", layout="wide")

CREDENTIALS = {
    "admin": "198200",
    "moha33": "tickmillx33"
}

METRICS_LABELS = {
    "Open Interest": "مركز السيولة (Open Interest)",
    "Gamma Exposure": "قوة الدفع (Gamma Exposure)",
    "Gamma Gold": "قوة الدفع الذهبية (Gamma Gold)",
    "Delta Exposure": "دلتا (Delta Exposure)",
    "Vanna Exposure": "تأثير التقلب (Vanna Exposure)",
    "Vega Exposure": "فيغا (Vega Exposure)",
    "Theta Exposure": "ثيتا (Theta Exposure)",
    "Charm Exposure (x10k)": "سحر الدلتا (Charm Exposure x10k)",
    "Speed Exposure (x10k)": "سرعة غاما (Speed Exposure x10k)",
    "Vomma Exposure": "تسارع التقلب (Vomma Exposure)",
    "Zomma Exposure": "تسارع غاما (Zomma Exposure)",
    "Implied Volatility": "مؤشر القلق (Implied Volatility)",
    "IV Skew": "انحراف التقلب (IV Skew)",
}

DEFAULT_SETTINGS = {
    'iv_skew_call_pct': 1.15,
    'iv_skew_put_pct': 0.85,
    'iv_sma_period': 20,
    'iv_deviation_threshold': 0.20,
    'confluence_pct': 0.30,
}

VISITOR_FILE = "visitors_log.json"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/migolio19/gcop-dashboard/main/options_data.json"

@st.cache_data(ttl=30)
def get_options_metadata():
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        return {
            "last_updated": data.get("last_updated", "Unknown"),
            "symbols": list(data.get("symbols", {}).keys())
        }
    except:
        return {"last_updated": "Unknown", "symbols": []}

@st.cache_data(ttl=30)
def get_available_expirations(symbol):
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        if symbol not in data.get("symbols", {}):
            return []
        return list(data["symbols"][symbol]["expirations"].keys())
    except:
        return []

@st.cache_data(ttl=30)
def get_current_price(symbol):
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        if symbol not in data.get("symbols", {}):
            return None
        return data["symbols"][symbol]["current_price"]
    except:
        return None

@st.cache_data(ttl=30)
def fetch_options_data(symbol, expiration_date=None):
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        st.error(f"❌ فشل قراءة البيانات من GitHub: {e}")
        return None, None, None, None
    
    if symbol not in data.get("symbols", {}):
        st.error(f"No data for {symbol}.")
        return None, None, None, None
    
    symbol_data = data["symbols"][symbol]
    current_price = symbol_data["current_price"]
    all_expirations = list(symbol_data["expirations"].keys())
    
    if not all_expirations:
        st.error(f"No expirations for {symbol}.")
        return None, None, None, None
    
    if expiration_date is None or expiration_date not in all_expirations:
        expiration_date = all_expirations[0]
    
    exp_data = symbol_data["expirations"][expiration_date]
    calls = pd.DataFrame(exp_data["calls"])
    puts = pd.DataFrame(exp_data["puts"])
    T = exp_data["T"]
    
    df = pd.merge(calls[['strike', 'openInterest', 'impliedVolatility']],
                  puts[['strike', 'openInterest', 'impliedVolatility']],
                  on='strike', how='outer', suffixes=('_call', '_put'))
    
    df.fillna({'openInterest_call': 0, 'openInterest_put': 0,
               'impliedVolatility_call': 0.001, 'impliedVolatility_put': 0.001}, inplace=True)
    
    total_oi = df['openInterest_call'] + df['openInterest_put']
    df['weighted_IV'] = np.where(total_oi > 0,
                                 (df['openInterest_call'] * df['impliedVolatility_call'] +
                                  df['openInterest_put'] * df['impliedVolatility_put']) / total_oi,
                                 (df['impliedVolatility_call'] + df['impliedVolatility_put']) / 2)
    
    return current_price, expiration_date, df, T

@st.cache_data(ttl=60)
def fetch_other_instrument_price(ticker_symbol):
    try:
        from curl_cffi import requests as curl_requests
        session = curl_requests.Session(impersonate="chrome120")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker_symbol}?interval=1m&range=1d"
        r = session.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get('chart', {}).get('result', [])
            if result:
                meta = result[0].get('meta', {})
                price = meta.get('regularMarketPrice')
                if price: return float(price)
        return None
    except Exception:
        return None

def get_conversion_ratio(price_gld, price_other):
    if price_other is None or price_gld == 0:
        return 1.0
    return price_other / price_gld

def convert_price(price_gld, ratio):
    return price_gld * ratio

def generate_mt4_csv(df_sorted, sync_ratio=1.0):
    top_levels = df_sorted.reindex(df_sorted['net_gamma'].abs().sort_values(ascending=False).index).head(10)
    csv_content = "Price,GammaValue,Type,OriginalGLD\n"
    for _, row in top_levels.iterrows():
        converted_strike = row['strike'] * sync_ratio
        gamma_val = row['net_gamma']
        original_gld = row['strike']
        lvl_type = "CALL" if gamma_val > 0 else "PUT"
        csv_content += f"{round(converted_strike, 2)},{round(gamma_val, 2)},{lvl_type},{round(original_gld, 2)}\n"
    return csv_content

def calculate_ai_prediction(S, zero_gamma, gex_flow, iv_skew, vanna_net, charm_net):
    score = 0
    reasons = []
    if gex_flow > 0:
        score += 1.5
        reasons.append("🟢 تدفق غاما إيجابي (المشترون يسيطرون على العقود).")
    else:
        score -= 1.5
        reasons.append("🔴 تدفق غاما سلبي (البائعون يسيطرون على العقود).")
    if iv_skew > 0.05:
        score += 1.0
        reasons.append("🟢 انحراف التقلب يميل لصالح الـ Calls (تفاؤل).")
    elif iv_skew < -0.05:
        score -= 1.0
        reasons.append("🔴 انحراف التقلب يميل لصالح الـ Puts (خوف).")
    else:
        reasons.append("⚖️ انحراف التقلب في المنطقة الطبيعية.")
    if vanna_net > 0:
        score += 0.5
        reasons.append("🟢 تدفق فانا إيجابي (دعم من صناع السوق).")
    else:
        score -= 0.5
        reasons.append("🔴 تدفق فانا سلبي (ضغط من صناع السوق).")
    if charm_net > 0:
        score += 0.5
        reasons.append("🟢 تدفق تشارم إيجابي (استقرار دلتا).")
    else:
        score -= 0.5
        reasons.append("🔴 تدفق تشارم سلبي (تسارع دلتا).")

    probability = 1 / (1 + np.exp(-score))
    prob_pct = probability * 100
    confidence = abs(prob_pct - 50) * 2

    if prob_pct > 60:
        prediction = "صعود قوي (Bullish) 🚀"
        color = "limegreen"
    elif prob_pct < 40:
        prediction = "هبوط قوي (Bearish) 📉"
        color = "crimson"
    else:
        prediction = "تذبذب / حيادية (Neutral) ⚖️"
        color = "orange"
    return prediction, color, prob_pct, confidence, reasons

# ... (باقي دوال الحساب الرياضي، GEXHistory، login، إلخ. كما هي في السكريبت السابق) ...
# للاختصار، سأدمجها في النهاية. (يرجى التأكد من نسخ الكود الكامل من المربع أدناه)
