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

CREDENTIALS = {"admin": "198200", "moha33": "tickmillx33"}

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

DEFAULT_SETTINGS = {'iv_skew_call_pct': 1.15, 'iv_skew_put_pct': 0.85, 'iv_sma_period': 20, 'iv_deviation_threshold': 0.20, 'confluence_pct': 0.30}
VISITOR_FILE = "visitors_log.json"
GITHUB_RAW_URL = "https://raw.githubusercontent.com/migolio19/gcop-dashboard/main/options_data.json"

@st.cache_data(ttl=30)
def get_options_metadata():
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        return {"last_updated": data.get("last_updated", "Unknown"), "symbols": list(data.get("symbols", {}).keys())}
    except: return {"last_updated": "Unknown", "symbols": []}

@st.cache_data(ttl=30)
def get_available_expirations(symbol):
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        if symbol not in data.get("symbols", {}): return []
        return list(data["symbols"][symbol]["expirations"].keys())
    except: return []

@st.cache_data(ttl=30)
def get_current_price(symbol):
    try:
        req = urllib.request.Request(GITHUB_RAW_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode('utf-8'))
        if symbol not in data.get("symbols", {}): return None
        return data["symbols"][symbol]["current_price"]
    except: return None

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
    
    if not all_expirations: return None, None, None, None
    if expiration_date is None or expiration_date not in all_expirations: expiration_date = all_expirations[0]
    
    exp_data = symbol_data["expirations"][expiration_date]
    calls = pd.DataFrame(exp_data["calls"])
    puts = pd.DataFrame(exp_data["puts"])
    T = exp_data["T"]
    
    df = pd.merge(calls[['strike', 'openInterest', 'impliedVolatility']],
                  puts[['strike', 'openInterest', 'impliedVolatility']],
                  on='strike', how='outer', suffixes=('_call', '_put'))
    
    df.fillna({'openInterest_call': 0, 'openInterest_put': 0, 'impliedVolatility_call': 0.001, 'impliedVolatility_put': 0.001}, inplace=True)
    total_oi = df['openInterest_call'] + df['openInterest_put']
    df['weighted_IV'] = np.where(total_oi > 0, (df['openInterest_call'] * df['impliedVolatility_call'] + df['openInterest_put'] * df['impliedVolatility_put']) / total_oi, (df['impliedVolatility_call'] + df['impliedVolatility_put']) / 2)
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
    except: return None

def get_conversion_ratio(price_gld, price_other):
    if price_other is None or price_gld == 0: return 1.0
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
    if gex_flow > 0: score += 1.5; reasons.append("🟢 تدفق غاما إيجابي.")
    else: score -= 1.5; reasons.append("🔴 تدفق غاما سلبي.")
    if iv_skew > 0.05: score += 1.0; reasons.append("🟢 انحراف التقلب لصالح الكول.")
    elif iv_skew < -0.05: score -= 1.0; reasons.append("🔴 انحراف التقلب لصالح البوت.")
    else: reasons.append("⚖️ انحراف التقلب طبيعي.")
    if vanna_net > 0: score += 0.5; reasons.append("🟢 تدفق فانا إيجابي.")
    else: score -= 0.5; reasons.append("🔴 تدفق فانا سلبي.")
    if charm_net > 0: score += 0.5; reasons.append("🟢 تدفق تشارم إيجابي.")
    else: score -= 0.5; reasons.append("🔴 تدفق تشارم سلبي.")

    probability = 1 / (1 + np.exp(-score))
    prob_pct = probability * 100
    confidence = abs(prob_pct - 50) * 2

    if prob_pct > 60: prediction = "صعود قوي 🚀"; color = "limegreen"
    elif prob_pct < 40: prediction = "هبوط قوي 📉"; color = "crimson"
    else: prediction = "تذبذب ⚖️"; color = "orange"
    return prediction, color, prob_pct, confidence, reasons

def get_visitor_ip_and_country():
    try:
        ip = urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')
        url = f'http://ip-api.com/json/{ip}?fields=status,country,countryCode'
        response = urllib.request.urlopen(url, timeout=5).read().decode('utf8')
        data = json.loads(response)
        if data.get('status') == 'success': return ip, data.get('countryCode', 'UN')
        return ip, 'UN'
    except: return '127.0.0.1', 'Local'

def track_visitors(username=None):
    now = time.time()
    ip, country = get_visitor_ip_and_country()
    visitor_id = hashlib.sha256(ip.encode()).hexdigest()
    if os.path.exists(VISITOR_FILE):
        with open(VISITOR_FILE, 'r') as f:
            try: logs = json.load(f)
            except: logs = []
    else: logs = []
    cutoff = now - (24 * 60 * 60)
    filtered_logs = [log for log in logs if log['timestamp'] > cutoff]
    existing = False
    for log in filtered_logs:
        if log['id'] == visitor_id:
            log['timestamp'] = now; log['country'] = country; log['username'] = username if username else log.get('username', 'visitor')
            existing = True; break
    if not existing:
        filtered_logs.append({'id': visitor_id, 'country': country, 'username': username if username else 'visitor', 'timestamp': now})
    with open(VISITOR_FILE, 'w') as f: json.dump(filtered_logs, f, indent=2)
    return filtered_logs

def display_visitor_widget():
    logs = track_visitors(); total_visitors = len(logs)
    if total_visitors == 0: st.info("لا يوجد زوار."); return
    data = [{'المستخدم': log.get('username', 'visitor'), 'الدولة': log['country'], 'آخر ظهور': datetime.datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %I:%M %p')} for log in logs]
    col1, col2 = st.columns([1, 3])
    with col1: st.metric("زوار فريدون (24 ساعة)", total_visitors)
    with col2: st.dataframe(pd.DataFrame(data), width='stretch', hide_index=True, height=min(200, 35 + 35 * total_visitors))

def login_page():
    st.markdown("""<style>.stTextInput { text-align: center; } .stTextInput > div { display: flex; justify-content: center; } .stTextInput input { text-align: center; max-width: 300px; margin: 0 auto; } .login-title { text-align: center; margin-bottom: 30px; font-size: 28px; font-weight: bold; color: #00d4ff; }</style>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-title">رادار عادل للخيارات الكمية</div>', unsafe_allow_html=True)
        with st.form(key="login_form", clear_on_submit=False):
            username = st.text_input("اسم المستخدم", placeholder="ادخل اسم المستخدم", key="login_username")
            password = st.text_input("كلمة المرور", placeholder="ادخل كلمة المرور", type="password", key="login_password")
            login_btn = st.form_submit_button("دخول", width='stretch')
            if login_btn:
                if username in CREDENTIALS and CREDENTIALS[username] == password:
                    st.session_state.logged_in = True; st.session_state.username = username; st.success(f"مرحباً، {username}"); time.sleep(0.5); st.rerun()
                else: st.error("اسم المستخدم أو كلمة المرور غير صحيحة")

def get_market_status():
    now_ny = datetime.datetime.now(datetime.timezone.utc).astimezone(zoneinfo.ZoneInfo("America/New_York"))
    if now_ny.weekday() >= 5: return "closed", now_ny
    if datetime.time(9, 30) <= now_ny.time() <= datetime.time(16, 0): return "open", now_ny
    return "closed", now_ny

def should_autorefresh(): return get_market_status()[0] == "open"

def d1(S, K, T, r, sigma, q=0.0): return (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
def delta_call(S, K, T, r, sigma, q=0.0): return np.exp(-q * T) * norm.cdf(d1(S, K, T, r, sigma, q))
def delta_put(S, K, T, r, sigma, q=0.0): return np.exp(-q * T) * (norm.cdf(d1(S, K, T, r, sigma, q)) - 1)
def gamma(S, K, T, r, sigma, q=0.0): return np.exp(-q * T) * norm.pdf(d1(S, K, T, r, sigma, q)) / (S * sigma * np.sqrt(T))
def vanna(S, K, T, r, sigma, q=0.0): return -np.exp(-q * T) * norm.pdf(d1(S, K, T, r, sigma, q)) * (d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)) / sigma
def vega(S, K, T, r, sigma, q=0.0): return S * np.exp(-q * T) * norm.pdf(d1(S, K, T, r, sigma, q)) * np.sqrt(T)
def vomma(S, K, T, r, sigma, q=0.0): return vega(S, K, T, r, sigma, q) * d1(S, K, T, r, sigma, q) * (d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)) / sigma
def zomma(S, K, T, r, sigma, q=0.0): return gamma(S, K, T, r, sigma, q) * (d1(S, K, T, r, sigma, q) * (d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)) - 1) / sigma
def theta_call(S, K, T, r, sigma, q=0.0):
    d1_val, d2_val = d1(S, K, T, r, sigma, q), d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)
    return -(S * np.exp(-q * T) * norm.pdf(d1_val) * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2_val) + q * S * np.exp(-q * T) * norm.cdf(d1_val)
def theta_put(S, K, T, r, sigma, q=0.0):
    d1_val, d2_val = d1(S, K, T, r, sigma, q), d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)
    return -(S * np.exp(-q * T) * norm.pdf(d1_val) * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2_val) - q * S * np.exp(-q * T) * norm.cdf(-d1_val)
def charm_call(S, K, T, r, sigma, q=0.0):
    d1_val, d2_val = d1(S, K, T, r, sigma, q), d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)
    return -np.exp(-q * T) * norm.pdf(d1_val) * (2 * (r - q) * T - d2_val * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T)) + q * np.exp(-q * T) * norm.cdf(d1_val)
def charm_put(S, K, T, r, sigma, q=0.0): return charm_call(S, K, T, r, sigma, q) - q * np.exp(-q * T)
def speed(S, K, T, r, sigma, q=0.0): return -gamma(S, K, T, r, sigma, q) * (d1(S, K, T, r, sigma, q) / (sigma * np.sqrt(T)) + 1) / S

class GEXHistory:
    def __init__(self, max_minutes=60): self.history = deque(maxlen=max_minutes)
    def add(self, net_gex): self.history.append((datetime.datetime.now(), net_gex))
    def get_60min_ago(self):
        if len(self.history) < 2: return None
        target = datetime.datetime.now() - datetime.timedelta(minutes=60)
        for ts, val in self.history:
            if ts <= target: return val
        return self.history[0][1] if self.history else None

if 'gex_history' not in st.session_state: st.session_state.gex_history = GEXHistory()

def calculate_iv_skew(df, S, settings):
    call_idx = np.argmin(np.abs(df['strike'].values - S * settings['iv_skew_call_pct']))
    put_idx = np.argmin(np.abs(df['strike'].values - S * settings['iv_skew_put_pct']))
    c_iv, p_iv = max(df.iloc[call_idx].get('impliedVolatility_call', 0.001), 0.001), max(df.iloc[put_idx].get('impliedVolatility_put', 0.001), 0.001)
    return c_iv - p_iv, c_iv, p_iv, df.iloc[call_idx]['strike'], df.iloc[put_idx]['strike']

def calculate_zero_gamma(df, S):
    net_gamma_vals = df['net_gamma'].values if 'net_gamma' in df.columns else np.exp(-0.5 * ((df['strike'].values - S) / (S * 0.05))**2) / (S * 0.05 * np.sqrt(2 * np.pi))
    for i in range(1, len(net_gamma_vals)):
        if net_gamma_vals[i-1] * net_gamma_vals[i] < 0: return (df['strike'].values[i-1] + df['strike'].values[i]) / 2, net_gamma_vals
    return S, net_gamma_vals

def calculate_confluence_zones(df, S, max_gamma, max_vanna, settings):
    zones = []
    for _, row in df.iterrows():
        gn = row.get('net_gamma', 0) / max_gamma if max_gamma != 0 else 0
        vn = row.get('net_vanna', 0) / max_vanna if max_vanna != 0 else 0
        if gn > settings['confluence_pct'] and vn > settings['confluence_pct'] and row['strike'] > S: zones.append({'strike': row['strike'], 'type': 'squeeze', 'color': 'limegreen'})
        if gn < -settings['confluence_pct'] and vn < -settings['confluence_pct'] and row['strike'] < S: zones.append({'strike': row['strike'], 'type': 'meltdown', 'color': 'red'})
    return zones

def create_combined_chart(zero_gamma_level, distance_to_zero_gamma, setup_signal, gex_flow, zones, S, expiration_date, settings):
    fig = go.Figure()
    fig.update_xaxes(visible=False, range=[0, 1]); fig.update_yaxes(visible=False, range=[0, 1])
    fig.add_annotation(x=0.5, y=0.99, text=f"<b>📅 تاريخ الانتهاء: {expiration_date}</b>", showarrow=False, font=dict(color="#00d4ff", size=18), xref="paper", yref="paper")
    fig.add_annotation(x=0.5, y=0.945, text="<b>⚙️ الإعدادات المتقدمة</b>", showarrow=False, font=dict(color="#00d4ff", size=14), xref="paper", yref="paper")
    for pos, (l, v) in zip([0.12, 0.31, 0.50, 0.69, 0.88], [("IV Call %", f"{settings['iv_skew_call_pct']:.2f}"), ("IV Put %", f"{settings['iv_skew_put_pct']:.2f}"), ("SMA Period", f"{settings['iv_sma_period']}"), ("IV Skew Dev", f"{settings['iv_deviation_threshold']:.2f}"), ("Confluence %", f"{settings['confluence_pct']:.2f}")]):
        fig.add_annotation(x=pos, y=0.905, text=f"<b>{l}</b>", showarrow=False, font=dict(color="#9aa0a6", size=11), xref="paper", yref="paper"); fig.add_annotation(x=pos, y=0.865, text=f"<b>{v}</b>", showarrow=False, font=dict(color="#00d4ff", size=15), xref="paper", yref="paper")
    fig.add_shape(type="line", x0=0.05, x1=0.95, y0=0.815, y1=0.815, line=dict(color="#333", width=1))
    fig.add_annotation(x=0.5, y=0.78, text="<b>🎯 مؤشرات صفر غاما (Zero-Gamma)</b>", showarrow=False, font=dict(color="#00d4ff", size=20), xref="paper", yref="paper")
    for pos, t, v, c in zip([0.125, 0.375, 0.625, 0.875], ["📍 مستوى صفر غاما", "📏 المسافة من السعر", "📈 الإشارة", "🌊 تدفق غاما"], [f"${zero_gamma_level:.2f}", f"${distance_to_zero_gamma:.2f}", setup_signal, f"{gex_flow:+.0f}"], ["white", "white", "limegreen" if setup_signal == "Bullish Setup" else "crimson", "limegreen" if gex_flow > 0 else "crimson"]):
        fig.add_annotation(x=pos, y=0.70, text=f"<b>{t}</b>", showarrow=False, font=dict(color="white", size=14), xref="paper", yref="paper"); fig.add_annotation(x=pos, y=0.61, text=f"<b>{v}</b>", showarrow=False, font=dict(color=c, size=24), xref="paper", yref="paper")
    fig.add_shape(type="line", x0=0.05, x1=0.95, y0=0.52, y1=0.52, line=dict(color="#444", width=1))
    fig.add_annotation(x=0.5, y=0.46, text="<b>📍 مناطق التقاء غاما وفانا (Confluence Zones)</b>", showarrow=False, font=dict(color="#00d4ff", size=20), xref="paper", yref="paper")
    lines, colors_zones = [], []
    if zones:
        sq = [z for z in zones if z['type'] == 'squeeze']; ml = [z for z in zones if z['type'] == 'meltdown']
        if sq: lines.append(f"💥 مناطق Squeeze (صاعد) عند: {', '.join([f'${z['strike']:.2f}' for z in sq])}"); colors_zones.append("limegreen")
        if ml: lines.append(f"⬇️ مناطق Meltdown (هابط) عند: {', '.join([f'${z['strike']:.2f}' for z in ml])}"); colors_zones.append("crimson")
        for z in zones:
            if z['type'] == 'squeeze' and S <= zero_gamma_level: lines.append(f"⚠️ Squeeze عند ${z['strike']:.2f} غير مفعّل"); colors_zones.append("orange")
            if z['type'] == 'meltdown' and S >= zero_gamma_level: lines.append(f"⚠️ Meltdown عند ${z['strike']:.2f} غير مفعّل"); colors_zones.append("orange")
    if not lines: lines, colors_zones = ["لا توجد مناطق التقاء حالياً."], ["gray"]
    for i, (l, c) in enumerate(zip(lines, colors_zones)):
        if 0.36 - (i * 0.065) < 0.02: break
        fig.add_annotation(x=0.5, y=0.36 - (i * 0.065), text=f"<b>{l}</b>", showarrow=False, font=dict(color=c, size=15), xref="paper", yref="paper")
    fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", height=max(640, 420 + len(lines) * 40), margin=dict(l=10, r=10, t=20, b=20), showlegend=False)
    return fig

def plot_metric_single(df, S, call_col, put_col, title, y_axis, x_range=None, zero_gamma_level=None, zones=None, gex_flow=None):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['strike'], y=df[call_col], marker_color='limegreen', name='Calls'))
    fig.add_trace(go.Bar(x=df['strike'], y=df[put_col], marker_color='crimson', name='Puts'))
    fig.update_layout(barmode='relative')
    if x_range is None:
        min_s, max_s = df['strike'].min(), df['strike'].max()
        if S < min_s: min_s = S - (max_s - min_s) * 0.15
        elif S > max_s: max_s = S + (max_s - min_s) * 0.15
        x_range = (S - max(S - min_s, max_s - S) * 1.2, S + max(S - min_s, max_s - S) * 1.2)
    fig.add_vline(x=S, line_dash="dash", line_color="white", annotation_text=f"S = {S:.1f}", annotation_position="top", annotation_font=dict(color="white", size=12))
    if zero_gamma_level is not None: fig.add_vline(x=zero_gamma_level, line_dash="dash", line_color="white", annotation_text="Zero-Gamma", annotation_position="bottom", annotation_font=dict(color="white", size=10))
    if zones:
        for z in zones: fig.add_vline(x=z['strike'], line_dash="dot", line_color=z['color'], annotation_text=f"{'SQZ' if z['type'] == 'squeeze' else 'MLT'} {z['type'].upper()}", annotation_position="top", annotation_font=dict(color=z['color'], size=10))
    if gex_flow is not None: fig.add_annotation(x=0.95, y=0.95, xref="paper", yref="paper", text=f"GEX Flow: {gex_flow:+.0f}", showarrow=False, font=dict(color="limegreen" if gex_flow > 0 else "crimson", size=14), bgcolor="rgba(0,0,0,0.7)", borderpad=4)
    fig.update_layout(title=METRICS_LABELS.get(title, title), yaxis_title=y_axis, xaxis_title="Strike Price", font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222", hovermode="x unified", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="white")), margin=dict(l=10, r=10, t=40, b=40))
    fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range)
    fig.update_yaxes(gridcolor='gray')
    return fig

def plot_iv_skew(skew_history, sma_history, current_skew, sma_value, deviation, call_strike, put_strike, call_iv, put_iv, call_pct, put_pct, y_range_mode="auto", y_range_manual=None):
    fig = go.Figure()
    all_values = [v for v in skew_history + sma_history if v is not None and not np.isnan(v)]
    if all_values:
        d_min, d_max = min(all_values), max(all_values)
        d_center = (d_min + d_max) / 2
        d_span = max(d_max - d_min, 1e-4)
        padding = max(d_span * 0.3, abs(d_center) * 0.1, 1e-4)
        a_y_min, a_y_max = d_min - padding, d_max + padding
        if d_span < 0.001: a_y_min, a_y_max = d_center - 0.005, d_center + 0.005
    else: a_y_min, a_y_max = -0.1, 0.1
    t = 0.20
    if a_y_min < -t < a_y_max: fig.add_hrect(y0=-t, y1=t, fillcolor="rgba(0,255,0,0.04)", line_width=0, layer="below")
    if a_y_min < t: fig.add_hrect(y0=t, y1=a_y_max, fillcolor="rgba(255,255,0,0.06)", line_width=0, layer="below")
    if a_y_max > -t: fig.add_hrect(y0=a_y_min, y1=-t, fillcolor="rgba(255,255,0,0.06)", line_width=0, layer="below")
    fig.add_hline(y=0, line_dash="solid", line_color="#666", line_width=1)
    fig.add_hline(y=t, line_dash="dot", line_color="orange", opacity=0.5, annotation_text="+0.20", annotation_position="right", annotation_font=dict(color="orange", size=10))
    fig.add_hline(y=-t, line_dash="dot", line_color="orange", opacity=0.5, annotation_text="-0.20", annotation_position="right", annotation_font=dict(color="orange", size=10))
    if skew_history: fig.add_trace(go.Scatter(x=list(range(len(skew_history))), y=skew_history, mode='lines+markers', line=dict(color='cyan', width=2), marker=dict(size=5, color='cyan'), name='IV Skew'))
    if sma_history: fig.add_trace(go.Scatter(x=list(range(len(sma_history))), y=sma_history, mode='lines', line=dict(color='orange', width=2, dash='dash'), name='SMA'))
    c_badge = 'yellow' if abs(deviation) > 0.20 else 'white'
    fig.add_annotation(x=0.5, y=0.97, xref="paper", yref="paper", text=f"Skew: {current_skew:.4f} | SMA: {sma_value:.4f} | Dev: {deviation:.2%}", showarrow=False, font=dict(color=c_badge, size=12), bgcolor="rgba(0,0,0,0.6)", borderpad=4)
    d_pct = deviation * 100; is_ab = abs(deviation) > 0.20
    fig.add_shape(type="line", x0=0.02, x1=0.98, y0=-0.10, y1=-0.10, line=dict(color="#555", width=1), xref="paper", yref="paper")
    for pos, l, v, c in zip([0.125, 0.375, 0.625, 0.875], ["📊 IV Skew الحالي", "📈 المتوسط (SMA 20)", "📉 الانحراف عن المتوسط", "🎯 حالة الانحراف"], [f"{current_skew:.4f}", f"{sma_value:.4f}", f"{d_pct:.2f}%", "⚠️ غير طبيعي" if is_ab else "✅ طبيعي"], ["white", "white", "yellow" if is_ab else "white", "yellow" if is_ab else "limegreen"]):
        fig.add_annotation(x=pos, y=-0.16, text=f"<b>{l}</b>", showarrow=False, font=dict(color="#9aa0a6", size=13), xref="paper", yref="paper"); fig.add_annotation(x=pos, y=-0.23, text=f"<b>{v}</b>", showarrow=False, font=dict(color=c, size=22 if "حالة" in l else 26), xref="paper", yref="paper")
    fig.add_shape(type="line", x0=0.02, x1=0.98, y0=-0.30, y1=-0.30, line=dict(color="#555", width=1), xref="paper", yref="paper")
    for pos, l, v, c in zip([0.083, 0.25, 0.417, 0.583, 0.75, 0.917], ["📍 سعر تنفيذ Call", "📊 نسبة Call %", "🌊 IV Call", "📍 سعر تنفيذ Put", "📊 نسبة Put %", "🌊 IV Put"], [f"${call_strike:.2f}", f"{call_pct:.0%}", f"{call_iv:.4f}", f"${put_strike:.2f}", f"{put_pct:.0%}", f"{put_iv:.4f}"], ["limegreen", "limegreen", "limegreen", "crimson", "crimson", "crimson"]):
        fig.add_annotation(x=pos, y=-0.36, text=f"<b>{l}</b>", showarrow=False, font=dict(color="#9aa0a6", size=11), xref="paper", yref="paper"); fig.add_annotation(x=pos, y=-0.42, text=f"<b>{v}</b>", showarrow=False, font=dict(color=c, size=22), xref="paper", yref="paper")
    if y_range_mode == "auto": f_y_min, f_y_max = a_y_min, a_y_max
    elif y_range_mode == "manual" and y_range_manual is not None: f_y_min, f_y_max = y_range_manual
    else: f_y_min, f_y_max = a_y_min, a_y_max
    fig.update_layout(title="IV Skew (Auto-Scale)", yaxis_title="IV Spread", xaxis_title="Time", font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222", height=700, margin=dict(l=10, r=10, t=40, b=200), showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="white")))
    fig.update_xaxes(gridcolor='gray'); fig.update_yaxes(gridcolor='gray', range=[f_y_min, f_y_max])
    return fig

def plot_ratio_line(df, S, x_col, y_col, title, y_axis, line_color='magenta'):
    fig = go.Figure(go.Scatter(x=df[x_col], y=df[y_col], mode='lines+markers', line=dict(color=line_color, width=2), marker=dict(size=6), name='Gamma / OI Ratio'))
    fig.add_vline(x=S, line_dash="dash", line_color="white", annotation_text=f"S = {S:.1f}", annotation_position="top right", annotation_font=dict(color="white"))
    fig.update_layout(title=title, yaxis_title=y_axis, xaxis_title="Strike Price", font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222", hovermode="x unified", margin=dict(l=10, r=10, t=40, b=40))
    fig.update_xaxes(gridcolor='gray'); fig.update_yaxes(gridcolor='gray')
    return fig

def plot_cumulative_delta(df, S, x_col, y_col, title, y_axis, line_color='deepskyblue'):
    fig = go.Figure(go.Scatter(x=df[x_col], y=df[y_col], mode='lines', fill='tozeroy', line=dict(color=line_color, width=2), name='Net Delta'))
    fig.add_vline(x=S, line_dash="dash", line_color="white", annotation_text=f"S = {S:.1f}", annotation_position="top right", annotation_font=dict(color="white"))
    fig.update_layout(title=title, yaxis_title=y_axis, xaxis_title="Strike Price", font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222", hovermode="x unified", showlegend=True, margin=dict(l=10, r=10, t=40, b=40))
    fig.update_xaxes(gridcolor='gray'); fig.update_yaxes(gridcolor='gray')
    return fig

def single_date_page(symbol):
    st.header("تحليل تاريخ انتهاء واحد")
    st.caption(f"التاريخ: {datetime.datetime.now().strftime('%Y-%m-%d')}")
    current_price, expiration_date, df, T = fetch_options_data(symbol)
    if df is None: return
    S, q = current_price, 0.0
    status, _ = get_market_status()
    st.info(f"📊 البيانات من GitHub Actions — {'🟢 السوق مفتوح' if status == 'open' else '🟡 السوق مغلق'}")

    with st.sidebar:
        st.markdown("## الإعدادات")
        r = st.slider("سعر الفائدة (r)", 0.0, 0.2, 0.05, 0.005)
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("تحديث سريع", width='stretch'): st.cache_data.clear(); st.rerun()
        with col2:
            if st.button("تحديث قسري", width='stretch'): st.cache_data.clear(); st.rerun()
        if current_price is not None:
            st.metric("السعر الحالي", f"${current_price:.2f}", delta="مفتوح" if status == "open" else "مغلق")
            st.markdown(f"**تاريخ الانتهاء:** `{expiration_date}`")
            st.caption(f"آخر تحديث: {datetime.datetime.now().strftime('%I:%M:%S %p')}")
        st.divider()
        min_strike, max_strike = int(df['strike'].min()), int(df['strike'].max())
        strike_range = st.slider("نطاق أسعار التنفيذ", min_value=min_strike, max_value=max_strike, value=(min_strike, max_strike), step=5)

    settings = DEFAULT_SETTINGS.copy()
    df_sorted = df[(df['strike'] >= strike_range[0]) & (df['strike'] <= strike_range[1])].copy().sort_values('strike').reset_index(drop=True)
    if df_sorted.empty: st.warning("لا توجد بيانات."); return

    sigma = np.maximum(df_sorted['weighted_IV'].values, 0.001)
    K = df_sorted['strike'].values; oi_c, oi_p = df_sorted['openInterest_call'].values, df_sorted['openInterest_put'].values
    delta_c, delta_p = delta_call(S, K, T, r, sigma, q), delta_put(S, K, T, r, sigma, q)
    gamma_val, vanna_val, vega_val, vomma_val, zomma_val = gamma(S, K, T, r, sigma, q), vanna(S, K, T, r, sigma, q), vega(S, K, T, r, sigma, q), vomma(S, K, T, r, sigma, q), zomma(S, K, T, r, sigma, q)
    theta_c, theta_p, charm_c, charm_p, speed_val = theta_call(S, K, T, r, sigma, q), theta_put(S, K, T, r, sigma, q), charm_call(S, K, T, r, sigma, q), charm_put(S, K, T, r, sigma, q), speed(S, K, T, r, sigma, q)
    SCALE = 10000
    df_sorted['call_delta'], df_sorted['put_delta'] = oi_c * delta_c, oi_p * delta_p
    df_sorted['call_gamma'], df_sorted['put_gamma'] = oi_c * gamma_val, oi_p * gamma_val * -1
    df_sorted['call_gamma_gold'], df_sorted['put_gamma_gold'] = oi_c * gamma_val * 1.2, oi_p * gamma_val * -1.2
    df_sorted['call_vanna'], df_sorted['put_vanna'] = oi_c * vanna_val, oi_p * vanna_val
    df_sorted['call_vomma'], df_sorted['put_vomma'] = oi_c * vomma_val, oi_p * vomma_val
    df_sorted['call_zomma'], df_sorted['put_zomma'] = oi_c * zomma_val, oi_p * zomma_val * -1
    df_sorted['openInterest_call_display'], df_sorted['openInterest_put_display'] = oi_c, oi_p * -1
    df_sorted['call_vega'], df_sorted['put_vega'] = oi_c * vega_val, oi_p * vega_val
    df_sorted['call_theta'], df_sorted['put_theta'] = oi_c * theta_c, oi_p * theta_p
    df_sorted['call_charm'], df_sorted['put_charm'] = oi_c * charm_c * SCALE, oi_p * charm_p * SCALE
    df_sorted['call_speed'], df_sorted['put_speed'] = oi_c * speed_val * SCALE, oi_p * speed_val * SCALE
    df_sorted['net_gamma'], df_sorted['net_vanna'] = df_sorted['call_gamma'] + df_sorted['put_gamma'], df_sorted['call_vanna'] + df_sorted['put_vanna']
    df_sorted['total_gamma'], df_sorted['total_oi'] = df_sorted['call_gamma'] + df_sorted['put_gamma'], df_sorted['openInterest_call'] + df_sorted['openInterest_put']
    df_sorted['gamma_ratio'] = df_sorted['total_gamma'] / (df_sorted['total_oi'] + 1)

    skew_value, call_iv, put_iv, call_strike, put_strike = calculate_iv_skew(df_sorted, S, settings)
    if 'iv_skew_history' not in st.session_state: st.session_state.iv_skew_history = deque(maxlen=settings['iv_sma_period'] + 10)
    st.session_state.iv_skew_history.append(skew_value)
    skew_history = list(st.session_state.iv_skew_history)
    sma_period = settings['iv_sma_period']
    if len(skew_history) >= sma_period:
        sma_value = np.mean(skew_history[-sma_period:]); sma_history = [np.mean(skew_history[i-sma_period:i]) for i in range(sma_period, len(skew_history) + 1)]
    else: sma_value = np.mean(skew_history) if skew_history else 0; sma_history = []
    deviation = (skew_value - sma_value) / sma_value if sma_value != 0 else 0

    zero_gamma_level, _ = calculate_zero_gamma(df_sorted, S)
    setup_signal = "Bullish Setup" if S > zero_gamma_level else "Bearish Setup"
    max_gamma = max(abs(df_sorted['net_gamma'].max()), abs(df_sorted['net_gamma'].min())) if 'net_gamma' in df_sorted else 1
    max_vanna = max(abs(df_sorted['net_vanna'].max()), abs(df_sorted['net_vanna'].min())) if 'net_vanna' in df_sorted else 1
    zones = calculate_confluence_zones(df_sorted, S, max_gamma, max_vanna, settings)
    current_net_gex = df_sorted['net_gamma'].sum()
    st.session_state.gex_history.add(current_net_gex)
    gex_60min_ago = st.session_state.gex_history.get_60min_ago()
    gex_flow = current_net_gex - gex_60min_ago if gex_60min_ago is not None else 0

    st.divider()
    st.subheader("🔄 مزامنة الأسعار ومحاكي الحركة")
    base_sym = symbol.upper()
    sync_options = {"GLD": ["GLD (الأساسي)", "GC=F (الذهب الآجل)", "XAUUSD (الذهب الفوري)"], "SPY": ["SPY (الأساسي)", "ES=F (S&P 500 آجل)", "^GSPC (مؤشر S&P 500)"], "SPX": ["SPX (الأساسي)", "ES=F (S&P 500 آجل)", "^GSPC (مؤشر S&P 500)"], "QQQ": ["QQQ (الأساسي)", "NQ=F (ناسداك آجل)", "^NDX (مؤشر ناسداك 100)"], "NDX": ["NDX (الأساسي)", "NQ=F (ناسداك آجل)", "^NDX (مؤشر ناسداك 100)"]}
    ticker_map = {"GC=F (الذهب الآجل)": "GC=F", "XAUUSD (الذهب الفوري)": "XAUUSD=X", "ES=F (S&P 500 آجل)": "ES=F", "^GSPC (مؤشر S&P 500)": "^GSPC", "NQ=F (ناسداك آجل)": "NQ=F", "^NDX (مؤشر ناسداك 100)": "^NDX"}
    available_options = sync_options.get(base_sym, sync_options["GLD"])
    col_sync1, col_sync2, col_sync3 = st.columns([2, 1, 1])
    with col_sync1: instrument_choice = st.selectbox(f"اختر الأداة لمزامنة سعر {base_sym}:", available_options, index=0)
    
    reference_price, sync_ratio = S, 1.0
    
    if instrument_choice != available_options[0]:
        ticker_symbol = ticker_map.get(instrument_choice)
        other_price = fetch_other_instrument_price(ticker_symbol) if ticker_symbol else None
        
        if other_price:
            sync_ratio = get_conversion_ratio(S, other_price)
            reference_price = other_price
            with col_sync2:
                st.metric(label=f"سعر {instrument_choice.split(' ')[0]}", value=f"${reference_price:,.2f}")
            with col_sync3:
                st.metric(label="معامل التحويل", value=f"{sync_ratio:.3f}x")
        else:
            st.warning(f"⚠️ تعذر جلب سعر {instrument_choice} تلقائياً من ياهو.")
            manual_mt4_price = st.number_input("أدخل سعر شارت ميتاتريدر الحالي يدوياً (لضبط التحويل):", value=4050.0, step=10.0)
            sync_ratio = get_conversion_ratio(S, manual_mt4_price)
            reference_price = manual_mt4_price
            st.info(f"تم ضبط معامل التحويل يدوياً على: {sync_ratio:.3f}x")
            
        converted_zero_gamma = convert_price(zero_gamma_level, sync_ratio)
        st.success(f"📌 مستوى صفر غاما المحول: **${converted_zero_gamma:,.2f}**")
        
        st.markdown("---")
        st.markdown(f"#### 🎯 محاكي الحركة (ماذا لو تحرك {base_sym}؟)")
        price_offset = st.slider(f"حاكي حركة سعر {base_sym} (بالدولار):", min_value=-20.0, max_value=20.0, value=0.0, step=0.5)
        
        if price_offset != 0:
            simulated_gld = S + price_offset
            simulated_converted = simulated_gld * sync_ratio
            col_sim1, col_sim2 = st.columns(2)
            with col_sim1:
                st.metric(label=f"سعر {base_sym} المحاكي", value=f"${simulated_gld:.2f}", delta=f"{price_offset:+.2f}$")
            with col_sim2:
                st.metric(label=f"السعر المكافئ في {instrument_choice.split(' ')[0]}", value=f"${simulated_converted:.2f}")

    csv_content = generate_mt4_csv(df_sorted, sync_ratio)
    st.download_button(label="📥 تحميل ملف CSV لميتاتريدر (إذا لم يتحدث تلقائياً)", data=csv_content, file_name="mt4_gamma_levels.csv", mime="text/csv")

    st.divider()
    fig_combined = create_combined_chart(zero_gamma_level, S - zero_gamma_level, setup_signal, gex_flow, zones, S, expiration_date, settings)
    st.plotly_chart(fig_combined, width='stretch', key="chart_combined")

    st.divider()
    st.subheader("🤖 محرك التوقع الذكي (AI Engine)")
    net_vanna = df_sorted['net_vanna'].sum(); net_charm = df_sorted['call_charm'].sum() + df_sorted['put_charm'].sum()
    pred_text, pred_color, prob, confidence, reasons = calculate_ai_prediction(S, zero_gamma_level, gex_flow, skew_value, net_vanna, net_charm)
    prob_bearish = 100 - prob
    col_ai1, col_ai2 = st.columns([1, 2])
    with col_ai1:
        st.markdown(f"""
        <div style="background-color: #1E1E1E; padding: 20px; border-radius: 10px; border: 2px solid {pred_color}; text-align: center;">
            <h3 style="color: {pred_color}; margin: 0 0 15px 0;">{pred_text}</h3>
            <div style="display: flex; justify-content: space-around; margin: 10px 0;">
                <div><h2 style="color: limegreen; margin: 0;">{prob:.1f}%</h2><p style="color: #9aa0a6; margin: 0; font-size: 14px;">صعود</p></div>
                <div><h2 style="color: crimson; margin: 0;">{prob_bearish:.1f}%</h2><p style="color: #9aa0a6; margin: 0; font-size: 14px;">هبوط</p></div>
            </div>
            <p style="color: {pred_color}; font-weight: bold; margin-top: 15px;">مستوى الثقة: {confidence:.0f}%</p>
        </div>
        """, unsafe_allow_html=True)
    with col_ai2:
        st.markdown("### 🧠 الأسباب الكمية وراء التوقع:")
        for reason in reasons: st.markdown(f"- {reason}")
            
    st.divider()
    st.subheader("📉 مؤشر انحراف التقلب (IV Skew)")
    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl2: auto_scale = st.checkbox("Auto-Scale تلقائي", value=True, key="iv_skew_auto")
    if not auto_scale:
        with st.expander("⚙️ ضبط نطاق Y يدوياً", expanded=True):
            col_a, col_b = st.columns(2)
            with col_a: y_min_manual = st.number_input("الحد الأدنى", value=-0.05, step=0.01, key="iv_y_min")
            with col_b: y_max_manual = st.number_input("الحد الأعلى", value=0.10, step=0.01, key="iv_y_max")
        y_range_manual = (y_min_manual, y_max_manual)
    else: y_range_manual = None
    fig_skew = plot_iv_skew(skew_history, sma_history, skew_value, sma_value, deviation, call_strike, put_strike, call_iv, put_iv, settings['iv_skew_call_pct'], settings['iv_skew_put_pct'], "auto" if auto_scale else "manual", y_range_manual)
    st.plotly_chart(fig_skew, width='stretch', key="chart_iv_skew")

    metrics = [('openInterest_call_display', 'openInterest_put_display', 'Open Interest', 'Contracts'), ('call_gamma', 'put_gamma', 'Gamma Exposure', 'Gamma Exposure'), ('call_gamma_gold', 'put_gamma_gold', 'Gamma Gold', 'Gamma Exposure'), ('call_delta', 'put_delta', 'Delta Exposure', 'Delta Exposure'), ('call_vanna', 'put_vanna', 'Vanna Exposure', 'Vanna Exposure'), ('call_vega', 'put_vega', 'Vega Exposure', 'Vega Exposure'), ('call_theta', 'put_theta', 'Theta Exposure', 'Theta Exposure'), ('call_charm', 'put_charm', 'Charm Exposure (x10k)', 'Charm (x10k)'), ('call_speed', 'put_speed', 'Speed Exposure (x10k)', 'Speed (x10k)'), ('call_vomma', 'put_vomma', 'Vomma Exposure', 'Vomma'), ('call_zomma', 'put_zomma', 'Zomma Exposure', 'Zomma'), ('impliedVolatility_call', 'impliedVolatility_put', 'Implied Volatility', 'IV')]
    any_frozen = False
    for call_col, put_col, title, yaxis in metrics:
        x_range = st.session_state.get(f"xrange_{title}", None)
        if title == "Gamma Gold": z_gam, z_lst, g_fl = zero_gamma_level, zones, gex_flow
        else: z_gam, z_lst, g_fl = None, None, None
        fig = plot_metric_single(df_sorted, S, call_col, put_col, title, yaxis, x_range=x_range, zero_gamma_level=z_gam, zones=z_lst, gex_flow=g_fl)
        col_plot, col_freeze = st.columns([0.96, 0.04])
        with col_plot: st.plotly_chart(fig, width='stretch', key=f"chart_{title}")
        with col_freeze:
            st.write("")
            frozen = st.checkbox("قفل", key=f"freeze_{title}", value=st.session_state.get(f"freeze_{title}", False))
            if frozen: any_frozen = True

    fig_ratio = plot_ratio_line(df_sorted, S, 'strike', 'gamma_ratio', 'Gamma / Open Interest Ratio', 'Gamma per Contract', 'magenta')
    st.plotly_chart(fig_ratio, width='stretch')
    df_sorted['net_delta'] = df_sorted['call_delta'] - df_sorted['put_delta']
    df_sorted['cumulative_delta'] = df_sorted['net_delta'].cumsum()
    if "show_cum_delta" not in st.session_state: st.session_state.show_cum_delta = False
    col_btn, col_title = st.columns([0.15, 0.85])
    with col_btn:
        label = "إخفاء" if st.session_state.show_cum_delta else "إظهار"
        if st.button(label, key="toggle_cum_delta"): st.session_state.show_cum_delta = not st.session_state.show_cum_delta; st.rerun()
    with col_title: st.write("### 📊 الدلتا التراكمي (Cumulative Delta Exposure)")
    if st.session_state.show_cum_delta:
        fig_cum = plot_cumulative_delta(df_sorted, S, 'strike', 'cumulative_delta', 'Cumulative Delta Exposure', 'Cumulative Net Delta', 'deepskyblue')
        st.plotly_chart(fig_cum, width='stretch')
    else: st.caption("🔒 المؤشر مخفي.")

    st.divider()
    st.subheader("📋 قائمة الخيارات - صافي العقود")
    df_inventory = df_sorted.copy(); df_inventory['Net_Contracts'] = df_inventory['openInterest_call'] - df_inventory['openInterest_put']
    fig_inv = go.Figure()
    bought, sold = df_inventory[df_inventory['Net_Contracts'] > 0], df_inventory[df_inventory['Net_Contracts'] < 0]
    if not bought.empty: fig_inv.add_trace(go.Bar(x=bought['strike'], y=bought['Net_Contracts'], marker_color='limegreen', name='BOUGHT', text=bought['Net_Contracts'].apply(lambda x: f'{x:.0f}'), textposition='outside'))
    if not sold.empty: fig_inv.add_trace(go.Bar(x=sold['strike'], y=sold['Net_Contracts'], marker_color='crimson', name='SOLD', text=sold['Net_Contracts'].apply(lambda x: f'{x:.0f}'), textposition='outside'))
    fig_inv.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5); fig_inv.add_vline(x=S, line_dash="dash", line_color="yellow", annotation_text=f"S = {S:.2f}", annotation_position="top", annotation_font=dict(color="yellow", size=12))
    min_s, max_s = df_inventory['strike'].min(), df_inventory['strike'].max()
    if S < min_s: min_s = S - (max_s - min_s) * 0.15
    elif S > max_s: max_s = S + (max_s - min_s) * 0.15
    x_range_inv = (S - max(S - min_s, max_s - S) * 1.2, S + max(S - min_s, max_s - S) * 1.2)
    fig_inv.update_layout(title=dict(text=f"Net Options Positions - {symbol} - {expiration_date}", x=0.02, xanchor='left', font=dict(color="white", size=16)), xaxis_title="", yaxis_title="Net Contracts", font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222", hovermode="x unified", barmode='relative', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="white")), height=750, margin=dict(l=60, r=20, t=50, b=170))
    fig_inv.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True, thickness=0.08), range=x_range_inv, showticklabels=True); fig_inv.update_yaxes(gridcolor='gray', zeroline=True, zerolinecolor='white')
    fig_inv.add_shape(type="line", x0=0.02, x1=0.98, y0=-0.23, y1=-0.23, line=dict(color="#555", width=1), xref="paper", yref="paper")
    total_oi_calls, total_oi_puts = df_inventory['openInterest_call'].sum(), df_inventory['openInterest_put'].sum(); total_net = total_oi_calls - total_oi_puts
    for pos, l, v, c in zip([0.125, 0.375, 0.625, 0.875], ["إجمالي OI (Calls)", "إجمالي OI (Puts)", "صافي العقود الكلي", "السعر الحالي"], [f"{total_oi_calls:,.0f}", f"{total_oi_puts:,.0f}", f"{total_net:+,.0f}", f"${S:.2f}"], ["white", "white", "limegreen" if total_net > 0 else "crimson", "white"]):
        fig_inv.add_annotation(x=pos, y=-0.28, text=f"<b>{l}</b>", showarrow=False, font=dict(color="#9aa0a6", size=13), xref="paper", yref="paper"); fig_inv.add_annotation(x=pos, y=-0.36, text=f"<b>{v}</b>", showarrow=False, font=dict(color=c, size=26), xref="paper", yref="paper")
    st.plotly_chart(fig_inv, width='stretch', key="chart_inventory")

    st.divider()
    st.download_button(label="تحميل جميع البيانات CSV", data=df_sorted.to_csv(index=False).encode('utf-8'), file_name=f'{symbol}_options_{expiration_date}.csv', mime='text/csv', key='download_csv_single')
    if should_autorefresh(): st_autorefresh(interval=15 * 1000, key="auto_normal")
    else: st.caption("التحديث التلقائي متوقف.")

def multi_date_page(symbol):
    st.header("مقارنة تواريخ انتهاء متعددة")
    with st.sidebar:
        r = st.slider("سعر الفائدة (r)", 0.0, 0.2, 0.05, 0.005, key="r_multi")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("تحديث سريع", key="refresh_multi_quick", width='stretch'): st.cache_data.clear(); st.rerun()
        with col2:
            if st.button("تحديث قسري", key="refresh_multi_force", width='stretch'): st.cache_data.clear(); st.rerun()
        st.caption(f"{datetime.datetime.now().strftime('%I:%M:%S %p')}")
    try: all_exps = get_available_expirations(symbol); current_price = get_current_price(symbol)
    except: all_exps = []; current_price = 0
    if not all_exps: st.error("لا توجد تواريخ انتهاء متاحة."); return
    selected_exps = st.multiselect("اختر تواريخ الانتهاء (حد أقصى 5)", all_exps, default=all_exps[:2] if len(all_exps) >= 2 else all_exps, max_selections=5)
    if not selected_exps: st.warning("اختر تاريخاً واحداً على الأقل."); return
    dfs = {}; S = current_price if current_price else 0; q = 0.0; SCALE = 10000
    for exp in selected_exps:
        curr_price, exp_date, df, T = fetch_options_data(symbol, exp)
        if df is None: continue
        df = df.sort_values('strike'); K = df['strike'].values; sigma = np.maximum(df['weighted_IV'].values, 0.001); oi_c, oi_p = df['openInterest_call'].values, df['openInterest_put'].values
        dfs[exp] = {'strike': K, 'total_oi': oi_c + oi_p, 'total_delta': oi_c * delta_call(S, K, T, r, sigma, q) + oi_p * delta_put(S, K, T, r, sigma, q), 'total_gamma': (oi_c - oi_p) * gamma(S, K, T, r, sigma, q), 'total_vanna': (oi_c + oi_p) * vanna(S, K, T, r, sigma, q), 'total_vega': (oi_c + oi_p) * vega(S, K, T, r, sigma, q), 'total_theta': oi_c * theta_call(S, K, T, r, sigma, q) + oi_p * theta_put(S, K, T, r, sigma, q), 'total_charm': (oi_c * charm_call(S, K, T, r, sigma, q) + oi_p * charm_put(S, K, T, r, sigma, q)) * SCALE, 'total_speed': (oi_c + oi_p) * speed(S, K, T, r, sigma, q) * SCALE, 'total_iv': df['weighted_IV']}
    compare_metrics = [("total_oi", "Total Open Interest"), ("total_gamma", "Total Gamma Exposure"), ("total_delta", "Total Delta Exposure"), ("total_vanna", "Total Vanna Exposure"), ("total_vega", "Total Vega Exposure"), ("total_theta", "Total Theta Exposure"), ("total_charm", "Total Charm Exposure (x10k)"), ("total_speed", "Total Speed Exposure (x10k)"), ("total_iv", "Implied Volatility (avg)")]
    for key, title in compare_metrics:
        fig = go.Figure(); all_strikes = []
        for exp in selected_exps:
            if exp in dfs: all_strikes.extend(dfs[exp]['strike']); fig.add_trace(go.Scatter(x=dfs[exp]['strike'], y=dfs[exp][key], mode='lines', name=exp))
        if all_strikes and S:
            min_s, max_s = min(all_strikes), max(all_strikes)
            if S < min_s: min_s = S - (max_s - min_s) * 0.15
            elif S > max_s: max_s = S + (max_s - min_s) * 0.15
            x_range = (S - max(S - min_s, max_s - S) * 1.2, S + max(S - min_s, max_s - S) * 1.2)
        else: x_range = None
        if S: fig.add_vline(x=S, line_dash="dash", line_color="white", annotation_text=f"S = {S:.1f}", annotation_position="top", annotation_font=dict(color="white", size=12))
        fig.update_layout(title=METRICS_LABELS.get(title, title), xaxis_title="Strike Price", yaxis_title="Value", font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222", showlegend=True, margin=dict(l=10, r=10, t=40, b=40))
        fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range); fig.update_yaxes(gridcolor='gray')
        st.plotly_chart(fig, width='stretch')

def main():
    if "show_visitors" not in st.session_state: st.session_state.show_visitors = False
    if "logged_in" not in st.session_state or not st.session_state.logged_in: login_page(); return
    with st.sidebar:
        st.divider()
        if st.button("تسجيل الخروج", width='stretch'): st.session_state.logged_in = False; st.session_state.username = ""; st.rerun()
    col_title, col_selector = st.columns([2, 1])
    with col_title: st.title("Quantitative Options Radar"); st.caption(f"مرحباً، {st.session_state.username}")
    with col_selector: symbol = st.selectbox("اختر الرمز", ["GLD", "SPY", "SPX", "QQQ", "NDX"], index=0); st.caption(f"تحليل: {symbol}")
    metadata = get_options_metadata()
    if metadata["last_updated"] != "Unknown":
        try:
            last_update = datetime.datetime.fromisoformat(metadata["last_updated"]); time_diff = datetime.datetime.now() - last_update; minutes_ago = int(time_diff.total_seconds() / 60)
            if minutes_ago < 60: st.info(f"آخر تحديث للبيانات: قبل {minutes_ago} دقيقة ({last_update.strftime('%H:%M')})")
            else: hours_ago = minutes_ago // 60; st.warning(f"آخر تحديث للبيانات: قبل {hours_ago} ساعة ({last_update.strftime('%H:%M')})")
        except: st.info(f"آخر تحديث: {metadata['last_updated']}")
    st.divider()
    page = st.sidebar.radio("اختر الصفحة", ["تحليل تاريخ انتهاء واحد", "مقارنة تواريخ متعددة"])
    if page == "تحليل تاريخ انتهاء واحد": single_date_page(symbol)
    else: multi_date_page(symbol)
    track_visitors(st.session_state.username)
    if st.session_state.username == "admin":
        st.divider(); col_btn, col_title_bloc = st.columns([0.2, 0.8])
        with col_btn:
            label = "إخفاء" if st.session_state.show_visitors else "إظهار"
            if st.button(label, width='stretch'): st.session_state.show_visitors = not st.session_state.show_visitors; st.rerun()
        with col_title_bloc: st.subheader("👥 إحصائيات الزوار (آخر 24 ساعة)")
        if st.session_state.show_visitors: display_visitor_widget()
        else: st.caption("🔒 الجدول مخفي.")

if __name__ == "__main__":
    main()
