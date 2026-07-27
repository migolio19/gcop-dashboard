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
import io
import tempfile
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from fpdf import FPDF
from PIL import Image

# ========== إعدادات الصفحة ==========
st.set_page_config(page_title="رادار عادل للخيارات الكمية", layout="wide")

# ========== بيانات اعتماد تسجيل الدخول ==========
CREDENTIALS = {
    "admin": "198200",
    "moha33": "tickmillx33"
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
            .login-container {
                max-width: 400px;
                margin: 5% auto;
                padding: 40px;
                background-color: #1e1e1e;
                border-radius: 15px;
                border: 1px solid #333;
                box-shadow: 0 10px 30px rgba(0,0,0,0.7);
                text-align: center;
            }
            .login-title {
                text-align: center;
                margin-bottom: 30px;
                font-size: 28px;
                font-weight: bold;
                color: #00d4ff;
            }
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
        </style>
    """, unsafe_allow_html=True)

    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            st.markdown('<div class="login-title">🔐 رادار عادل للخيارات الكمية</div>', unsafe_allow_html=True)
            
            username = st.text_input("👤 اسم المستخدم", placeholder="أدخل اسم المستخدم", key="login_username")
            password = st.text_input("🔑 كلمة المرور", placeholder="أدخل كلمة المرور", type="password", key="login_password")
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                login_btn = st.button("🚀 دخول", use_container_width=True)
            
            if login_btn:
                if username in CREDENTIALS and CREDENTIALS[username] == password:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success(f"✅ مرحباً بك، {username}!")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ اسم المستخدم أو كلمة المرور غير صحيحة.")
            
            st.markdown('</div>', unsafe_allow_html=True)

# ========== دالة التحقق من فتح السوق ==========
def is_market_open():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    now_ny = now_utc.astimezone(ny_tz)
    
    if now_ny.weekday() >= 5:
        return False
    
    current_time = now_ny.time()
    open_time = datetime.time(9, 30)
    close_time = datetime.time(16, 0)
    
    return open_time <= current_time <= close_time

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

# ========== جلب البيانات ==========
@st.cache_data(ttl=120)
def fetch_options_data(symbol, expiration_date=None):
    if symbol == "SPX":
        symbol = "^SPX"
    
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

# ========== دوال الرسم ==========
def plot_metric_single(df, S, call_col, put_col, title, y_axis, 
                       call_color='limegreen', put_color='crimson', x_range=None):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df['strike'], y=df[call_col], marker_color=call_color, name='Calls', legendgroup='calls'))
    fig.add_trace(go.Bar(x=df['strike'], y=df[put_col], marker_color=put_color, name='Puts', legendgroup='puts'))
    fig.update_layout(barmode='stack')

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

    fig.update_layout(
        title=title,
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

def plot_cumulative_line(df, S, x_col, y_col, title, y_axis, line_color='deepskyblue'):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df[x_col], y=df[y_col],
        mode='lines', fill='tozeroy', line=dict(color=line_color, width=2),
        name='Net Delta'
    ))
    
    fig.add_vline(x=S, line_dash="dash", line_color="white",
                  annotation_text=f"S = {S:.1f}",
                  annotation_position="top",
                  annotation_font=dict(color="white", size=12))
    
    min_s = df[x_col].min()
    max_s = df[x_col].max()
    if S < min_s:
        min_s = S - (max_s - min_s) * 0.15
    elif S > max_s:
        max_s = S + (max_s - min_s) * 0.15
    center = S
    half_range = max(center - min_s, max_s - center) * 1.2
    x_range = (center - half_range, center + half_range)
    
    fig.update_layout(
        title=title,
        yaxis_title=y_axis,
        xaxis_title="Strike Price",
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig.update_xaxes(gridcolor='gray', range=x_range)
    fig.update_yaxes(gridcolor='gray')
    return fig

# ========== صفحة تاريخ واحد ==========
def single_date_page(symbol):
    # عرض التاريخ تحت العنوان مباشرة
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    st.header("تحليل تاريخ انتهاء واحد")
    st.caption(f"📅 {today}")

    current_price, expiration_date, df, T = fetch_options_data(symbol)
    if df is None:
        st.error(f"لا توجد بيانات خيارات للرمز {symbol}.")
        return

    S = current_price
    q = 0.0

    with st.sidebar:
        st.markdown("## ⚙️ الإعدادات")
        r = st.slider("سعر الفائدة الخالي من المخاطر (r)", 0.0, 0.2, 0.05, 0.005)
        
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
            market_status = "🟢 مفتوح" if is_market_open() else "🔴 مغلق"
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
    df_sorted['put_gamma'] = oi_p * gamma_val
    df_sorted['call_vanna'] = oi_c * vanna_val
    df_sorted['put_vanna'] = oi_p * vanna_val
    df_sorted['call_vega'] = oi_c * vega_val
    df_sorted['put_vega'] = oi_p * vega_val
    df_sorted['call_theta'] = oi_c * theta_c
    df_sorted['put_theta'] = oi_p * theta_p
    df_sorted['call_charm'] = oi_c * charm_c * SCALE
    df_sorted['put_charm'] = oi_p * charm_p * SCALE
    df_sorted['call_speed'] = oi_c * speed_val * SCALE
    df_sorted['put_speed'] = oi_p * speed_val * SCALE

    df_sorted['total_gamma'] = df_sorted['call_gamma'] + df_sorted['put_gamma']
    df_sorted['total_oi'] = df_sorted['openInterest_call'] + df_sorted['openInterest_put']
    df_sorted['gamma_ratio'] = df_sorted['total_gamma'] / (df_sorted['total_oi'] + 1)

    metrics = [
        ('openInterest_call', 'openInterest_put', 'Open Interest', 'Contracts'),
        ('call_gamma', 'put_gamma', 'Gamma Exposure', 'Gamma Exposure'),
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
        fig = plot_metric_single(df_sorted, S, call_col, put_col, title, yaxis, 
                                 x_range=x_range)

        col_plot, col_freeze = st.columns([0.96, 0.04])
        with col_plot:
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{title}")
        with col_freeze:
            st.write("")
            frozen = st.checkbox("🔒", key=f"freeze_{title}", value=st.session_state.get(f"freeze_{title}", False))
            if frozen:
                any_frozen = True

    # ---- الدلتا التراكمي ----
    df_sorted['net_delta'] = df_sorted['call_delta'] - df_sorted['put_delta']
    df_sorted['cumulative_delta'] = df_sorted['net_delta'].cumsum()

    fig_cum = plot_cumulative_line(
        df_sorted, S,
        x_col='strike',
        y_col='cumulative_delta',
        title='Cumulative Delta Exposure',
        y_axis='Cumulative Net Delta',
        line_color='deepskyblue'
    )
    st.plotly_chart(fig_cum, use_container_width=True, key="chart_cumulative_delta")

    # ---- نسبة Gamma/Open Interest ----
    fig_ratio = go.Figure()
    fig_ratio.add_trace(go.Scatter(
        x=df_sorted['strike'], 
        y=df_sorted['gamma_ratio'],
        mode='lines+markers', 
        line=dict(color='magenta', width=2),
        marker=dict(size=6),
        name='Gamma / OI Ratio'
    ))
    
    fig_ratio.add_vline(x=S, line_dash="dash", line_color="white",
                        annotation_text=f"S = {S:.1f}",
                        annotation_position="top",
                        annotation_font=dict(color="white", size=12))
    
    min_s = df_sorted['strike'].min()
    max_s = df_sorted['strike'].max()
    if S < min_s:
        min_s = S - (max_s - min_s) * 0.15
    elif S > max_s:
        max_s = S + (max_s - min_s) * 0.15
    center = S
    half_range = max(center - min_s, max_s - center) * 1.2
    x_range_ratio = (center - half_range, center + half_range)
    
    fig_ratio.update_layout(
        title='Gamma / Open Interest Ratio',
        yaxis_title='Gamma per Contract',
        xaxis_title='Strike Price',
        font=dict(color="white"),
        plot_bgcolor="#111",
        paper_bgcolor="#222",
        hovermode="x unified",
        margin=dict(l=10, r=10, t=40, b=40)
    )
    fig_ratio.update_xaxes(gridcolor='gray', range=x_range_ratio)
    fig_ratio.update_yaxes(gridcolor='gray')
    st.plotly_chart(fig_ratio, use_container_width=True)

    # ========== إضافة Inventory ==========
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

    # إحصائيات سريعة
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

    # زر تحميل CSV العام
    st.divider()
    csv_data_all = df_sorted.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download All Data CSV",
        data=csv_data_all,
        file_name=f'{symbol}_options_{expiration_date}.csv',
        mime='text/csv',
        key='download_csv_single'
    )

    # ===== التحديث التلقائي =====
    if any_frozen:
        st_autorefresh(interval=0, key="auto_frozen")
    else:
        st_autorefresh(interval=30 * 1000, key="auto_normal")

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
        ticker = yf.Ticker(ticker_symbol)
        current_price = ticker.history(period="1d")['Close'].iloc[-1]
        
        market_status = "🟢 Open" if is_market_open() else "🔴 Closed"
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
            'total_gamma': (oi_c + oi_p) * gamma_val,
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
        
        fig.update_layout(title=title, xaxis_title="Strike Price", yaxis_title="Value",
                          font=dict(color="white"), plot_bgcolor="#111", paper_bgcolor="#222",
                          showlegend=True, margin=dict(l=10, r=10, t=40, b=40))
        fig.update_xaxes(gridcolor='gray', rangeslider=dict(visible=True), range=x_range)
        fig.update_yaxes(gridcolor='gray')
        st.plotly_chart(fig, use_container_width=True)

# ========== التطبيق الرئيسي (مع القائمة المنسدلة) ==========
def main():
    if "show_visitors" not in st.session_state:
        st.session_state.show_visitors = True

    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_page()
        return

    with st.sidebar:
        st.divider()
        if st.button("🚪 Logout", width="stretch"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.rerun()

    # ===== إعادة القائمة المنسدلة =====
    col_title, col_selector = st.columns([2, 1])
    with col_title:
        st.title("📊 رادار عادل للخيارات الكمية")
        st.caption(f"👋 مرحباً، {st.session_state.username}!")
    with col_selector:
        symbol = st.selectbox(
            "🔍 اختر الصندوق / المؤشر",
            ["GLD", "SPY", "SPX", "QQQ"],
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

    # ===== عرض البلوجن =====
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
            st.caption("🔒 تم إخفاء الجدول. اضغط على زر '👀 إظهار' لإعادة عرضه.")

if __name__ == "__main__":
    main()