import streamlit as st
import yfinance as yf
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

# ========== إعدادات الصفحة ==========
st.set_page_config(page_title="رادار عادل للخيارات الكمية", layout="wide")

# ========== بيانات اعتماد تسجيل الدخول ==========
CREDENTIALS = {
    "admin": "198200",
    "moha33": "tickmillx33"
}

# ========== أسماء الأدوات ==========
METRICS_LABELS = {
    "Open Interest": "📊 مركز السيولة (Open Interest)",
    "Gamma Exposure": "⚡ قوة الدفع (Gamma Exposure)",
    "Gamma Gold": "⚡ قوة الدفع الذهبية (Gamma Gold)",
    "Delta Exposure": "📌 دلتا (Delta Exposure)",
    "Vanna Exposure": "🌊 تأثير التقلب (Vanna Exposure)",
    "Vanna Gold": "🌊 تأثير التقلب الذهبي (Vanna Gold) + Gamma",  # تمت إعادتها
    "Vega Exposure": "📈 فيغا (Vega Exposure)",
    "Theta Exposure": "⏳ ثيتا (Theta Exposure)",
    "Charm Exposure (x10k)": "🕰️ سحر الدلتا (Charm Exposure ×10k)",
    "Speed Exposure (x10k)": "🚀 سرعة غاما (Speed Exposure ×10k)",
    "Implied Volatility": "😰 مؤشر القلق (Implied Volatility)",
    "IV Skew": "📉 انحراف التقلب (IV Skew)",
}

# ========== نظام تتبع الزوار ==========
VISITOR_FILE = "visitors_log.json"

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
            log['username'] = username if username else log.get('username', 'زائر')
            existing = True
            break
    
    if not existing:
        filtered_logs.append({
            'id': visitor_id,
            'country': country,
            'username': username if username else 'زائر',
            'timestamp': now
        })
    
    with open(VISITOR_FILE, 'w') as f:
        json.dump(filtered_logs, f, indent=2)
    
    return filtered_logs

def display_visitor_widget():
    logs = track_visitors()
    total_visitors = len(logs)
    
    if total_visitors == 0:
        st.info("👤 لا يوجد زوار مسجلون خلال الـ 24 ساعة الماضية.")
        return
    
    data = []
    for log in logs:
        dt = datetime.datetime.fromtimestamp(log['timestamp']).strftime('%Y-%m-%d %I:%M %p')
        data.append({
            'اسم المستخدم 👤': log.get('username', 'زائر'),
            'الدولة 🌍': log['country'],
            'آخر اتصال 🕒': dt
        })
    
    df_visitors = pd.DataFrame(data)
    
    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("👥 زوار فريدون (24 ساعة)", total_visitors)
    with col2:
        st.dataframe(
            df_visitors,
            use_container_width=True,
            hide_index=True,
            height=min(200, 35 + 35 * total_visitors)
        )

# ========== صفحة تسجيل الدخول ==========
def login_page():
    st.markdown("""
        <style>
            .stTextInput {
                text-align: center;
            }
            .stTextInput > div {
                display: flex;
                justify-content: center;
            }
            .stTextInput input {
                text-align: center;
                max-width: 300px;
                margin: 0 auto;
            }
            .login-title {
                text-align: center;
                margin-bottom: 30px;
                font-size: 28px;
                font-weight: bold;
                color: #00d4ff;
            }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-title">🔐 رادار عادل للخيارات الكمية</div>', unsafe_allow_html=True)
        
        with st.form(key="login_form", clear_on_submit=False):
            username = st.text_input("👩‍🏫 اسم المستخدم", placeholder="👩‍🏫 أدخل اسم المستخدم", key="login_username")
            password = st.text_input("🔑 كلمة المرور", placeholder="🔑 أدخل كلمة المرور", type="password", key="login_password")
            
            login_btn = st.form_submit_button("🚀 دخول", use_container_width=True)
            
            if login_btn:
                if username in CREDENTIALS and CREDENTIALS[username] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success(f"✅ مرحباً بك، {username}!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ اسم المستخدم أو كلمة المرور غير صحيحة.")

# ========== دوال التحقق من حالة السوق ==========
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
        target_time = datetime.time(8, 30)
        current_time = now_ny.time()
        if current_time <= target_time:
            return True
        else:
            return False
    else:
        target_time = datetime.time(15, 0)
        current_time = now_ny.time()
        if current_time >= target_time:
            return False
        else:
            return True

# ========== دوال بلاك-شولز ==========
def d1(S, K, T, r, sigma, q=0.0):
    return (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))

def delta_call(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    return np.exp(-q * T) * norm.cdf(d1_val)

def delta_put(S, K, T, r, sigma, q=0.0):
    d1_val = d1(S, K, T, r, sigma, q)
    return np.exp(-q * T) * (norm.cdf(d1_val) - 1)

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

# ========== GEX History ==========
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

# ========== جلب البيانات ==========
@st.cache_data(ttl=120)
def fetch_options_data(symbol, expiration_date=None):
    if symbol == "SPX":
        symbol = "^SPX"
    elif symbol == "NDX":
        symbol = "^NDX"
    
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="1d")
    if hist.empty:
        st.error(f"⚠️ لا توجد بيانات للسعر للرمز {symbol}. تحقق من الاتصال بالإنترنت أو الرمز.")
        return None, None, None, None
    
    current_price = hist['Close'].iloc[-1]
    all_expirations = ticker.options

    if not all_expirations:
        st.warning(f"⚠️ لا توجد تواريخ انتهاء متاحة للرمز {symbol}.")
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

# ========== حساب IV Skew ==========
def calculate_iv_skew(df, S, settings):
    call_pct = settings.get('iv_skew_call_pct', 1.15)
    put_pct = settings.get('iv_skew_put_pct', 0.85)
    
    call_target = S * call_pct
    put_target = S * put_pct
    
    strikes = df['strike'].values
    call_idx = np.argmin(np.abs(strikes - call_target))
    put_idx = np.argmin(np.abs(strikes - put_target))
    
    call_iv = df.iloc[call_idx].get('impliedVolatility_call', 0.001)
    put_iv = df.iloc[put_idx].get('impliedVolatility_put', 0.001)
    
    call_iv = max(call_iv, 0.001)
    put_iv = max(put_iv, 0.001)
    
    skew = call_iv - put_iv
    return skew, call_iv, put_iv, df.iloc[call_idx]['strike'], df.iloc[put_idx]['strike']

# ========== حساب صفر غاما ==========
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

# ========== حساب مناطق التقاء غاما وفانا (للأعلى) ==========
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
            zones.append({
                'strike': strike,
                'type': 'squeeze',
                'gamma_norm': gamma_norm,
                'vanna_norm': vanna_norm,
                'color': 'limegreen'
            })
        
        if gamma_norm < -threshold and vanna_norm < -threshold and strike < S:
            zones.append({
                'strike': strike,
                'type': 'meltdown',
                'gamma_norm': gamma_norm,
                'vanna_norm': vanna_norm,
                'color': 'red'
            })
    
    return zones

# ========== دوال الرسم ==========
def plot_metric_single(df, S, call_col, put_col, title, y_axis, 
                       call_color='limegreen', put_color='crimson', x_range=None,
                       zero_gamma_level=None, zones=None, gex_flow=None,
                       show_gamma_line=False, gamma_line_data=None):
    fig = go.Figure()
    
    fig.add_trace(go.Bar(x=df['strike'], y=df[call_col], marker_color=call_color, name='Calls', legendgroup='calls'))
    fig.add_trace(go.Bar(x=df['strike'], y=df[put_col], marker_color=put_color, name='Puts', legendgroup='puts'))
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
                  annotation_text=f"S = {S:.1f}",
                  annotation_position="top",
                  annotation_font=dict(color="white", size=12))
    
    if zero_gamma_level is not None:
        fig.add_vline(x=zero_gamma_level, line_dash="dash", line_color="white",
                      annotation_text="Zero-Gamma",
                      annotation_position="bottom",
                      annotation_font=dict(color="white", size=10))
    
    if zones:
        for zone in zones:
            color = zone['color']
            marker = '💥' if zone['type'] == 'squeeze' else '⬇️'
            fig.add_vline(x=zone['strike'], line_dash="dot", line_color=color,
                          annotation_text=f"{marker} {zone['type'].upper()}",
                          annotation_position="top",
                          annotation_font=dict(color=color, size=10))
    
    if gex_flow is not None:
        fig.add_annotation(
            x=0.95, y=0.95,
            xref="paper", yref="paper",
            text=f"GEX Flow: {gex_flow:+.0f}",
            showarrow=False,
            font=dict(color="limegreen" if gex_flow > 0 else "crimson", size=14),
            bgcolor="rgba(0,0,0,0.7)",
            borderpad=4
        )
    
    # إضافة خط Gamma لـ Vanna Gold
    if show_gamma_line and gamma_line_data is not None:
        fig.add_trace(go.Scatter(
            x=df['strike'],
            y=gamma_line_data,
            mode='lines',
            line=dict(color='cyan', width=2, dash='dash'),
            name='Gamma Exposure'
        ))

    display_title = METRICS_LABELS.get(title, title)
    fig.update_layout(
        title=display_title,
        yaxis_title=y_axis,
        xaxis_title="Strike Price",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="white")),
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range)
    fig.update_yaxes(gridcolor='gray')
    return fig

def plot_iv_skew(skew_history, sma_history, current_skew, sma_value, deviation):
    fig = go.Figure()
    
    if skew_history:
        fig.add_trace(go.Scatter(
            x=list(range(len(skew_history))),
            y=skew_history,
            mode='lines',
            line=dict(color='cyan', width=2),
            name='IV Skew'
        ))
    
    if sma_history:
        fig.add_trace(go.Scatter(
            x=list(range(len(sma_history))),
            y=sma_history,
            mode='lines',
            line=dict(color='orange', width=2, dash='dash'),
            name='SMA 20'
        ))
    
    color = 'yellow' if abs(deviation) > 0.20 else 'white'
    fig.add_annotation(
        x=0.5, y=0.95,
        xref="paper", yref="paper",
        text=f"Skew: {current_skew:.4f} | SMA: {sma_value:.4f} | Dev: {deviation:.2%}",
        showarrow=False,
        font=dict(color=color, size=12),
        bgcolor="rgba(0,0,0,0.6)",
        borderpad=4
    )
    
    fig.update_layout(
        title="📉 انحراف التقلب (IV Skew)",
        yaxis_title="IV Spread",
        xaxis_title="الوقت",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig.update_xaxes(gridcolor='gray')
    fig.update_yaxes(gridcolor='gray')
    return fig

def plot_ratio_line(df, S, x_col, y_col, title, y_axis, line_color='magenta'):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[y_col],
        mode='lines+markers',
        line=dict(color=line_color, width=2),
        marker=dict(size=6),
        name='Gamma / OI Ratio'
    ))
    fig.add_vline(x=S, line_dash="dash", line_color="white",
                  annotation_text=f"S = {S:.1f}", annotation_position="top right",
                  annotation_font=dict(color="white"))
    fig.update_layout(
        title=title,
        yaxis_title=y_axis,
        xaxis_title="Strike Price",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig.update_xaxes(gridcolor='gray')
    fig.update_yaxes(gridcolor='gray')
    return fig

def plot_cumulative_delta(df, S, x_col, y_col, title, y_axis, line_color='deepskyblue'):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[y_col],
        mode='lines', fill='tozeroy',
        line=dict(color=line_color, width=2),
        name='Net Delta'
    ))
    fig.add_vline(x=S, line_dash="dash", line_color="white",
                  annotation_text=f"S = {S:.1f}", annotation_position="top right",
                  annotation_font=dict(color="white"))
    fig.update_layout(
        title=title,
        yaxis_title=y_axis,
        xaxis_title="Strike Price",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        showlegend=True,
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig.update_xaxes(gridcolor='gray')
    fig.update_yaxes(gridcolor='gray')
    return fig

# ========== صفحة تاريخ واحد ==========
def single_date_page(symbol):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    st.header("تحليل تاريخ انتهاء واحد")
    st.caption(f"📅 {today}")

    current_price, expiration_date, df, T = fetch_options_data(symbol)
    if df is None:
        st.error(f"لا توجد بيانات خيارات للرمز {symbol}.")
        return

    S = current_price
    q = 0.0

    # ===== إعدادات المستخدم =====
    with st.sidebar:
        st.markdown("## ⚙️ الإعدادات")
        r = st.slider("سعر الفائدة الخالي من المخاطر (r)", 0.0, 0.2, 0.05, 0.005)
        
        st.divider()
        st.markdown("### 🎯 إعدادات متقدمة")
        
        iv_call_pct = st.slider("IV Call نسبة السعر (%)", 1.05, 1.30, 1.15, 0.01, key="iv_call_pct")
        iv_put_pct = st.slider("IV Put نسبة السعر (%)", 0.70, 0.95, 0.85, 0.01, key="iv_put_pct")
        sma_period = st.slider("فترة SMA لـ IV Skew", 5, 50, 20, 1, key="sma_period")
        dev_threshold = st.slider("عتبة انحراف IV Skew (%)", 0.05, 0.50, 0.20, 0.01, key="dev_threshold")
        
        st.divider()
        
        confluence_pct = st.slider(
            "نسبة التقاء غاما/فانا (%)",
            0.10, 0.60, 0.30, 0.01,
            key="confluence_pct",
            help="النسبة المئوية من Max_Gamma و Max_Vanna لتحديد مناطق Squeeze و Meltdown"
        )
        
        st.divider()
        
        taha_confluence_pct = st.slider(
            "نسبة التقاء غاما/فانا لـ 🧑‍🏫 طه (%)",
            0.10, 0.60, 0.30, 0.01,
            key="taha_confluence_pct",
            help="النسبة المئوية من Max_Gamma و Max_Vanna لتحديد مناطق Squeeze و Meltdown في مؤشر طه"
        )
        
        st.divider()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 تحديث سريع", width="stretch"):
                st.rerun()
        with col2:
            if st.button("⚡ قسري", width="stretch"):
                st.cache_data.clear()
                st.rerun()

        if current_price is not None:
            status, _ = get_market_status()
            market_status = "🟢 مفتوح" if status == "open" else "🔴 مغلق"
            st.metric("💰 السعر الحالي", f"${current_price:.2f}", delta=market_status)
            st.markdown(f"**📅 تاريخ الانتهاء:** `{expiration_date}`")
            st.caption(f"🕒 آخر تحديث: {datetime.datetime.now().strftime('%I:%M:%S %p')}") 
        
        st.divider()
        
        min_strike = int(df['strike'].min())
        max_strike = int(df['strike'].max())
        strike_range = st.slider(
            "🎯 نطاق أسعار التنفيذ (Strike Range)",
            min_value=min_strike,
            max_value=max_strike,
            value=(min_strike, max_strike),
            step=5
        )
        st.caption("قم بتفعيل '🔒' أسفل كل رسم بياني لتثبيت النطاق.")

    settings = {
        'iv_skew_call_pct': iv_call_pct,
        'iv_skew_put_pct': iv_put_pct,
        'iv_sma_period': sma_period,
        'iv_deviation_threshold': dev_threshold,
        'confluence_pct': confluence_pct,
        'taha_confluence_pct': taha_confluence_pct,
    }

    df_filtered = df[(df['strike'] >= strike_range[0]) & (df['strike'] <= strike_range[1])].copy()
    df_sorted = df_filtered.sort_values('strike').reset_index(drop=True)

    if df_sorted.empty:
        st.warning("لا توجد بيانات في النطاق المحدد، يرجى توسيع النطاق.")
        return

    sigma = np.maximum(df_sorted['weighted_IV'].values, 0.001)
    K = df_sorted['strike'].values
    oi_c = df_sorted['openInterest_call'].values
    oi_p = df_sorted['openInterest_put'].values

    delta_c = delta_call(S, K, T, r, sigma, q)
    delta_p = delta_put(S, K, T, r, sigma, q)
    gamma_val = gamma(S, K, T, r, sigma, q)
    vanna_val = vanna(S, K, T, r, sigma, q)
    vega_val  = vega(S, K, T, r, sigma, q)
    theta_c   = theta_call(S, K, T, r, sigma, q)
    theta_p   = theta_put(S, K, T, r, sigma, q)
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
    # ===== إعادة Vanna Gold =====
    df_sorted['call_vanna_gold'] = oi_c * vanna_val * 1.2
    df_sorted['put_vanna_gold'] = oi_p * vanna_val * 1.2
    # ===========================
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

    # ===== IV Skew =====
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

    # ===== Zero-Gamma =====
    zero_gamma_level, net_gamma_vals = calculate_zero_gamma(df_sorted, S)
    distance_to_zero_gamma = S - zero_gamma_level
    setup_signal = "🟢 Bullish Setup" if S > zero_gamma_level else "🔴 Bearish Setup"

    # ===== Confluence Zones (للأعلى) =====
    max_gamma = max(abs(df_sorted['net_gamma'].max()), abs(df_sorted['net_gamma'].min())) if 'net_gamma' in df_sorted else 1
    max_vanna = max(abs(df_sorted['net_vanna'].max()), abs(df_sorted['net_vanna'].min())) if 'net_vanna' in df_sorted else 1
    
    zones = calculate_confluence_zones(df_sorted, S, max_gamma, max_vanna, settings)

    # ===== GEX Flow =====
    current_net_gex = df_sorted['net_gamma'].sum()
    st.session_state.gex_history.add(current_net_gex)
    
    gex_60min_ago = st.session_state.gex_history.get_60min_ago()
    gex_flow = current_net_gex - gex_60min_ago if gex_60min_ago is not None else 0

    # =================================================================
    # ===== 1. Zero-Gamma =====
    # =================================================================

    st.divider()
    st.subheader("🎯 مؤشرات صفر غاما (Zero-Gamma) - خاصة بـ Gamma Gold")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📍 مستوى صفر غاما", f"${zero_gamma_level:.2f}")
    with col2:
        st.metric("📏 المسافة من السعر", f"${distance_to_zero_gamma:.2f}", 
                  delta=f"{distance_to_zero_gamma:.2f}")
    with col3:
        st.metric("📈 الإشارة", setup_signal)
    with col4:
        st.metric("🌊 تدفق غاما (GEX Flow)", f"{gex_flow:+.0f}",
                  delta=f"{gex_flow:+.0f}", 
                  delta_color="normal")

    # =================================================================
    # ===== 2. Confluence Zones (تم إعادتها إلى الأعلى) =====
    # =================================================================

    if zones:
        st.divider()
        st.subheader("📍 مناطق التقاء غاما وفانا (Confluence Zones) - خاصة بـ Gamma Gold")
        
        squeeze_zones = [z for z in zones if z['type'] == 'squeeze']
        meltdown_zones = [z for z in zones if z['type'] == 'meltdown']
        
        if squeeze_zones:
            st.success(f"💥 Squeeze Zones (صاعد) عند: {', '.join([f'${z['strike']:.2f}' for z in squeeze_zones])}")
        if meltdown_zones:
            st.error(f"⬇️ Meltdown Zones (هابط) عند: {', '.join([f'${z['strike']:.2f}' for z in meltdown_zones])}")
        
        for zone in zones:
            if zone['type'] == 'squeeze' and S <= zero_gamma_level:
                st.warning(f"⚠️ Squeeze عند ${zone['strike']:.2f} غير مفعّل (السعر تحت صفر غاما)")
            if zone['type'] == 'meltdown' and S >= zero_gamma_level:
                st.warning(f"⚠️ Meltdown عند ${zone['strike']:.2f} غير مفعّل (السعر فوق صفر غاما)")

    # =================================================================
    # ===== 3. IV Skew =====
    # =================================================================

    st.divider()
    st.subheader("📉 مؤشر انحراف التقلب (IV Skew)")

    fig_skew = plot_iv_skew(skew_history, sma_history, skew_value, sma_value, deviation)
    st.plotly_chart(fig_skew, use_container_width=True)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📊 IV Skew الحالي", f"{skew_value:.4f}")
    with col2:
        st.metric("📈 SMA 20", f"{sma_value:.4f}")
    with col3:
        deviation_pct = deviation * 100
        st.metric("📉 الانحراف عن SMA", f"{deviation_pct:.2f}%",
                  delta=f"{deviation_pct:.2f}%",
                  delta_color="inverse" if abs(deviation) > 0.20 else "off")
    with col4:
        st.metric("🎯 حالة الانحراف", "⚠️ غير طبيعي" if abs(deviation) > 0.20 else "✅ طبيعي")

    with st.expander("📊 تفاصيل IV Skew"):
        st.write(f"**سعر التنفيذ لـ Call ({settings['iv_skew_call_pct']:.0%}):** ${call_strike:.2f} - IV: {call_iv:.4f}")
        st.write(f"**سعر التنفيذ لـ Put ({settings['iv_skew_put_pct']:.0%}):** ${put_strike:.2f} - IV: {put_iv:.4f}")
        st.write(f"**الفرق (Skew):** {skew_value:.4f}")
        st.write(f"**SMA {settings['iv_sma_period']}:** {sma_value:.4f}")
        st.write(f"**الانحراف:** {deviation:.2%}")
        st.write(f"**الحالة:** {'⚠️ غير طبيعي' if abs(deviation) > 0.20 else '✅ طبيعي'}")

    # =================================================================
    # ===== 4. المؤشرات الأساسية (مع إعادة Vanna Gold) =====
    # =================================================================

    metrics = [
        ('openInterest_call_display', 'openInterest_put_display', 'Open Interest', 'Contracts'),
        ('call_gamma', 'put_gamma', 'Gamma Exposure', 'Gamma Exposure'),
        ('call_gamma_gold', 'put_gamma_gold', 'Gamma Gold', 'Gamma Exposure'),
        ('call_delta', 'put_delta', 'Delta Exposure', 'Delta Exposure'),
        ('call_vanna', 'put_vanna', 'Vanna Exposure', 'Vanna Exposure'),
        # ===== إعادة Vanna Gold =====
        ('call_vanna_gold', 'put_vanna_gold', 'Vanna Gold', 'Vanna Exposure'),
        # ============================
        ('call_vega', 'put_vega', 'Vega Exposure', 'Vega Exposure'),
        ('call_theta', 'put_theta', 'Theta Exposure', 'Theta Exposure'),
        ('call_charm', 'put_charm', 'Charm Exposure (x10k)', 'Charm (x10k)'),
        ('call_speed', 'put_speed', 'Speed Exposure (x10k)', 'Speed (x10k)'),
        ('impliedVolatility_call', 'impliedVolatility_put', 'Implied Volatility', 'IV'),
    ]

    any_frozen = False
    
    for call_col, put_col, title, yaxis in metrics:
        x_range = st.session_state.get(f"xrange_{title}", None)
        
        # ===== تمرير المناطق إلى Gamma Gold =====
        if title == "Gamma Gold":
            zero_gamma = zero_gamma_level
            zones_list = zones  # تم إعادة تمرير المناطق إلى Gamma Gold
            gex_flow_val = gex_flow
        else:
            zero_gamma = None
            zones_list = None
            gex_flow_val = None
        
        # ===== إظهار خط Gamma في Vanna Gold =====
        show_gamma = False
        gamma_line = None
        if title == "Vanna Gold":
            show_gamma = True
            gamma_line = df_sorted['call_gamma_gold'].values
        
        fig = plot_metric_single(
            df_sorted, S, call_col, put_col, title, yaxis, 
            x_range=x_range,
            zero_gamma_level=zero_gamma,
            zones=zones_list,
            gex_flow=gex_flow_val,
            show_gamma_line=show_gamma,
            gamma_line_data=gamma_line
        )

        col_plot, col_freeze = st.columns([0.96, 0.04])
        with col_plot:
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{title}")
        with col_freeze:
            st.write("")
            frozen = st.checkbox("🔒", key=f"freeze_{title}", value=st.session_state.get(f"freeze_{title}", False))
            if frozen:
                any_frozen = True

    # =================================================================
    # ===== 5. المؤشرات الإضافية =====
    # =================================================================

    fig_ratio = plot_ratio_line(
        df_sorted, S,
        x_col='strike',
        y_col='gamma_ratio',
        title='Gamma / Open Interest Ratio',
        y_axis='Gamma per Contract',
        line_color='magenta'
    )
    st.plotly_chart(fig_ratio, use_container_width=True)

    df_sorted['net_delta'] = df_sorted['call_delta'] - df_sorted['put_delta']
    df_sorted['cumulative_delta'] = df_sorted['net_delta'].cumsum()

    if "show_cum_delta" not in st.session_state:
        st.session_state.show_cum_delta = False

    col_btn, col_title = st.columns([0.15, 0.85])
    with col_btn:
        label = "🔽 إخفاء" if st.session_state.show_cum_delta else "▶️ إظهار"
        if st.button(label, key="toggle_cum_delta", help="إظهار أو إخفاء مؤشر الدلتا التراكمي"):
            st.session_state.show_cum_delta = not st.session_state.show_cum_delta
            st.rerun()
    with col_title:
        st.write("### 📊 الدلتا التراكمي (Cumulative Delta Exposure)")

    if st.session_state.show_cum_delta:
        fig_cum = plot_cumulative_delta(
            df_sorted, S,
            x_col='strike',
            y_col='cumulative_delta',
            title='Cumulative Delta Exposure',
            y_axis='Cumulative Net Delta',
            line_color='deepskyblue'
        )
        st.plotly_chart(fig_cum, use_container_width=True)
    else:
        st.caption("🔒 المؤشر مخفي. اضغط على زر '▶️ إظهار' لعرضه.")

    # =================================================================
    # ===== 6. Inventory =====
    # =================================================================

    st.divider()
    st.subheader("📋 Options Inventory - Net Contracts")

    df_inventory = df_sorted.copy()
    df_inventory['Net_Contracts'] = df_inventory['openInterest_call'] - df_inventory['openInterest_put']

    fig_inv = go.Figure()

    bought = df_inventory[df_inventory['Net_Contracts'] > 0]
    if not bought.empty:
        fig_inv.add_trace(go.Bar(
            x=bought['strike'],
            y=bought['Net_Contracts'],
            marker_color='limegreen',
            name='BOUGHT',
            text=bought['Net_Contracts'].apply(lambda x: f'{x:.0f}'),
            textposition='outside',
            hovertemplate='Price: %{x}<br>Net Contracts: %{y}<extra></extra>'
        ))

    sold = df_inventory[df_inventory['Net_Contracts'] < 0]
    if not sold.empty:
        fig_inv.add_trace(go.Bar(
            x=sold['strike'],
            y=sold['Net_Contracts'],
            marker_color='crimson',
            name='SOLD',
            text=sold['Net_Contracts'].apply(lambda x: f'{x:.0f}'),
            textposition='outside',
            hovertemplate='Price: %{x}<br>Net Contracts: %{y}<extra></extra>'
        ))

    zero = df_inventory[df_inventory['Net_Contracts'] == 0]
    if not zero.empty:
        fig_inv.add_trace(go.Bar(
            x=zero['strike'],
            y=zero['Net_Contracts'],
            marker_color='gray',
            name='Zero',
            text='0',
            textposition='outside',
            hovertemplate='Price: %{x}<br>Net Contracts: 0<extra></extra>'
        ))

    fig_inv.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
    fig_inv.add_vline(x=S, line_dash="dash", line_color="yellow",
                      annotation_text=f"S = {S:.2f}",
                      annotation_position="top",
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

    fig_inv.update_layout(
        title=f"Net Options Positions (Calls - Puts) - {symbol} - {expiration_date}",
        xaxis_title="Strike Price",
        yaxis_title="Net Contracts",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        barmode='relative',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=600,
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig_inv.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range_inv)
    fig_inv.update_yaxes(gridcolor='gray', zeroline=True, zerolinecolor='white')

    st.plotly_chart(fig_inv, use_container_width=True)

    total_oi_calls = df_inventory['openInterest_call'].sum()
    total_oi_puts = df_inventory['openInterest_put'].sum()
    total_net = total_oi_calls - total_oi_puts

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total OI (Calls)", f"{total_oi_calls:,.0f}")
    with col2:
        st.metric("Total OI (Puts)", f"{total_oi_puts:,.0f}")
    with col3:
        st.metric("Net Contracts Total", f"{total_net:+,.0f}")
    with col4:
        st.metric("Current Price", f"${S:.2f}")

    # =================================================================
    # ===== 7. مؤشر قوة الدفع طه (Gamma Taha) مع Confluence Zones =====
    # =================================================================
    st.divider()
    st.subheader("⚡ قوة الدفع طه (Gamma Taha) + Vanna Exposure + Confluence Zones")

    threshold_taha = settings['taha_confluence_pct']
    max_gamma_abs = df_sorted['net_gamma'].abs().max()
    max_vanna_abs = df_sorted['net_vanna'].abs().max()
    
    taha_zones = []
    for idx, row in df_sorted.iterrows():
        strike = row['strike']
        net_g = row['net_gamma']
        net_v = row['net_vanna']
        
        if max_gamma_abs == 0 or max_vanna_abs == 0:
            continue
        
        gamma_ratio = net_g / max_gamma_abs
        vanna_ratio = net_v / max_vanna_abs
        
        if gamma_ratio > threshold_taha and vanna_ratio > threshold_taha and S > zero_gamma_level:
            taha_zones.append({
                'strike': strike,
                'type': 'squeeze',
                'gamma_ratio': gamma_ratio,
                'vanna_ratio': vanna_ratio,
                'color': 'limegreen',
                'marker': '💥'
            })
        
        if gamma_ratio < -threshold_taha and vanna_ratio < -threshold_taha and S < zero_gamma_level:
            taha_zones.append({
                'strike': strike,
                'type': 'meltdown',
                'gamma_ratio': gamma_ratio,
                'vanna_ratio': vanna_ratio,
                'color': 'red',
                'marker': '⬇️'
            })

    fig_taha = go.Figure()

    fig_taha.add_trace(go.Bar(
        x=df_sorted['strike'],
        y=df_sorted['call_gamma'],
        marker_color='limegreen',
        name='Calls',
        legendgroup='calls'
    ))
    fig_taha.add_trace(go.Bar(
        x=df_sorted['strike'],
        y=df_sorted['put_gamma'],
        marker_color='crimson',
        name='Puts',
        legendgroup='puts'
    ))
    fig_taha.update_layout(barmode='relative')

    fig_taha.add_vline(
        x=S,
        line_dash="dash",
        line_color="white",
        annotation_text=f"S = {S:.1f}",
        annotation_position="top",
        annotation_font=dict(color="white", size=12)
    )

    fig_taha.add_vline(
        x=zero_gamma_level,
        line_dash="dash",
        line_color="white",
        annotation_text="Zero-Gamma",
        annotation_position="bottom",
        annotation_font=dict(color="white", size=10)
    )

    fig_taha.add_trace(go.Scatter(
        x=df_sorted['strike'],
        y=df_sorted['net_vanna'],
        mode='lines',
        line=dict(color='orange', width=2, dash='dash'),
        name='Vanna Exposure'
    ))

    for zone in taha_zones:
        fig_taha.add_vline(
            x=zone['strike'],
            line_dash="dot",
            line_color=zone['color'],
            annotation_text=f"{zone['marker']} {zone['type'].upper()}",
            annotation_position="top",
            annotation_font=dict(color=zone['color'], size=10)
        )

    min_s = df_sorted['strike'].min()
    max_s = df_sorted['strike'].max()
    if S < min_s:
        min_s = S - (max_s - min_s) * 0.15
    elif S > max_s:
        max_s = S + (max_s - min_s) * 0.15
    center = S
    half_range = max(center - min_s, max_s - center) * 1.2
    x_range_taha = (center - half_range, center + half_range)

    fig_taha.update_layout(
        title="⚡ قوة الدفع طه (Gamma Taha) + Vanna Exposure + Confluence Zones",
        yaxis_title="Gamma Exposure",
        xaxis_title="Strike Price",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="white")),
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig_taha.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range_taha)
    fig_taha.update_yaxes(gridcolor='gray')

    st.plotly_chart(fig_taha, use_container_width=True)

    if taha_zones:
        st.divider()
        st.subheader("📍 مناطق التقاء غاما وفانا (Confluence Zones) - خاصة بـ 🧑‍🏫 طه")
        
        squeeze_zones = [z for z in taha_zones if z['type'] == 'squeeze']
        meltdown_zones = [z for z in taha_zones if z['type'] == 'meltdown']
        
        if squeeze_zones:
            st.success(f"💥 Squeeze Zones (صاعد) عند: {', '.join([f'${z['strike']:.2f}' for z in squeeze_zones])}")
        if meltdown_zones:
            st.error(f"⬇️ Meltdown Zones (هابط) عند: {', '.join([f'${z['strike']:.2f}' for z in meltdown_zones])}")
        
        for zone in taha_zones:
            st.caption(
                f"عند ${zone['strike']:.2f}: "
                f"Gamma = {zone['gamma_ratio']:.2%} من Max, "
                f"Vanna = {zone['vanna_ratio']:.2%} من Max"
            )

    # =================================================================
    # ===== 8. تحميل CSV =====
    # =================================================================

    st.divider()
    csv_data_all = df_sorted.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download All Data CSV",
        data=csv_data_all,
        file_name=f'{symbol}_options_{expiration_date}.csv',
        mime='text/csv',
        key='download_csv_single'
    )

    if should_autorefresh():
        st_autorefresh(interval=30 * 1000, key="auto_normal")
    else:
        st.caption("⏸️ التحديث التلقائي متوقف مؤقتاً (خارج ساعات التداول أو قبيل الإغلاق).")

# ========== صفحة المقارنة ==========
def multi_date_page(symbol):
    st.header("Compare Different Expiration Dates")

    with st.sidebar:
        r = st.slider("Risk-free interest rate (r)", 0.0, 0.2, 0.05, 0.005, key="r_multi")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Quick Refresh", key="refresh_multi_quick", width="stretch"):
                st.rerun()
        with col2:
            if st.button("⚡ Force Refresh", key="refresh_multi_force", width="stretch"):
                st.cache_data.clear()
                st.rerun()
        
        ticker_symbol = "^SPX" if symbol == "SPX" else symbol
        ticker_symbol = "^NDX" if symbol == "NDX" else ticker_symbol
        ticker = yf.Ticker(ticker_symbol)
        current_price = ticker.history(period="1d")['Close'].iloc[-1]
        
        status, _ = get_market_status()
        market_status = "🟢 Open" if status == "open" else "🔴 Closed"
        st.metric("Current Price", f"${current_price:.2f}", delta=market_status)
        st.caption(f"🕒 {datetime.datetime.now().strftime('%I:%M:%S %p')}")

    all_exps = ticker.options
    if not all_exps:
        st.error("No expiration dates available.")
        return

    selected_exps = st.multiselect("Select expiration dates (max 5)", all_exps,
                                   default=all_exps[:2] if len(all_exps)>=2 else all_exps,
                                   max_selections=5)

    if not selected_exps:
        st.warning("Please select at least one date.")
        return

    dfs = {}
    S = current_price
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

        dfs[exp] = {
            'strike': K,
            'total_oi': oi_c + oi_p,
            'total_delta': oi_c * delta_c + oi_p * delta_p,
            'total_gamma': (oi_c - oi_p) * gamma_val,
            'total_vanna': (oi_c + oi_p) * vanna_val,
            'total_vega': (oi_c + oi_p) * vega_val,
            'total_theta': oi_c * theta_c + oi_p * theta_p,
            'total_charm': (oi_c * charm_c + oi_p * charm_p) * SCALE,
            'total_speed': (oi_c + oi_p) * speed_val * SCALE,
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
                fig.add_trace(go.Scatter(x=data['strike'], y=data[key],
                                         mode='lines', name=exp))
        
        if all_strikes:
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
        
        fig.add_vline(x=S, line_dash="dash", line_color="white",
                      annotation_text=f"S = {S:.1f}",
                      annotation_position="top",
                      annotation_font=dict(color="white", size=12))
        
        display_title = METRICS_LABELS.get(title, title)
        fig.update_layout(title=display_title, xaxis_title="Strike Price", yaxis_title="Value",
                          font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                          showlegend=True, margin=dict(l=10, r=10, t=40, b=40))
        fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range)
        fig.update_yaxes(gridcolor='gray')
        st.plotly_chart(fig, use_container_width=True)

# ========== التطبيق الرئيسي ==========
def main():
    if "show_visitors" not in st.session_state:
        st.session_state.show_visitors = False

    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_page()
        return

    with st.sidebar:
        st.divider()
        if st.button("🚪 Logout", width="stretch"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()

    col_title, col_selector = st.columns([2, 1])
    with col_title:
        st.title("📊 رادار عادل للخيارات الكمية")
        st.caption(f"👋 مرحباً، {st.session_state.username}!")
    with col_selector:
        symbol = st.selectbox(
            "🔍 اختر الصندوق / المؤشر",
            ["GLD", "SPY", "SPX", "QQQ", "NDX"],
            index=0,
            help="اختر الصندوق المتداول أو المؤشر لتحليل خياراته"
        )
        st.caption(f"تحليل: {symbol}")

    st.divider()

    page = st.sidebar.radio(
        "اختر الصفحة",
        ["تحليل تاريخ واحد", "مقارنة تواريخ متعددة"]
    )

    if page == "تحليل تاريخ واحد":
        single_date_page(symbol)
    else:
        multi_date_page(symbol)

    track_visitors(st.session_state.username)

    if st.session_state.username == "admin":
        st.divider()
        
        col_btn, col_title_bloc = st.columns([0.2, 0.8])
        with col_btn:
            label = "🙈 إخفاء" if st.session_state.show_visitors else "👀 إظهار"
            if st.button(label, width="stretch", help="إظهار أو إخفاء إحصائيات الزوار"):
                st.session_state.show_visitors = not st.session_state.show_visitors
                st.rerun()
        
        with col_title_bloc:
            st.subheader("👥 إحصائيات الزوار (آخر 24 ساعة)")
        
        if st.session_state.show_visitors:
            display_visitor_widget()
        else:
            st.caption("🔒 الجدول مخفي. اضغط على زر '👀 إظهار' لعرضه.")

if __name__ == "__main__":
    main()
