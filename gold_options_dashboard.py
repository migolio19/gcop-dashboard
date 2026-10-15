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
DATA_FILE = "options_data.json"
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


def get_visitor_ip_and_country():
    try:
        ip = urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')
        url = f'http://ip-api.com/json/{ip}?fields=status,country,countryCode'
        response = urllib.request.urlopen(url, timeout=5).read().decode('utf8')
        data = json.loads(response)
        if data.get('status') == 'success':
            return ip, data.get('countryCode', 'UN')
        return ip, 'UN'
    except Exception:
        return '127.0.0.1', 'Local'


def track_visitors(username=None):
    now = time.time()
    ip, country = get_visitor_ip_and_country()
    visitor_id = hashlib.sha256(ip.encode()).hexdigest()
    
    if os.path.exists(VISITOR_FILE):
        with open(VISITOR_FILE, 'r') as f:
            try:
                logs = json.load(f)
            except:
                logs = []
    else:
        logs = []
    
    cutoff = now - (24 * 60 * 60)
    filtered_logs = [log for log in logs if log['timestamp'] > cutoff]
    
    existing = False
    for log in filtered_logs:
        if log['id'] == visitor_id:
            log['timestamp'] = now
            log['country'] = country
            log['username'] = username if username else log.get('username', 'visitor')
            existing = True
            break
    
    if not existing:
        filtered_logs.append({
            'id': visitor_id,
            'country': country,
            'username': username if username else 'visitor',
            'timestamp': now
        })
    
    with open(VISITOR_FILE, 'w') as f:
        json.dump(filtered_logs, f, indent=2)
    
    return filtered_logs


def display_visitor_widget():
    logs = track_visitors()
    total_visitors = len(logs)
    
    if total_visitors == 0:
        st.info("لا يوجد زوار في الـ 24 ساعة الماضية.")
        return
    
    data = []
    for log in logs:
        dt = datetime.datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %I:%M %p')
        data.append({
            'المستخدم': log.get('username', 'visitor'),
            'الدولة': log['country'],
            'آخر ظهور': dt
        })
    
    df_visitors = pd.DataFrame(data)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("زوار فريدون (24 ساعة)", total_visitors)
    with col2:
        st.dataframe(df_visitors, use_container_width=True, hide_index=True,
                     height=min(200, 35 + 35 * total_visitors))


def login_page():
    st.markdown("""
        <style>
            .stTextInput { text-align: center; }
            .stTextInput > div { display: flex; justify-content: center; }
            .stTextInput input { text-align: center; max-width: 300px; margin: 0 auto; }
            .login-title { text-align: center; margin-bottom: 30px; font-size: 28px; font-weight: bold; color: #00d4ff; }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-title">رادار عادل للخيارات الكمية</div>', unsafe_allow_html=True)
        
        with st.form(key="login_form", clear_on_submit=False):
            username = st.text_input("اسم المستخدم", placeholder="ادخل اسم المستخدم", key="login_username")
            password = st.text_input("كلمة المرور", placeholder="ادخل كلمة المرور", type="password", key="login_password")
            
            login_btn = st.form_submit_button("دخول", use_container_width=True)
            
            if login_btn:
                if username in CREDENTIALS and CREDENTIALS[username] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success(f"مرحباً، {username}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("اسم المستخدم أو كلمة المرور غير صحيحة")


def get_market_status():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    now_ny = now_utc.astimezone(ny_tz)
    
    if now_ny.weekday() >= 5:
        return "closed", now_ny
    
    current_time = now_ny.time()
    open_time = datetime.time(9, 30)
    close_time = datetime.time(16, 0)
    
    if open_time <= current_time <= close_time:
        return "open", now_ny
    else:
        return "closed", now_ny


def should_autorefresh():
    status, now_ny = get_market_status()
    if status == "closed":
        return False
    return True


def d1(S, K, T, r, sigma, q=0.0):
    return (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))


def delta_call(S, K, T, r, sigma, q=0.0):
    return np.exp(-q * T) * norm.cdf(d1(S, K, T, r, sigma, q))


def delta_put(S, K, T, r, sigma, q=0.0):
    return np.exp(-q * T) * (norm.cdf(d1(S, K, T, r, sigma, q)) - 1)


def gamma(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    return np.exp(-q * T) * norm.pdf(d1_val) / (S * sigma * np.sqrt(T))


def vanna(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d1_val - sigma * np.sqrt(T)
    return -np.exp(-q * T) * norm.pdf(d1_val) * d2_val / sigma


def vega(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    return S * np.exp(-q * T) * norm.pdf(d1_val) * np.sqrt(T)


def theta_call(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d1_val - sigma * np.sqrt(T)
    term1 = -(S * np.exp(-q * T) * norm.pdf(d1_val) * sigma) / (2 * np.sqrt(T))
    term2 = -r * K * np.exp(-r * T) * norm.cdf(d2_val)
    term3 = q * S * np.exp(-q * T) * norm.cdf(d1_val)
    return term1 + term2 + term3


def theta_put(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d1_val - sigma * np.sqrt(T)
    term1 = -(S * np.exp(-q * T) * norm.pdf(d1_val) * sigma) / (2 * np.sqrt(T))
    term2 = r * K * np.exp(-r * T) * norm.cdf(-d2_val)
    term3 = -q * S * np.exp(-q * T) * norm.cdf(-d1_val)
    return term1 + term2 + term3


def charm_call(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    d2_val = d1_val - sigma * np.sqrt(T)
    nd1 = norm.pdf(d1_val)
    Nd1 = norm.cdf(d1_val)
    term1 = -np.exp(-q * T) * nd1 * (2 * (r - q) * T - d2_val * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
    term2 = q * np.exp(-q * T) * Nd1
    return term1 + term2


def charm_put(S, K, T, r, sigma, q=0.0):
    return charm_call(S, K, T, r, sigma, q) - q * np.exp(-q * T)


def speed(S, K, T, r, sigma, q=0.0):
    g = gamma(S, K, T, r, sigma, q)
    d1_val = d1(S, K, T, r, sigma, q)
    return -g * (d1_val / (sigma * np.sqrt(T)) + 1) / S


class GEXHistory:
    def __init__(self, max_minutes=60):
        self.max_minutes = max_minutes
        self.history = deque(maxlen=max_minutes)
        self.last_timestamp = None
    
    def add(self, net_gex, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now()
        self.history.append((timestamp, net_gex))
        self.last_timestamp = timestamp
    
    def get_60min_ago(self):
        if len(self.history) < 2:
            return None
        now = datetime.datetime.now()
        target_time = now - datetime.timedelta(minutes=60)
        for ts, val in self.history:
            if ts <= target_time:
                return val
        return self.history[0][1] if self.history else None
    
    def get_current(self):
        return self.history[-1][1] if self.history else None


if 'gex_history' not in st.session_state:
    st.session_state.gex_history = GEXHistory(max_minutes=120)


def calculate_iv_skew(df, S, settings):
    call_pct = settings.get('iv_skew_call_pct', 1.15)
    put_pct = settings.get('iv_skew_put_pct', 0.85)
    call_target = S * call_pct
    put_target = S * put_pct
    strikes = df['strike'].values
    call_idx = np.argmin(np.abs(strikes - call_target))
    put_idx = np.argmin(np.abs(strikes - put_target))
    call_iv = max(df.iloc[call_idx].get('impliedVolatility_call', 0.001), 0.001)
    put_iv = max(df.iloc[put_idx].get('impliedVolatility_put', 0.001), 0.001)
    skew = call_iv - put_iv
    return skew, call_iv, put_iv, df.iloc[call_idx]['strike'], df.iloc[put_idx]['strike']


def calculate_zero_gamma(df, S):
    if 'net_gamma' in df.columns:
        net_gamma_vals = df['net_gamma'].values
    else:
        strikes = df['strike'].values
        net_gamma_vals = []
        for i, strike in enumerate(strikes):
            gamma_est = np.exp(-0.5 * ((strike - S) / (S * 0.05))**2) / (S * 0.05 * np.sqrt(2 * np.pi))
            net_gamma_vals.append(gamma_est)
    strikes = df['strike'].values
    for i in range(1, len(net_gamma_vals)):
        if net_gamma_vals[i-1] * net_gamma_vals[i] < 0:
            zero_level = (strikes[i-1] + strikes[i]) / 2
            return zero_level, net_gamma_vals
    return S, net_gamma_vals


def calculate_confluence_zones(df, S, max_gamma, max_vanna, settings):
    threshold = settings.get('confluence_pct', 0.30)
    zones = []
    for idx, row in df.iterrows():
        strike = row['strike']
        gamma_val = row.get('net_gamma', 0)
        vanna_val = row.get('net_vanna', 0) if 'net_vanna' in row else row.get('call_vanna', 0) + row.get('put_vanna', 0)
        gamma_norm = gamma_val / max_gamma if max_gamma != 0 else 0
        vanna_norm = vanna_val / max_vanna if max_vanna != 0 else 0
        if gamma_norm > threshold and vanna_norm > threshold and strike > S:
            zones.append({'strike': strike, 'type': 'squeeze', 'color': 'limegreen'})
        if gamma_norm < -threshold and vanna_norm < -threshold and strike < S:
            zones.append({'strike': strike, 'type': 'meltdown', 'color': 'red'})
    return zones


def create_combined_chart(zero_gamma_level, distance_to_zero_gamma, setup_signal,
                          gex_flow, zones, S, expiration_date, settings):
    fig = go.Figure()
    fig.update_xaxes(visible=False, range=[0, 1])
    fig.update_yaxes(visible=False, range=[0, 1])
    
    fig.add_annotation(x=0.5, y=0.99, text=f"<b>📅 تاريخ الانتهاء: {expiration_date}</b>",
                       showarrow=False, font=dict(color="#00d4ff", size=18),
                       xref="paper", yref="paper")
    
    fig.add_annotation(x=0.5, y=0.945, text="<b>⚙️ الإعدادات المتقدمة</b>",
                       showarrow=False, font=dict(color="#00d4ff", size=14),
                       xref="paper", yref="paper")
    
    settings_items = [
        ("IV Call %", f"{settings['iv_skew_call_pct']:.2f}"),
        ("IV Put %", f"{settings['iv_skew_put_pct']:.2f}"),
        ("SMA Period", f"{settings['iv_sma_period']}"),
        ("IV Skew Dev", f"{settings['iv_deviation_threshold']:.2f}"),
        ("Confluence %", f"{settings['confluence_pct']:.2f}"),
    ]
    positions_set = [0.12, 0.31, 0.50, 0.69, 0.88]
    for pos, (label, value) in zip(positions_set, settings_items):
        fig.add_annotation(x=pos, y=0.905, text=f"<b>{label}</b>", showarrow=False,
                           font=dict(color="#9aa0a6", size=11), xref="paper", yref="paper")
        fig.add_annotation(x=pos, y=0.865, text=f"<b>{value}</b>", showarrow=False,
                           font=dict(color="#00d4ff", size=15), xref="paper", yref="paper")
    
    fig.add_shape(type="line", x0=0.05, x1=0.95, y0=0.815, y1=0.815,
                  line=dict(color="#333", width=1))
    
    fig.add_annotation(x=0.5, y=0.78, text="<b>🎯 مؤشرات صفر غاما (Zero-Gamma)</b>",
                       showarrow=False, font=dict(color="#00d4ff", size=20),
                       xref="paper", yref="paper")
    
    positions = [0.125, 0.375, 0.625, 0.875]
    titles = ["📍 مستوى صفر غاما", "📏 المسافة من السعر", "📈 الإشارة", "🌊 تدفق غاما"]
    values = [f"${zero_gamma_level:.2f}", f"${distance_to_zero_gamma:.2f}", setup_signal, f"{gex_flow:+.0f}"]
    signal_color = "limegreen" if setup_signal == "Bullish Setup" else "crimson"
    colors = ["white", "white", signal_color, "limegreen" if gex_flow > 0 else "crimson"]
    for pos, title, value, color in zip(positions, titles, values, colors):
        fig.add_annotation(x=pos, y=0.70, text=f"<b>{title}</b>", showarrow=False,
                           font=dict(color="white", size=14), xref="paper", yref="paper")
        fig.add_annotation(x=pos, y=0.61, text=f"<b>{value}</b>", showarrow=False,
                           font=dict(color=color, size=24), xref="paper", yref="paper")
    
    fig.add_shape(type="line", x0=0.05, x1=0.95, y0=0.52, y1=0.52,
                  line=dict(color="#444", width=1))
    
    fig.add_annotation(x=0.5, y=0.46, text="<b>📍 مناطق التقاء غاما وفانا (Confluence Zones)</b>",
                       showarrow=False, font=dict(color="#00d4ff", size=20),
                       xref="paper", yref="paper")
    
    lines = []
    colors_zones = []
    if zones:
        squeeze_zones = [z for z in zones if z['type'] == 'squeeze']
        meltdown_zones = [z for z in zones if z['type'] == 'meltdown']
        if squeeze_zones:
            squeeze_str = ', '.join([f"${z['strike']:.2f}" for z in squeeze_zones])
            lines.append(f"💥 مناطق Squeeze (صاعد) عند: {squeeze_str}")
            colors_zones.append("limegreen")
        if meltdown_zones:
            meltdown_str = ', '.join([f"${z['strike']:.2f}" for z in meltdown_zones])
            lines.append(f"⬇️ مناطق Meltdown (هابط) عند: {meltdown_str}")
            colors_zones.append("crimson")
        for zone in zones:
            if zone['type'] == 'squeeze' and S <= zero_gamma_level:
                lines.append(f"⚠️ Squeeze عند ${zone['strike']:.2f} غير مفعّل")
                colors_zones.append("orange")
            if zone['type'] == 'meltdown' and S >= zero_gamma_level:
                lines.append(f"⚠️ Meltdown عند ${zone['strike']:.2f} غير مفعّل")
                colors_zones.append("orange")
    if not lines:
        lines = ["لا توجد مناطق التقاء حالياً."]
        colors_zones = ["gray"]
    
    start_y = 0.36
    step = 0.065
    for i, (line, color) in enumerate(zip(lines, colors_zones)):
        y_pos = start_y - (i * step)
        if y_pos < 0.02:
            break
        fig.add_annotation(x=0.5, y=y_pos, text=f"<b>{line}</b>", showarrow=False,
                           font=dict(color=color, size=15), xref="paper", yref="paper")
    
    height = max(640, 420 + len(lines) * 40)
    fig.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                      height=height, margin=dict(l=10, r=10, t=20, b=20), showlegend=False)
    return fig


def plot_metric_single(df, S, call_col, put_col, title, y_axis, x_range=None,
                       zero_gamma_level=None, zones=None, gex_flow=None):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['strike'], y=df[call_col], marker_color='limegreen', name='Calls'))
    fig.add_trace(go.Bar(x=df['strike'], y=df[put_col], marker_color='crimson', name='Puts'))
    fig.update_layout(barmode='relative')
    
    if x_range is None:
        min_s = df['strike'].min()
        max_s = df['strike'].max()
        if S < min_s:
            min_s = S - (max_s - min_s) * 0.15
        elif S > max_s:
            max_s = S + (max_s - min_s) * 0.15
        center = S
        half_range = max(center - min_s, max_s - center) * 1.2
        x_range = (center - half_range, center + half_range)
    
    fig.add_vline(x=S, line_dash="dash", line_color="white",
                  annotation_text=f"S = {S:.1f}", annotation_position="top",
                  annotation_font=dict(color="white", size=12))
    
    if zero_gamma_level is not None:
        fig.add_vline(x=zero_gamma_level, line_dash="dash", line_color="white",
                      annotation_text="Zero-Gamma", annotation_position="bottom",
                      annotation_font=dict(color="white", size=10))
    
    if zones:
        for zone in zones:
            marker = 'SQZ' if zone['type'] == 'squeeze' else 'MLT'
            fig.add_vline(x=zone['strike'], line_dash="dot", line_color=zone['color'],
                          annotation_text=f"{marker} {zone['type'].upper()}",
                          annotation_position="top",
                          annotation_font=dict(color=zone['color'], size=10))
    
    if gex_flow is not None:
        fig.add_annotation(x=0.95, y=0.95, xref="paper", yref="paper",
                           text=f"GEX Flow: {gex_flow:+.0f}", showarrow=False,
                           font=dict(color="limegreen" if gex_flow > 0 else "crimson", size=14),
                           bgcolor="rgba(0,0,0,0.7)", borderpad=4)
    
    display_title = METRICS_LABELS.get(title, title)
    fig.update_layout(title=display_title, yaxis_title=y_axis, xaxis_title="Strike Price",
                      font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                      hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1, font=dict(color="white")),
                      margin=dict(l=10, r=10, t=40, b=40))
    fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range)
    fig.update_yaxes(gridcolor='gray')
    return fig


def plot_iv_skew(skew_history, sma_history, current_skew, sma_value, deviation,
                 call_strike, put_strike, call_iv, put_iv, call_pct, put_pct,
                 y_range_mode="auto", y_range_manual=None):
    fig = go.Figure()
    all_values = []
    if skew_history:
        all_values.extend([v for v in skew_history if v is not None and not np.isnan(v)])
    if sma_history:
        all_values.extend([v for v in sma_history if v is not None and not np.isnan(v)])
    
    if all_values:
        data_min = min(all_values)
        data_max = max(all_values)
        data_center = (data_min + data_max) / 2
        data_span = max(data_max - data_min, 1e-4)
        padding = max(data_span * 0.3, abs(data_center) * 0.1, 1e-4)
        auto_y_min = data_min - padding
        auto_y_max = data_max + padding
        if data_span < 0.001:
            auto_y_min = data_center - 0.005
            auto_y_max = data_center + 0.005
    else:
        auto_y_min, auto_y_max = -0.1, 0.1
    
    threshold = 0.20
    if auto_y_min < -threshold < auto_y_max:
        fig.add_hrect(y0=-threshold, y1=threshold, fillcolor="rgba(0,255,0,0.04)",
                      line_width=0, layer="below")
    if auto_y_min < threshold:
        fig.add_hrect(y0=threshold, y1=auto_y_max, fillcolor="rgba(255,255,0,0.06)",
                      line_width=0, layer="below")
    if auto_y_max > -threshold:
        fig.add_hrect(y0=auto_y_min, y1=-threshold, fillcolor="rgba(255,255,0,0.06)",
                      line_width=0, layer="below")
    
    fig.add_hline(y=0, line_dash="solid", line_color="#666", line_width=1)
    fig.add_hline(y=threshold, line_dash="dot", line_color="orange", opacity=0.5,
                  annotation_text="+0.20", annotation_position="right",
                  annotation_font=dict(color="orange", size=10))
    fig.add_hline(y=-threshold, line_dash="dot", line_color="orange", opacity=0.5,
                  annotation_text="-0.20", annotation_position="right",
                  annotation_font=dict(color="orange", size=10))
    
    if skew_history:
        fig.add_trace(go.Scatter(x=list(range(len(skew_history))), y=skew_history,
                                 mode='lines+markers', line=dict(color='cyan', width=2),
                                 marker=dict(size=5, color='cyan'), name='IV Skew'))
    if sma_history:
        fig.add_trace(go.Scatter(x=list(range(len(sma_history))), y=sma_history,
                                 mode='lines', line=dict(color='orange', width=2, dash='dash'), name='SMA'))
    
    color_badge = 'yellow' if abs(deviation) > 0.20 else 'white'
    fig.add_annotation(x=0.5, y=0.97, xref="paper", yref="paper",
                       text=f"Skew: {current_skew:.4f} | SMA: {sma_value:.4f} | Dev: {deviation:.2%}",
                       showarrow=False, font=dict(color=color_badge, size=12),
                       bgcolor="rgba(0,0,0,0.6)", borderpad=4)
    
    deviation_pct = deviation * 100
    is_abnormal = abs(deviation) > 0.20
    
    fig.add_shape(type="line", x0=0.02, x1=0.98, y0=-0.10, y1=-0.10,
                  line=dict(color="#555", width=1), xref="paper", yref="paper")
    
    row1_positions = [0.125, 0.375, 0.625, 0.875]
    row1_labels = ["📊 IV Skew الحالي", "📈 المتوسط (SMA 20)", "📉 الانحراف عن المتوسط", "🎯 حالة الانحراف"]
    row1_values = [f"{current_skew:.4f}", f"{sma_value:.4f}", f"{deviation_pct:.2f}%",
                   "⚠️ غير طبيعي" if is_abnormal else "✅ طبيعي"]
    dev_color = "yellow" if is_abnormal else "white"
    state_color = "yellow" if is_abnormal else "limegreen"
    row1_colors = ["white", "white", dev_color, state_color]
    
    for pos, label, value, color in zip(row1_positions, row1_labels, row1_values, row1_colors):
        fig.add_annotation(x=pos, y=-0.16, text=f"<b>{label}</b>", showarrow=False,
                           font=dict(color="#9aa0a6", size=13), xref="paper", yref="paper")
        font_size = 22 if "حالة" in label else 26
        fig.add_annotation(x=pos, y=-0.23, text=f"<b>{value}</b>", showarrow=False,
                           font=dict(color=color, size=font_size), xref="paper", yref="paper")
    
    fig.add_shape(type="line", x0=0.02, x1=0.98, y0=-0.30, y1=-0.30,
                  line=dict(color="#555", width=1), xref="paper", yref="paper")
    
    row2_positions = [0.083, 0.25, 0.417, 0.583, 0.75, 0.917]
    row2_labels = ["📍 سعر تنفيذ Call", "📊 نسبة Call %", "🌊 IV Call",
                   "📍 سعر تنفيذ Put", "📊 نسبة Put %", "🌊 IV Put"]
    row2_values = [f"${call_strike:.2f}", f"{call_pct:.0%}", f"{call_iv:.4f}",
                   f"${put_strike:.2f}", f"{put_pct:.0%}", f"{put_iv:.4f}"]
    row2_colors = ["limegreen", "limegreen", "limegreen", "crimson", "crimson", "crimson"]
    
    for pos, label, value, color in zip(row2_positions, row2_labels, row2_values, row2_colors):
        fig.add_annotation(x=pos, y=-0.36, text=f"<b>{label}</b>", showarrow=False,
                           font=dict(color="#9aa0a6", size=11), xref="paper", yref="paper")
        fig.add_annotation(x=pos, y=-0.42, text=f"<b>{value}</b>", showarrow=False,
                           font=dict(color=color, size=22), xref="paper", yref="paper")
    
    if y_range_mode == "auto":
        final_y_min, final_y_max = auto_y_min, auto_y_max
    elif y_range_mode == "manual" and y_range_manual is not None:
        final_y_min, final_y_max = y_range_manual
    else:
        final_y_min, final_y_max = auto_y_min, auto_y_max
    
    fig.update_layout(title="IV Skew (Auto-Scale)", yaxis_title="IV Spread", xaxis_title="Time",
                      font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                      height=700, margin=dict(l=10, r=10, t=40, b=200), showlegend=True,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="right", x=1, font=dict(color="white")))
    fig.update_xaxes(gridcolor='gray')
    fig.update_yaxes(gridcolor='gray', range=[final_y_min, final_y_max])
    return fig


def plot_ratio_line(df, S, x_col, y_col, title, y_axis, line_color='magenta'):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode='lines+markers',
                             line=dict(color=line_color, width=2), marker=dict(size=6),
                             name='Gamma / OI Ratio'))
    fig.add_vline(x=S, line_dash="dash", line_color="white",
                  annotation_text=f"S = {S:.1f}", annotation_position="top right",
                  annotation_font=dict(color="white"))
    fig.update_layout(title=title, yaxis_title=y_axis, xaxis_title="Strike Price",
                      font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                      hovermode="x unified", margin=dict(l=10, r=10, t=40, b=40))
    fig.update_xaxes(gridcolor='gray')
    fig.update_yaxes(gridcolor='gray')
    return fig


def plot_cumulative_delta(df, S, x_col, y_col, title, y_axis, line_color='deepskyblue'):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x_col], y=df[y_col], mode='lines', fill='tozeroy',
                             line=dict(color=line_color, width=2), name='Net Delta'))
    fig.add_vline(x=S, line_dash="dash", line_color="white",
                  annotation_text=f"S = {S:.1f}", annotation_position="top right",
                  annotation_font=dict(color="white"))
    fig.update_layout(title=title, yaxis_title=y_axis, xaxis_title="Strike Price",
                      font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                      hovermode="x unified", showlegend=True,
                      margin=dict(l=10, r=10, t=40, b=40))
    fig.update_xaxes(gridcolor='gray')
    fig.update_yaxes(gridcolor='gray')
    return fig


def single_date_page(symbol):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    st.header("تحليل تاريخ انتهاء واحد")
    st.caption(f"التاريخ: {today}")

    current_price, expiration_date, df, T = fetch_options_data(symbol)
    if df is None:
        st.error(f"لا توجد بيانات خيارات للرمز {symbol}.")
        return

    S = current_price
    q = 0.0

    status, _ = get_market_status()
    market_status = "🟢 السوق مفتوح" if status == "open" else "🟡 السوق مغلق"
    st.info(f"📊 البيانات من GitHub Actions — {market_status} — التحديث كل 30 ثانية")

    with st.sidebar:
        st.markdown("## الإعدادات")
        r = st.slider("سعر الفائدة الخالي من المخاطر (r)", 0.0, 0.2, 0.05, 0.005)
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("تحديث سريع", width="stretch"):
                st.cache_data.clear()
                st.rerun()
        with col2:
            if st.button("تحديث قسري", width="stretch"):
                st.cache_data.clear()
                st.rerun()

        if current_price is not None:
            status, _ = get_market_status()
            market_status = "مفتوح" if status == "open" else "مغلق"
            st.metric("السعر الحالي", f"${current_price:.2f}", delta=market_status)
            st.markdown(f"**تاريخ الانتهاء:** `{expiration_date}`")
            st.caption(f"آخر تحديث: {datetime.datetime.now().strftime('%I:%M:%S %p')}")
        
        st.divider()
        
        min_strike = int(df['strike'].min())
        max_strike = int(df['strike'].max())
        strike_range = st.slider("نطاق أسعار التنفيذ", min_value=min_strike,
                                 max_value=max_strike, value=(min_strike, max_strike), step=5)
        st.caption("قم بتفعيل زر القفل أسفل كل رسم بياني لتثبيت النطاق.")

    settings = DEFAULT_SETTINGS.copy()
    df_filtered = df[(df['strike'] >= strike_range[0]) & (df['strike'] <= strike_range[1])].copy()
    df_sorted = df_filtered.sort_values('strike').reset_index(drop=True)

    if df_sorted.empty:
        st.warning("لا توجد بيانات في النطاق المحدد.")
        return

    sigma = np.maximum(df_sorted['weighted_IV'].values, 0.001)
    K = df_sorted['strike'].values
    oi_c = df_sorted['openInterest_call'].values
    oi_p = df_sorted['openInterest_put'].values

    delta_c = delta_call(S, K, T, r, sigma, q)
    delta_p = delta_put(S, K, T, r, sigma, q)
    gamma_val = gamma(S, K, T, r, sigma, q)
    vanna_val = vanna(S, K, T, r, sigma, q)
    vega_val = vega(S, K, T, r, sigma, q)
    theta_c = theta_call(S, K, T, r, sigma, q)
    theta_p = theta_put(S, K, T, r, sigma, q)
    charm_c = charm_call(S, K, T, r, sigma, q)
    charm_p = charm_put(S, K, T, r, sigma, q)
    speed_val = speed(S, K, T, r, sigma, q)

    SCALE = 10000

    df_sorted['call_delta'] = oi_c * delta_c
    df_sorted['put_delta'] = oi_p * delta_p
    df_sorted['call_gamma'] = oi_c * gamma_val
    df_sorted['put_gamma'] = oi_p * gamma_val * -1
    df_sorted['call_gamma_gold'] = oi_c * gamma_val * 1.2
    df_sorted['put_gamma_gold'] = oi_p * gamma_val * -1.2
    df_sorted['call_vanna'] = oi_c * vanna_val
    df_sorted['put_vanna'] = oi_p * vanna_val
    df_sorted['openInterest_call_display'] = oi_c
    df_sorted['openInterest_put_display'] = oi_p * -1
    df_sorted['call_vega'] = oi_c * vega_val
    df_sorted['put_vega'] = oi_p * vega_val
    df_sorted['call_theta'] = oi_c * theta_c
    df_sorted['put_theta'] = oi_p * theta_p
    df_sorted['call_charm'] = oi_c * charm_c * SCALE
    df_sorted['put_charm'] = oi_p * charm_p * SCALE
    df_sorted['call_speed'] = oi_c * speed_val * SCALE
    df_sorted['put_speed'] = oi_p * speed_val * SCALE
    
    df_sorted['net_gamma'] = df_sorted['call_gamma'] + df_sorted['put_gamma']
    df_sorted['net_vanna'] = df_sorted['call_vanna'] + df_sorted['put_vanna']
    df_sorted['total_gamma'] = df_sorted['call_gamma'] + df_sorted['put_gamma']
    df_sorted['total_oi'] = df_sorted['openInterest_call'] + df_sorted['openInterest_put']
    df_sorted['gamma_ratio'] = df_sorted['total_gamma'] / (df_sorted['total_oi'] + 1)

    skew_value, call_iv, put_iv, call_strike, put_strike = calculate_iv_skew(df_sorted, S, settings)
    
    if 'iv_skew_history' not in st.session_state:
        st.session_state.iv_skew_history = deque(maxlen=settings['iv_sma_period'] + 10)
    st.session_state.iv_skew_history.append(skew_value)
    skew_history = list(st.session_state.iv_skew_history)
    
    sma_period = settings['iv_sma_period']
    if len(skew_history) >= sma_period:
        sma_value = np.mean(skew_history[-sma_period:])
        sma_history = []
        for i in range(sma_period, len(skew_history) + 1):
            sma_history.append(np.mean(skew_history[i-sma_period:i]))
    else:
        sma_value = np.mean(skew_history) if skew_history else 0
        sma_history = []
    deviation = (skew_value - sma_value) / sma_value if sma_value != 0 else 0

    zero_gamma_level, net_gamma_vals = calculate_zero_gamma(df_sorted, S)
    distance_to_zero_gamma = S - zero_gamma_level
    setup_signal = "Bullish Setup" if S > zero_gamma_level else "Bearish Setup"

    max_gamma = max(abs(df_sorted['net_gamma'].max()), abs(df_sorted['net_gamma'].min())) if 'net_gamma' in df_sorted else 1
    max_vanna = max(abs(df_sorted['net_vanna'].max()), abs(df_sorted['net_vanna'].min())) if 'net_vanna' in df_sorted else 1
    zones = calculate_confluence_zones(df_sorted, S, max_gamma, max_vanna, settings)

    current_net_gex = df_sorted['net_gamma'].sum()
    st.session_state.gex_history.add(current_net_gex)
    gex_60min_ago = st.session_state.gex_history.get_60min_ago()
    gex_flow = current_net_gex - gex_60min_ago if gex_60min_ago is not None else 0

    st.divider()
    fig_combined = create_combined_chart(zero_gamma_level, distance_to_zero_gamma,
                                         setup_signal, gex_flow, zones, S, expiration_date, settings)
    st.plotly_chart(fig_combined, use_container_width=True, key="chart_combined")

    st.divider()
    st.subheader("📉 مؤشر انحراف التقلب (IV Skew)")

    col_ctrl1, col_ctrl2 = st.columns([3, 1])
    with col_ctrl2:
        auto_scale = st.checkbox("Auto-Scale تلقائي", value=True, key="iv_skew_auto")
    
    if not auto_scale:
        with st.expander("⚙️ ضبط نطاق Y يدوياً", expanded=True):
            col_a, col_b = st.columns(2)
            with col_a:
                y_min_manual = st.number_input("الحد الأدنى", value=-0.05, step=0.01, key="iv_y_min")
            with col_b:
                y_max_manual = st.number_input("الحد الأعلى", value=0.10, step=0.01, key="iv_y_max")
        y_range_manual = (y_min_manual, y_max_manual)
    else:
        y_range_manual = None
    
    fig_skew = plot_iv_skew(skew_history, sma_history, skew_value, sma_value, deviation,
                            call_strike, put_strike, call_iv, put_iv,
                            settings['iv_skew_call_pct'], settings['iv_skew_put_pct'],
                            y_range_mode="auto" if auto_scale else "manual",
                            y_range_manual=y_range_manual)
    st.plotly_chart(fig_skew, use_container_width=True, key="chart_iv_skew")

    metrics = [
        ('openInterest_call_display', 'openInterest_put_display', 'Open Interest', 'Contracts'),
        ('call_gamma', 'put_gamma', 'Gamma Exposure', 'Gamma Exposure'),
        ('call_gamma_gold', 'put_gamma_gold', 'Gamma Gold', 'Gamma Exposure'),
        ('call_delta', 'put_delta', 'Delta Exposure', 'Delta Exposure'),
        ('call_vanna', 'put_vanna', 'Vanna Exposure', 'Vanna Exposure'),
        ('call_vega', 'put_vega', 'Vega Exposure', 'Vega Exposure'),
        ('call_theta', 'put_theta', 'Theta Exposure', 'Theta Exposure'),
        ('call_charm', 'put_charm', 'Charm Exposure (x10k)', 'Charm (x10k)'),
        ('call_speed', 'put_speed', 'Speed Exposure (x10k)', 'Speed (x10k)'),
        ('impliedVolatility_call', 'impliedVolatility_put', 'Implied Volatility', 'IV'),
    ]

    any_frozen = False
    for call_col, put_col, title, yaxis in metrics:
        x_range = st.session_state.get(f"xrange_{title}", None)
        
        if title == "Gamma Gold":
            zero_gamma = zero_gamma_level
            zones_list = zones
            gex_flow_val = gex_flow
        else:
            zero_gamma = None
            zones_list = None
            gex_flow_val = None
        
        fig = plot_metric_single(df_sorted, S, call_col, put_col, title, yaxis,
                                 x_range=x_range, zero_gamma_level=zero_gamma,
                                 zones=zones_list, gex_flow=gex_flow_val)
        
        col_plot, col_freeze = st.columns([0.96, 0.04])
        with col_plot:
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{title}")
        with col_freeze:
            st.write("")
            frozen = st.checkbox("قفل", key=f"freeze_{title}",
                                 value=st.session_state.get(f"freeze_{title}", False))
            if frozen:
                any_frozen = True

    fig_ratio = plot_ratio_line(df_sorted, S, 'strike', 'gamma_ratio',
                                'Gamma / Open Interest Ratio', 'Gamma per Contract', 'magenta')
    st.plotly_chart(fig_ratio, use_container_width=True)

    df_sorted['net_delta'] = df_sorted['call_delta'] - df_sorted['put_delta']
    df_sorted['cumulative_delta'] = df_sorted['net_delta'].cumsum()

    if "show_cum_delta" not in st.session_state:
        st.session_state.show_cum_delta = False

    col_btn, col_title = st.columns([0.15, 0.85])
    with col_btn:
        label = "إخفاء" if st.session_state.show_cum_delta else "إظهار"
        if st.button(label, key="toggle_cum_delta"):
            st.session_state.show_cum_delta = not st.session_state.show_cum_delta
            st.rerun()
    with col_title:
        st.write("### 📊 الدلتا التراكمي (Cumulative Delta Exposure)")

    if st.session_state.show_cum_delta:
        fig_cum = plot_cumulative_delta(df_sorted, S, 'strike', 'cumulative_delta',
                                        'Cumulative Delta Exposure', 'Cumulative Net Delta', 'deepskyblue')
        st.plotly_chart(fig_cum, use_container_width=True)
    else:
        st.caption("🔒 المؤشر مخفي. اضغط على زر 'إظهار' لعرضه.")

    st.divider()
    st.subheader("📋 قائمة الخيارات - صافي العقود")

    df_inventory = df_sorted.copy()
    df_inventory['Net_Contracts'] = df_inventory['openInterest_call'] - df_inventory['openInterest_put']

    fig_inv = go.Figure()
    bought = df_inventory[df_inventory['Net_Contracts'] > 0]
    if not bought.empty:
        fig_inv.add_trace(go.Bar(x=bought['strike'], y=bought['Net_Contracts'],
                                 marker_color='limegreen', name='BOUGHT',
                                 text=bought['Net_Contracts'].apply(lambda x: f'{x:.0f}'),
                                 textposition='outside'))
    sold = df_inventory[df_inventory['Net_Contracts'] < 0]
    if not sold.empty:
        fig_inv.add_trace(go.Bar(x=sold['strike'], y=sold['Net_Contracts'],
                                 marker_color='crimson', name='SOLD',
                                 text=sold['Net_Contracts'].apply(lambda x: f'{x:.0f}'),
                                 textposition='outside'))

    fig_inv.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
    fig_inv.add_vline(x=S, line_dash="dash", line_color="yellow",
                      annotation_text=f"S = {S:.2f}", annotation_position="top",
                      annotation_font=dict(color="yellow", size=12))

    min_s = df_inventory['strike'].min()
    max_s = df_inventory['strike'].max()
    if S < min_s:
        min_s = S - (max_s - min_s) * 0.15
    elif S > max_s:
        max_s = S + (max_s - min_s) * 0.15
    center = S
    half_range = max(center - min_s, max_s - center) * 1.2
    x_range_inv = (center - half_range, center + half_range)

    total_oi_calls = df_inventory['openInterest_call'].sum()
    total_oi_puts = df_inventory['openInterest_put'].sum()
    total_net = total_oi_calls - total_oi_puts

    fig_inv.update_layout(
        title=dict(text=f"Net Options Positions - {symbol} - {expiration_date}",
                   x=0.02, xanchor='left', font=dict(color="white", size=16)),
        xaxis_title="", yaxis_title="Net Contracts",
        font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
        hovermode="x unified", barmode='relative',
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(color="white")),
        height=750, margin=dict(l=60, r=20, t=50, b=170))

    fig_inv.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True, thickness=0.08),
                         range=x_range_inv, showticklabels=True)
    fig_inv.update_yaxes(gridcolor='gray', zeroline=True, zerolinecolor='white')

    fig_inv.add_shape(type="line", x0=0.02, x1=0.98, y0=-0.23, y1=-0.23,
                      line=dict(color="#555", width=1), xref="paper", yref="paper")

    metric_positions = [0.125, 0.375, 0.625, 0.875]
    metric_labels = ["إجمالي OI (Calls)", "إجمالي OI (Puts)", "صافي العقود الكلي", "السعر الحالي"]
    metric_values = [f"{total_oi_calls:,.0f}", f"{total_oi_puts:,.0f}",
                     f"{total_net:+,.0f}", f"${S:.2f}"]
    net_color = "limegreen" if total_net > 0 else "crimson"
    metric_colors = ["white", "white", net_color, "white"]

    for pos, label, value, color in zip(metric_positions, metric_labels, metric_values, metric_colors):
        fig_inv.add_annotation(x=pos, y=-0.28, text=f"<b>{label}</b>", showarrow=False,
                               font=dict(color="#9aa0a6", size=13), xref="paper", yref="paper")
        fig_inv.add_annotation(x=pos, y=-0.36, text=f"<b>{value}</b>", showarrow=False,
                               font=dict(color=color, size=26), xref="paper", yref="paper")

    st.plotly_chart(fig_inv, use_container_width=True, key="chart_inventory")

    st.divider()
    csv_data_all = df_sorted.to_csv(index=False).encode('utf-8')
    st.download_button(label="تحميل جميع البيانات CSV", data=csv_data_all,
                       file_name=f'{symbol}_options_{expiration_date}.csv',
                       mime='text/csv', key='download_csv_single')

    if should_autorefresh():
        st_autorefresh(interval=15 * 1000, key="auto_normal")
    else:
        st.caption("التحديث التلقائي متوقف (خارج ساعات السوق).")


def multi_date_page(symbol):
    st.header("مقارنة تواريخ انتهاء متعددة")

    with st.sidebar:
        r = st.slider("سعر الفائدة (r)", 0.0, 0.2, 0.05, 0.005, key="r_multi")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("تحديث سريع", key="refresh_multi_quick", width="stretch"):
                st.cache_data.clear()
                st.rerun()
        with col2:
            if st.button("تحديث قسري", key="refresh_multi_force", width="stretch"):
                st.cache_data.clear()
                st.rerun()
        current_price = get_current_price(symbol)
        status, _ = get_market_status()
        market_status = "مفتوح" if status == "open" else "مغلق"
        if current_price:
            st.metric("السعر الحالي", f"${current_price:.2f}", delta=market_status)
        st.caption(f"{datetime.datetime.now().strftime('%I:%M:%S %p')}")

    all_exps = get_available_expirations(symbol)
    if not all_exps:
        st.error("لا توجد تواريخ انتهاء متاحة.")
        return

    selected_exps = st.multiselect("اختر تواريخ الانتهاء (حد أقصى 5)", all_exps,
                                   default=all_exps[:2] if len(all_exps) >= 2 else all_exps,
                                   max_selections=5)
    if not selected_exps:
        st.warning("اختر تاريخاً واحداً على الأقل.")
        return

    dfs = {}
    S = current_price if current_price else 0
    q = 0.0
    SCALE = 10000
    for exp in selected_exps:
        curr_price, exp_date, df, T = fetch_options_data(symbol, exp)
        if df is None:
            continue
        df = df.sort_values('strike')
        K = df['strike'].values
        sigma = np.maximum(df['weighted_IV'].values, 0.001)
        oi_c = df['openInterest_call'].values
        oi_p = df['openInterest_put'].values
        
        dfs[exp] = {
            'strike': K,
            'total_oi': oi_c + oi_p,
            'total_delta': oi_c * delta_call(S, K, T, r, sigma, q) + oi_p * delta_put(S, K, T, r, sigma, q),
            'total_gamma': (oi_c - oi_p) * gamma(S, K, T, r, sigma, q),
            'total_vanna': (oi_c + oi_p) * vanna(S, K, T, r, sigma, q),
            'total_vega': (oi_c + oi_p) * vega(S, K, T, r, sigma, q),
            'total_theta': oi_c * theta_call(S, K, T, r, sigma, q) + oi_p * theta_put(S, K, T, r, sigma, q),
            'total_charm': (oi_c * charm_call(S, K, T, r, sigma, q) + oi_p * charm_put(S, K, T, r, sigma, q)) * SCALE,
            'total_speed': (oi_c + oi_p) * speed(S, K, T, r, sigma, q) * SCALE,
            'total_iv': df['weighted_IV']
        }

    compare_metrics = [
        ("total_oi", "Total Open Interest"),
        ("total_gamma", "Total Gamma Exposure"),
        ("total_delta", "Total Delta Exposure"),
        ("total_vanna", "Total Vanna Exposure"),
        ("total_vega", "Total Vega Exposure"),
        ("total_theta", "Total Theta Exposure"),
        ("total_charm", "Total Charm Exposure (x10k)"),
        ("total_speed", "Total Speed Exposure (x10k)"),
        ("total_iv", "Implied Volatility (avg)"),
    ]

    for key, title in compare_metrics:
        fig = go.Figure()
        all_strikes = []
        for exp in selected_exps:
            if exp in dfs:
                data = dfs[exp]
                all_strikes.extend(data['strike'])
                fig.add_trace(go.Scatter(x=data['strike'], y=data[key], mode='lines', name=exp))
        
        if all_strikes and S:
            min_s = min(all_strikes)
            max_s = max(all_strikes)
            if S < min_s:
                min_s = S - (max_s - min_s) * 0.15
            elif S > max_s:
                max_s = S + (max_s - min_s) * 0.15
            center = S
            half_range = max(center - min_s, max_s - center) * 1.2
            x_range = (center - half_range, center + half_range)
        else:
            x_range = None
        
        if S:
            fig.add_vline(x=S, line_dash="dash", line_color="white",
                          annotation_text=f"S = {S:.1f}", annotation_position="top",
                          annotation_font=dict(color="white", size=12))
        
        display_title = METRICS_LABELS.get(title, title)
        fig.update_layout(title=display_title, xaxis_title="Strike Price", yaxis_title="Value",
                          font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                          showlegend=True, margin=dict(l=10, r=10, t=40, b=40))
        fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range)
        fig.update_yaxes(gridcolor='gray')
        st.plotly_chart(fig, use_container_width=True)


def main():
    if "show_visitors" not in st.session_state:
        st.session_state.show_visitors = False

    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_page()
        return

    with st.sidebar:
        st.divider()
        if st.button("تسجيل الخروج", width="stretch"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()

    col_title, col_selector = st.columns([2, 1])
    with col_title:
        st.title("Quantitative Options Radar")
        st.caption(f"مرحباً، {st.session_state.username}")
    with col_selector:
        symbol = st.selectbox("اختر الرمز", ["GLD", "SPY", "SPX", "QQQ", "NDX"], index=0)
        st.caption(f"تحليل: {symbol}")

    metadata = get_options_metadata()
    if metadata["last_updated"] != "Unknown":
        try:
            last_update = datetime.datetime.fromisoformat(metadata["last_updated"])
            time_diff = datetime.datetime.now() - last_update
            minutes_ago = int(time_diff.total_seconds() / 60)
            if minutes_ago < 60:
                st.info(f"آخر تحديث للبيانات: قبل {minutes_ago} دقيقة ({last_update.strftime('%H:%M')})")
            else:
                hours_ago = minutes_ago // 60
                st.warning(f"آخر تحديث للبيانات: قبل {hours_ago} ساعة ({last_update.strftime('%H:%M')})")
        except:
            st.info(f"آخر تحديث: {metadata['last_updated']}")

    st.divider()

    page = st.sidebar.radio("اختر الصفحة", ["تحليل تاريخ انتهاء واحد", "مقارنة تواريخ متعددة"])

    if page == "تحليل تاريخ انتهاء واحد":
        single_date_page(symbol)
    else:
        multi_date_page(symbol)

    track_visitors(st.session_state.username)

    if st.session_state.username == "admin":
        st.divider()
        col_btn, col_title_bloc = st.columns([0.2, 0.8])
        with col_btn:
            label = "إخفاء" if st.session_state.show_visitors else "إظهار"
            if st.button(label, width="stretch"):
                st.session_state.show_visitors = not st.session_state.show_visitors
                st.rerun()
        with col_title_bloc:
            st.subheader("👥 إحصائيات الزوار (آخر 24 ساعة)")
        if st.session_state.show_visitors:
            display_visitor_widget()
        else:
            st.caption("🔒 الجدول مخفي. اضغط على زر 'إظهار' لعرضه.")


if __name__ == "__main__":
    main()
