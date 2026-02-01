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
    .loss-card { background-color: #ffebee; padding: 10px; border-radius: 5px; color: #c62828; }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ⚙️ CONTRACT DATABASE (Zerodha Specs)
# ---------------------------------------------------------
# Note: Margins are approx estimates (SPAN + Exposure)
# Gold ~10-12%, Silver ~12-15% of Contract Value
CONTRACTS = {
    "GOLDTEN (Standard)": {
        "ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_qty": 1000, "margin_pct": 0.11, "type": "GOLD" # Lot = 1 Kg (1000g)
    },
    "GOLDM (Mini)": {
        "ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_qty": 100, "margin_pct": 0.11, "type": "GOLD" # Lot = 100g
    },
    "GOLDPETAL (1g)": {
        "ticker": "GC=F", "unit_mult": 1, "display_unit": "1 Gram", 
        "lot_qty": 1, "margin_pct": 0.11, "type": "GOLD" # Lot = 1g
    },
    "GOLDGUINEA (8g)": {
        "ticker": "GC=F", "unit_mult": 8, "display_unit": "8 Grams", 
        "lot_qty": 8, "margin_pct": 0.11, "type": "GOLD" # Lot = 8g
    },
    "SILVER (Standard)": {
        "ticker": "SI=F", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_qty": 30, "margin_pct": 0.13, "type": "SILVER" # Lot = 30 Kg
    },
    "SILVERM (Mini)": {
        "ticker": "SI=F", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_qty": 5, "margin_pct": 0.13, "type": "SILVER" # Lot = 5 Kg
    },
    "SILVERMIC (Micro)": {
        "ticker": "SI=F", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_qty": 1, "margin_pct": 0.13, "type": "SILVER" # Lot = 1 Kg
    }
}

# ---------------------------------------------------------
# 🎛️ SIDEBAR
# ---------------------------------------------------------
st.sidebar.title("⚙️ Setup")
selected_contract = st.sidebar.selectbox("Select Contract:", list(CONTRACTS.keys()))

st.sidebar.markdown("---")
st.sidebar.subheader("Timeframe")
period = st.sidebar.select_slider("Data Period", options=['1mo', '3mo', '6mo', '1y'], value='6mo')
interval = st.sidebar.selectbox("Interval", ['1d', '1wk'], index=0)

config = CONTRACTS[selected_contract]
TAX_FACTOR = 1.12 

# ---------------------------------------------------------
# 🔄 DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_data(ticker, multiplier, p, i):
    tickers = f"{ticker} INR=X"
    data = yf.download(tickers, period=p, interval=i, progress=False)
    
    # Handle Multi-level columns if needed
    if isinstance(data.columns, pd.MultiIndex):
        try:
            df_price = data['Close']
            df_open = data['Open']
            df_high = data['High']
            df_low = data['Low']
        except:
            # Fallback for simple structure
            df_price = data
    else:
        df_price = data['Close']

    # Merge into clean DF
    df = pd.DataFrame()
    df['Global_Price'] = df_price[ticker]
    df['USDINR'] = df_price['INR=X']
    
    # OHLC Data for Candlestick (Approx conversion)
    # Note: We approximate OHLC based on Close conversion factor for simplicity
    conv_factor = (df['USDINR'] / 31.1035) * multiplier * TAX_FACTOR
    
    df['Close'] = df['Global_Price'] * conv_factor
    # For accurate candles, we ideally need OHLC of global, but this is a close approximation for visual trend
    
    df = df.ffill().dropna()
    return df

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

    # Bollinger
    df['SMA_20'] = price.rolling(20).mean()
    df['Std'] = price.rolling(20).std()
    df['Upper'] = df['SMA_20'] + (df['Std']*2)
    df['Lower'] = df['SMA_20'] - (df['Std']*2)
    
    # Drawdown (Top se kitna gira)
    df['Peak'] = price.cummax()
    df['Drawdown_Pct'] = ((price - df['Peak']) / df['Peak']) * 100
    
    return df

# ---------------------------------------------------------
# 🧠 MARGIN CALCULATOR
# ---------------------------------------------------------
def calculate_zerodha_margin(price_per_unit):
    # Logic:
    # 1. Total Contract Value = Price_Per_Gram * Total_Grams_In_Lot
    # 2. Or Price_Per_Unit * Units_In_Lot
    
    # Adjust price to base unit (per gram or per kg)
    # But easier: We know displayed price unit.
    
    # If Display is 10g, and Lot is 1000g (1kg). Factor = 100.
    # If Display is 1kg, and Lot is 30kg. Factor = 30.
    
    display_unit_qty = 1 # default
    if "10 Grams" in config['display_unit']: display_unit_qty = 10
    elif "8 Grams" in config['display_unit']: display_unit_qty = 8
    elif "1 Gram" in config['display_unit']: display_unit_qty = 1
    elif "1 Kg" in config['display_unit']: display_unit_qty = 1000 # converting to grams for base
    
    # Lot Quantity in grams (for Gold) or Kg (for Silver) needs aligning
    # Let's simplify:
    # Value = (Price / Display_Qty) * Lot_Qty_Actual_Units
    
    # Actually, simpler way:
    # Price displayed is X.
    # How many "Display Units" in 1 Lot?
    
    units_in_lot = 1
    if config['type'] == 'GOLD':
        # Gold lot_qty is in grams
        # Display unit is in grams (1, 8, 10)
        units_in_lot = config['lot_qty'] / display_unit_qty
    else:
        # Silver lot_qty is in Kg
        # Display unit is 1 Kg
        units_in_lot = config['lot_qty'] # because display is 1kg
        
    total_contract_value = price_per_unit * units_in_lot
    margin_req = total_contract_value * config['margin_pct']
    
    return total_contract_value, margin_req

# ---------------------------------------------------------
# 🖥️ MAIN UI
# ---------------------------------------------------------
st.title(f"📊 Zerodha {selected_contract} Analysis")

if st.sidebar.button('🔄 Refresh Data'):
    st.cache_data.clear()

try:
    with st.spinner('Calculating Margins & Charts...'):
        df = fetch_data(config['ticker'], config['unit_mult'], period, interval)
        df = add_technicals(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['Close'] - prev['Close']
        
        # --- TOP METRICS ROW ---
        col1, col2, col3, col4 = st.columns(4)
        
        # 1. Price
        col1.metric(
            f"Price ({config['display_unit']})", 
            f"₹ {latest['Close']:,.0f}",
            f"{change:,.0f}", 
            delta_color="inverse"
        )
        
        # 2. RSI
        rsi_val = latest['RSI']
        rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "off"
        col2.metric("RSI (14)", f"{rsi_val:.1f}")
        
        # 3. Zerodha Margin (The New Feature!)
        contract_val, margin_val = calculate_zerodha_margin(latest['Close'])
        col3.metric(
            "Est. Margin (1 Lot)", 
            f"₹ {margin_val/100000:.2f} L",
            help=f"Approx {config['margin_pct']*100}% of Value. Total Contract Value: ₹ {contract_val/100000:.2f} Lakhs"
        )
        
        # 4. Drawdown (Crash)
        dd = latest['Drawdown_Pct']
        col4.metric("Fall from Top", f"{dd:.2f}%", delta_color="off")

        st.markdown("---")

        # --- TABS FOR CHARTS ---
        tab1, tab2, tab3 = st.tabs(["🕯️ Candlestick & EMA", "📉 Drawdown Analysis", "📋 Contract Info"])

        with tab1:
            # INTERACTIVE CANDLESTICK CHART
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.1, row_heights=[0.7, 0.3])

            # Candlestick
            # Note: Using Close for Open/High/Low approximation for visual trend 
            # (since we are converting USD to INR synthetically)
            fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name='Price', line=dict(color='black')), row=1, col=1)
            
            # EMA Lines
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name='EMA 20', line=dict(color='blue', width=1)), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['EMA_50'], name='EMA 50', line=dict(color='orange', width=1)), row=1, col=1)
            
            # Bollinger Bands
            fig.add_trace(go.Scatter(x=df.index, y=df['Upper'], name='Upper BB', line=dict(color='green', dash='dot'), showlegend=False), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['Lower'], name='Lower BB', line=dict(color='red', dash='dot'), showlegend=False), row=1, col=1)

            # RSI Subplot
            fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI', line=dict(color='purple')), row=2, col=1)
            fig.add_hline(y=70, line_dash="dot", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dot", line_color="green", row=2, col=1)

            fig.update_layout(height=600, title_text="Price Trend & Indicators (Interactive)", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            # DRAWDOWN CHART
            st.subheader("⚠️ Crash Analysis")
            st.write("This chart shows how much the price has fallen from its highest point in the selected period.")
            
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(x=df.index, y=df['Drawdown_Pct'], fill='tozeroy', line=dict(color='red'), name='Drawdown %'))
            fig_dd.update_layout(title="Percentage Fall from Peak", yaxis_title="Drawdown %", height=400)
            st.plotly_chart(fig_dd, use_container_width=True)
            
            if dd < -8:
                st.markdown(f'<div class="loss-card">🚨 Current Drawdown is <b>{dd:.2f}%</b>. Historically, corrections >10% are good buying opportunities in Bull Runs.</div>', unsafe_allow_html=True)

        with tab3:
            # CONTRACT DETAILS TABLE
            st.subheader("Zerodha Contract Specs")
            st.markdown(f"""
            | Detail | Value |
            | :--- | :--- |
            | **Contract** | {selected_contract} |
            | **Lot Size** | {config['lot_qty']} units |
            | **Display Unit** | {config['display_unit']} |
            | **Approx Margin** | {config['margin_pct']*100}% |
            | **Total Value (1 Lot)** | ₹ {contract_val:,.0f} |
            """)
            st.info("Note: Margin values are approximate based on standard exchange requirements. Actual margin may vary slightly on Zerodha Kite.")

except Exception as e:
    st.error(f"Error: {e}")
