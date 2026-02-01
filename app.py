import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------
# 📱 PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="Zerodha MCX Tracker", layout="wide", page_icon="📈")

# Custom CSS
st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .margin-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border: 1px solid #4caf50; }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ⚙️ CONTRACT DATABASE
# ---------------------------------------------------------
CONTRACTS = {
    "GOLDTEN (Standard)": {"ticker": "XAUUSD=X", "unit_mult": 10, "display_unit": "10 Grams", "lot_qty": 1000, "margin_pct": 0.11, "type": "GOLD"},
    "GOLDM (Mini)":       {"ticker": "XAUUSD=X", "unit_mult": 10, "display_unit": "10 Grams", "lot_qty": 100,  "margin_pct": 0.11, "type": "GOLD"},
    "GOLDPETAL (1g)":     {"ticker": "XAUUSD=X", "unit_mult": 1,  "display_unit": "1 Gram",   "lot_qty": 1,    "margin_pct": 0.11, "type": "GOLD"},
    "GOLDGUINEA (8g)":    {"ticker": "XAUUSD=X", "unit_mult": 8,  "display_unit": "8 Grams",  "lot_qty": 8,    "margin_pct": 0.11, "type": "GOLD"},
    "SILVER (Standard)":  {"ticker": "XAGUSD=X", "unit_mult": 1000,"display_unit": "1 Kg",    "lot_qty": 30,   "margin_pct": 0.13, "type": "SILVER"},
    "SILVERM (Mini)":     {"ticker": "XAGUSD=X", "unit_mult": 1000,"display_unit": "1 Kg",    "lot_qty": 5,    "margin_pct": 0.13, "type": "SILVER"},
    "SILVERMIC (Micro)":  {"ticker": "XAGUSD=X", "unit_mult": 1000,"display_unit": "1 Kg",    "lot_qty": 1,    "margin_pct": 0.13, "type": "SILVER"}
}

# ---------------------------------------------------------
# 🎛️ SIDEBAR SETTINGS (With Calibration Slider)
# ---------------------------------------------------------
st.sidebar.title("⚙️ Calibration")
selected_contract = st.sidebar.selectbox("Select Contract:", list(CONTRACTS.keys()))
config = CONTRACTS[selected_contract]

# --- NEW: DUTY SLIDER ---
st.sidebar.markdown("---")
st.sidebar.subheader("💰 Price Correction")
st.sidebar.info("Use this slider to match price with Zerodha (Adjusting for Duty/Premium).")

# Default 6.5% rakha hai (New Duty Structure ke hisaab se)
tax_input = st.sidebar.slider("Import Duty & Premium (%)", min_value=0.0, max_value=15.0, value=6.0, step=0.1)
TAX_FACTOR = 1 + (tax_input / 100)

st.sidebar.markdown("---")
st.sidebar.subheader("Timeframe")
period = st.sidebar.select_slider("Data Period", options=['1mo', '3mo', '6mo', '1y'], value='6mo')
interval = st.sidebar.selectbox("Interval", ['1d', '1wk', '1mo'], index=0)

# ---------------------------------------------------------
# 🔄 ROBUST DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_data(ticker, multiplier, p, i, tax_factor):
    try:
        # 1. Download Spot & Currency
        df_asset = yf.download(ticker, period=p, interval=i, progress=False)
        
        # Fallback Logic
        if df_asset.empty:
            fallback = "GC=F" if "XAU" in ticker else "SI=F"
            df_asset = yf.download(fallback, period=p, interval=i, progress=False)

        df_currency = yf.download("INR=X", period=p, interval=i, progress=False)

        if df_asset.empty or df_currency.empty: return pd.DataFrame()

        # 2. Extract Close
        def get_close(df, symbol):
            if isinstance(df.columns, pd.MultiIndex):
                if symbol in df.columns.get_level_values(1): return df['Close'][symbol]
                else: return df['Close'].iloc[:, 0]
            return df['Close']

        price_asset = get_close(df_asset, ticker)
        price_currency = get_close(df_currency, "INR=X")

        # 3. Timezone Fix
        if price_asset.index.tz is not None: price_asset.index = price_asset.index.tz_localize(None)
        if price_currency.index.tz is not None: price_currency.index = price_currency.index.tz_localize(None)

        # 4. Merge & Fill
        df = pd.concat([price_asset, price_currency], axis=1)
        df.columns = ['Global_Price', 'USDINR']
        df = df.ffill().dropna()

        # 5. Calculation with Dynamic Tax Factor
        conv_factor = (df['USDINR'] / 31.1035) * multiplier * tax_factor
        df['Close'] = df['Global_Price'] * conv_factor
        
        return df

    except Exception as e:
        return pd.DataFrame()

def add_technicals(df):
    price = df['Close']
    delta = price.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    df['EMA_20'] = price.ewm(span=20).mean()
    df['EMA_50'] = price.ewm(span=50).mean()
    df['SMA_20'] = price.rolling(20).mean()
    df['Std'] = price.rolling(20).std()
    df['Upper'] = df['SMA_20'] + (df['Std']*2)
    df['Lower'] = df['SMA_20'] - (df['Std']*2)
    df['Peak'] = price.cummax()
    df['Drawdown_Pct'] = ((price - df['Peak']) / df['Peak']) * 100
    return df

def calculate_zerodha_margin(price_per_unit):
    display_unit_qty = 1 
    if "10 Grams" in config['display_unit']: display_unit_qty = 10
    elif "1 Gram" in config['display_unit']: display_unit_qty = 1
    elif "8 Grams" in config['display_unit']: display_unit_qty = 8
    elif "1 Kg" in config['display_unit']: display_unit_qty = 1000 
    
    if config['type'] == 'GOLD': units_in_lot = config['lot_qty'] / display_unit_qty
    else: units_in_lot = config['lot_qty'] 
        
    total_val = price_per_unit * units_in_lot
    return total_val, total_val * config['margin_pct']

# ---------------------------------------------------------
# 🖥️ MAIN UI
# ---------------------------------------------------------
st.title(f"📊 Zerodha {selected_contract} Analysis")

if st.sidebar.button('🔄 Refresh Data'):
    st.cache_data.clear()

try:
    with st.spinner('Calibrating Prices...'):
        # Pass TAX_FACTOR to function
        df = fetch_data(config['ticker'], config['unit_mult'], period, interval, TAX_FACTOR)
        
        if df.empty:
            st.warning("⚠️ No Data. Market closed or Ticker issue.")
            st.stop()
            
        df = add_technicals(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['Close'] - prev['Close']
        
        # METRICS
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(f"Price ({config['display_unit']})", f"₹ {latest['Close']:,.0f}", f"{change:,.0f}", delta_color="inverse")
        
        rsi_val = latest['RSI']
        rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "off"
        c2.metric("RSI (14)", f"{rsi_val:.1f}" if not pd.isna(rsi_val) else "N/A")
        
        contract_val, margin_val = calculate_zerodha_margin(latest['Close'])
        c3.metric("Est. Margin (1 Lot)", f"₹ {margin_val/100000:.2f} L")
        
        c4.metric("Fall from Top", f"{latest['Drawdown_Pct']:.2f}%", delta_color="off")

        st.markdown("---")

        # CHARTS
        tab1, tab2 = st.tabs(["🕯️ Chart", "📋 Info"])
        
        with tab1:
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], name='Price', line=dict(color='black')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], name='EMA 50', line=dict(color='orange')), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI', line=dict(color='purple')), row=2, col=1)
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)
            fig.update_layout(height=600, xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
        with tab2:
            st.info(f"Current Import Duty Setting: **{tax_input}%** (Adjust slider in sidebar to match Zerodha price).")

except Exception as e:
    st.error(f"Error: {e}")
