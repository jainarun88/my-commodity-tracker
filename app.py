import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# 📱 PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="MCX All-in-One Tracker", layout="centered", page_icon="🏦")

# Custom CSS
st.markdown("""
    <style>
    .big-font { font-size:22px !important; font-weight: bold; }
    .status-buy { color: #00C853; font-weight: 900; }
    .status-sell { color: #D50000; font-weight: 900; }
    .status-wait { color: #FF6D00; font-weight: 900; }
    .contract-info { font-size: 14px; color: #555; background-color: #f0f2f6; padding: 10px; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ⚙️ CONTRACT DETAILS DATABASE
# ---------------------------------------------------------
# Yahan humne har contract ki details define ki hain
CONTRACTS = {
    "GOLD (Standard/10g)": {
        "ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_size": "1 Kg", "type": "GOLD"
    },
    "GOLDM (Mini)": {
        "ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_size": "100 Grams", "type": "GOLD"
    },
    "GOLDGUINEA": {
        "ticker": "GC=F", "unit_mult": 8, "display_unit": "8 Grams", 
        "lot_size": "8 Grams", "type": "GOLD"
    },
    "GOLDPETAL": {
        "ticker": "GC=F", "unit_mult": 1, "display_unit": "1 Gram", 
        "lot_size": "1 Gram", "type": "GOLD"
    },
    "SILVER (Standard)": {
        "ticker": "SI=F", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_size": "30 Kg", "type": "SILVER"
    },
    "SILVERM (Mini)": {
        "ticker": "SI=F", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_size": "5 Kg", "type": "SILVER"
    },
    "SILVERMIC (Micro)": {
        "ticker": "SI=F", "unit_mult": 1000, "display_unit": "1 Kg", 
        "lot_size": "1 Kg", "type": "SILVER"
    }
}

# ---------------------------------------------------------
# 🎛️ SIDEBAR / SELECTION
# ---------------------------------------------------------
st.title("🏦 MCX Contract Tracker")

# Dropdown for Selection
selected_contract = st.selectbox(
    "Select Contract:", 
    list(CONTRACTS.keys())
)

# Get Details of Selected Contract
config = CONTRACTS[selected_contract]
TAX_FACTOR = 1.12 # 12% Import Duty + Premium estimate

# ---------------------------------------------------------
# 🔄 DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_data(ticker, multiplier):
    # Download Global Price + USDINR
    tickers = f"{ticker} INR=X"
    data = yf.download(tickers, period="6mo", interval="1d", progress=False)
    
    # Cleaning
    df = data['Close'].copy()
    df.columns = ['Global_Price', 'USDINR']
    df = df.ffill().dropna()

    # MCX Calculation Formula:
    # (Global Price / 31.1035) * Multiplier * Tax
    # 31.1035 is conversion factor for Troy Ounce to Grams
    troy_ounce_factor = 31.1035
    
    df['MCX_Price'] = (df['Global_Price'] * df['USDINR']) / troy_ounce_factor * multiplier * TAX_FACTOR
    
    return df

def add_indicators(df):
    price = df['MCX_Price']
    
    # RSI
    delta = price.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['SMA_20'] = price.rolling(20).mean()
    df['Std'] = price.rolling(20).std()
    df['Upper'] = df['SMA_20'] + (df['Std']*2)
    df['Lower'] = df['SMA_20'] - (df['Std']*2)

    # EMA & MACD
    df['EMA_50'] = price.ewm(span=50).mean()
    df['MACD'] = price.ewm(span=12).mean() - price.ewm(span=26).mean()
    df['Signal'] = df['MACD'].ewm(span=9).mean()
    
    return df

# ---------------------------------------------------------
# 🧠 AI LOGIC
# ---------------------------------------------------------
def get_signal(row):
    score = 0
    reasons = []

    if row['RSI'] < 30: score += 2; reasons.append("RSI Oversold (Cheap)")
    elif row['RSI'] > 70: score -= 2; reasons.append("RSI Overbought (Expensive)")
    
    if row['MCX_Price'] < row['Lower']: score += 3; reasons.append("Price Crash (Below Band)")
    
    if row['MACD'] > row['Signal']: score += 1
    else: score -= 1

    if score >= 3: return "STRONG BUY", "status-buy", reasons
    elif score >= 1: return "BUY ON DIPS", "status-buy", reasons
    elif score <= -2: return "SELL / AVOID", "status-sell", reasons
    else: return "WAIT & WATCH", "status-wait", reasons

# ---------------------------------------------------------
# 📱 APP UI
# ---------------------------------------------------------
try:
    # Display Contract Info
    st.info(f"""
    **Contract Details:** {selected_contract}
    • **Price Unit:** Per {config['display_unit']} (Displayed below)
    • **Lot Size:** {config['lot_size']}
    """)

    with st.spinner(f'Fetching data for {selected_contract}...'):
        df = fetch_data(config['ticker'], config['unit_mult'])
        df = add_indicators(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['MCX_Price'] - prev['MCX_Price']
        
        # --- PRICE HEADER ---
        st.metric(
            label=f"Price (per {config['display_unit']})",
            value=f"₹ {latest['MCX_Price']:,.0f}",
            delta=f"₹ {change:,.0f}"
        )
        
        # --- AI SIGNAL ---
        st.write("---")
        st.subheader("🤖 AI Signal")
        verdict, color_class, reasons = get_signal(latest)
        st.markdown(f'<p class="big-font {color_class}">{verdict}</p>', unsafe_allow_html=True)
        for r in reasons:
            st.caption(f"• {r}")
            
        # --- CHART ---
        st.write("---")
        st.subheader("📉 Price Trend")
        
        fig, ax1 = plt.subplots(figsize=(8, 4))
        ax1.plot(df.index, df['MCX_Price'], label='Price', color='black')
        ax1.plot(df.index, df['Upper'], color='green', linestyle='--', alpha=0.3)
        ax1.plot(df.index, df['Lower'], color='red', linestyle='--', alpha=0.3)
        ax1.plot(df.index, df['EMA_50'], color='orange', label='EMA 50')
        ax1.legend(loc='upper left', fontsize='small')
        ax1.set_title(f"{selected_contract} Price vs Bands")
        ax1.grid(alpha=0.3)
        st.pyplot(fig)

        # Raw Data Option
        with st.expander("📊 View Raw Data"):
            st.dataframe(df.tail(10)[['MCX_Price', 'RSI', 'USDINR']])

except Exception as e:
    st.error(f"Error: {e}")
