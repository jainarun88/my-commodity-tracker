import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------
# 📱 PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="Zerodha MCX Tracker", layout="wide", page_icon="📈")

# Custom CSS for Styling
st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .margin-card { background-color: #e8f5e9; padding: 15px; border-radius: 10px; border: 1px solid #4caf50; }
    .loss-card { background-color: #ffebee; padding: 10px; border-radius: 5px; color: #c62828; }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ⚙️ CONTRACT DATABASE (Updated to SPOT Prices)
# ---------------------------------------------------------
# Ticker changed to XAUUSD=X (Spot) to avoid Futures rollover glitches
CONTRACTS = {
    "GOLDTEN (Standard)": {
        "ticker": "XAUUSD=X", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_qty": 1000, "margin_pct": 0.11, "type": "GOLD"
    },
    "GOLDM (Mini)": {
        "ticker": "XAUUSD=X", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_qty": 100, "margin_pct": 0.11, "type": "GOLD"
    },
    "GOLDPETAL (1g)": {
        "ticker": "XAUUSD=X", "unit_mult": 1, "display_unit": "1 Gram", 
        "lot_qty": 1, "margin_pct": 0.11, "type": "GOLD"
    },
    "GOLDGUINEA (8g)": {
        "ticker": "XAUUSD=X", "unit_mult": 8, "display_unit": "8 Grams", 
        "lot_qty": 8, "margin_pct": 0.11, "type": "GOLD"
    },
    "SILVER (Standard)": {
        "ticker": "XAGUSD=X", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_qty": 30, "margin_pct": 0.13, "type": "SILVER"
    },
    "SILVERM (Mini)": {
        "ticker": "XAGUSD=X", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_qty": 5, "margin_pct": 0.13, "type": "SILVER"
    },
    "SILVERMIC (Micro)": {
        "ticker": "XAGUSD=X", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_qty": 1, "margin_pct": 0.13, "type": "SILVER"
    }
}

# ---------------------------------------------------------
# 🎛️ SIDEBAR SETTINGS
# ---------------------------------------------------------
st.sidebar.title("⚙️ Setup")
selected_contract = st.sidebar.selectbox("Select Contract:", list(CONTRACTS.keys()))

st.sidebar.markdown("---")
st.sidebar.subheader("Timeframe")
period = st.sidebar.select_slider("Data Period", options=['1mo', '3mo', '6mo', '1y', '2y', '5y'], value='6mo')
interval = st.sidebar.selectbox("Interval", ['1d', '1wk', '1mo'], index=0)

config = CONTRACTS[selected_contract]
TAX_FACTOR = 1.12 # Import Duty + Premium

# ---------------------------------------------------------
# 🔄 BULLETPROOF DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_data(ticker, multiplier, p, i):
    try:
        # 1. Primary Download (Spot Price)
        df_asset = yf.download(ticker, period=p, interval=i, progress=False)
        
        # Fallback: Agar Spot Price khali aaye, to Futures try karein
        if df_asset.empty:
            fallback_ticker = "GC=F" if "XAU" in ticker else "SI=F"
            # st.toast(f"⚠️ Spot data failed. Switching to Futures ({fallback_ticker})...") 
            df_asset = yf.download(fallback_ticker, period=p, interval=i, progress=False)
            
        df_currency = yf.download("INR=X", period=p, interval=i, progress=False)

        # 2. Check Valid Data
        if df_asset.empty or df_currency.empty:
            return pd.DataFrame()

        # 3. Extract Close Prices (Handle MultiIndex Safely)
        def get_close(df, symbol):
            if isinstance(df.columns, pd.MultiIndex):
                # Try finding symbol in level 1
                if symbol in df.columns.get_level_values(1):
                    return df['Close'][symbol]
                else:
                    return df['Close'].iloc[:, 0] # First column fallback
            return df['Close']

        price_asset = get_close(df_asset, ticker)
        price_currency = get_close(df_currency, "INR=X")

        # 4. TIMEZONE FIX (Sabse Important Step) 🕒
        # Dono ke timezone hata kar plain date banate hain taaki match ho sakein
        if price_asset.index.tz is not None:
            price_asset.index = price_asset.index.tz_localize(None)
        if price_currency.index.tz is not None:
            price_currency.index = price_currency.index.tz_localize(None)

        # 5. Align Data
        df = pd.concat([price_asset, price_currency], axis=1)
        df.columns = ['Global_Price', 'USDINR']
        
        # 6. Smart Filling (Weekend/Holiday Handling)
        df = df.ffill()  # Pehle pichla rate aage copy karo (Friday ka rate Saturday/Sunday ke liye)
        df = df.dropna() # Ab jo sach mein khali hai use hatao

        # 7. Calculation
        conv_factor = (df['USDINR'] / 31.1035) * multiplier * TAX_FACTOR
        df['Close'] = df['Global_Price'] * conv_factor
        
        return df

    except Exception as e:
        st.error(f"Data Fetch Error: {e}")
        return pd.DataFrame()

def add_technicals(df):
    price = df['Close']
    
    # RSI
    delta = price.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # EMA
    df['EMA_20'] = price.ewm(span=20).mean()
    df['EMA_50'] = price.ewm(span=50).mean()

    # Bollinger Bands
    df['SMA_20'] = price.rolling(20).mean()
    df['Std'] = price.rolling(20).std()
    df['Upper'] = df['SMA_20'] + (df['Std']*2)
    df['Lower'] = df['SMA_20'] - (df['Std']*2)
    
    # Drawdown
    df['Peak'] = price.cummax()
    df['Drawdown_Pct'] = ((price - df['Peak']) / df['Peak']) * 100
    
    return df

# ---------------------------------------------------------
# 🧠 MARGIN CALCULATOR
# ---------------------------------------------------------
def calculate_zerodha_margin(price_per_unit):
    # Logic: Total Value = Price * Units in Lot
    # Display Unit adjustment logic
    
    display_unit_qty = 1 
    if "10 Grams" in config['display_unit']: display_unit_qty = 10
    elif "8 Grams" in config['display_unit']: display_unit_qty = 8
    elif "1 Gram" in config['display_unit']: display_unit_qty = 1
    elif "1 Kg" in config['display_unit']: display_unit_qty = 1000 
    
    # Determine how many "Display Units" fit in 1 Lot
    if config['type'] == 'GOLD':
        units_in_lot = config['lot_qty'] / display_unit_qty
    else:
        # For Silver, lot_qty is in Kg, Display is 1Kg. 1:1 ratio logic.
        units_in_lot = config['lot_qty'] 
        
    total_contract_value = price_per_unit * units_in_lot
    margin_req = total_contract_value * config['margin_pct']
    
    return total_contract_value, margin_req

# ---------------------------------------------------------
# 🖥️ MAIN DASHBOARD UI
# ---------------------------------------------------------
st.title(f"📊 Zerodha {selected_contract} Analysis")

if st.sidebar.button('🔄 Refresh Data'):
    st.cache_data.clear()

try:
    with st.spinner('Fetching Live Data...'):
        df = fetch_data(config['ticker'], config['unit_mult'], period, interval)
        
        # --- CRITICAL CHECK: If data empty, stop here ---
        if df.empty:
            st.warning("⚠️ No Data Found. Market might be closed or Ticker issue. Try changing Period.")
            st.stop()
            
        df = add_technicals(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['Close'] - prev['Close']
        
        # --- METRICS ROW ---
        col1, col2, col3, col4 = st.columns(4)
        
        # 1. Price
        col1.metric(
            f"Price ({config['display_unit']})", 
            f"₹ {latest['Close']:,.0f}",
            f"{change:,.0f}", 
            delta_color="inverse" # Green if drops (Buy opportunity)
        )
        
        # 2. RSI
        rsi_val = latest['RSI']
        if pd.isna(rsi_val):
            col2.metric("RSI (14)", "N/A")
        else:
            rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "off"
            col2.metric("RSI (14)", f"{rsi_val:.1f}")
        
        # 3. Zerodha Margin
        contract_val, margin_val = calculate_zerodha_margin(latest['Close'])
        col3.metric(
            "Est. Margin (1 Lot)", 
            f"₹ {margin_val/100000:.2f} L",
            help=f"Approx {config['margin_pct']*100}% Margin. Total Value: ₹ {contract_val/100000:.2f} L"
        )
        
        # 4. Drawdown
        dd = latest['Drawdown_Pct']
        col4.metric("Fall from Top", f"{dd:.2f}%", delta_color="off")

        st.markdown("---")

        # --- CHARTS TABS ---
        tab1, tab2, tab3 = st.tabs(["🕯️ Interactive Chart", "📉 Drawdown", "📋 Info"])

        with tab1:
            # PLOTLY CHART
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.1, row_heights=[0.7, 0.3])

            # Price Line (Simulated Candle using Line for clean look on calc data)
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name='Price', line=dict(color='black')), row=1, col=1)
            
            # Indicators
            if not df['EMA_20'].isnull().all():
                fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name='EMA 20', line=dict(color='blue', width=1)), row=1, col=1)
                fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], name='EMA 50', line=dict(color='orange', width=1)), row=1, col=1)
            
            # Bollinger Bands
            fig.add_trace(go.Scatter(x=df.index, y=df['Upper'], name='Upper BB', line=dict(color='green', dash='dot'), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Lower'], name='Lower BB', line=dict(color='red', dash='dot'), showlegend=False), row=1, col=1)

            # RSI
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI', line=dict(color='purple')), row=2, col=1)
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)

            fig.update_layout(height=600, title_text="Price Action & Indicators", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("⚠️ Market Crash Monitor")
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(x=df.index, y=df['Drawdown_Pct'], fill='tozeroy', line=dict(color='red'), name='Drawdown %'))
            fig_dd.update_layout(title="Percentage Fall from Peak", yaxis_title="Drawdown %", height=400)
            st.plotly_chart(fig_dd, use_container_width=True)

        with tab3:
            st.subheader("Contract Specifications")
            st.markdown(f"""
            | Detail | Value |
            | :--- | :--- |
            | **Contract** | {selected_contract} |
            | **Lot Size** | {config['lot_qty']} units |
            | **Display Unit** | {config['display_unit']} |
            | **Margin Req** | ~{config['margin_pct']*100}% |
            | **Total Value** | ₹ {contract_val:,.0f} |
            """)

except Exception as e:
    st.error(f"Application Error: {e}")

