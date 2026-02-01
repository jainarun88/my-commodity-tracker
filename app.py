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
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ⚙️ CONTRACT DATABASE
# ---------------------------------------------------------
CONTRACTS = {
    "GOLD (Standard/10g)": {
        "ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_size": "1 Kg", "type": "GOLD"
    },
    "GOLDM (Mini)": {
        "ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", 
        "lot_size": "100 Grams", "type": "GOLD"
    },
    "GOLDPETAL (1g)": {
        "ticker": "GC=F", "unit_mult": 1, "display_unit": "1 Gram", 
        "lot_size": "1 Gram", "type": "GOLD"
    },
    "SILVER (Standard/1kg)": {
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

selected_contract = st.selectbox("Select Contract:", list(CONTRACTS.keys()))
config = CONTRACTS[selected_contract]
TAX_FACTOR = 1.12 

# ---------------------------------------------------------
# 🔄 DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_data(ticker, multiplier):
    tickers = f"{ticker} INR=X"
    data = yf.download(tickers, period="6mo", interval="1d", progress=False)
    
    df = data['Close'].copy()
    df.columns = ['Global_Price', 'USDINR']
    df = df.ffill().dropna()

    # MCX Formula
    df['MCX_Price'] = (df['Global_Price'] * df['USDINR']) / 31.1035 * multiplier * TAX_FACTOR
    
    return df

def add_indicators(df):
    price = df['MCX_Price']
    
    # 1. RSI (Improved Calculation for Accuracy)
    delta = price.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    # Use Exponential Moving Average (Wilder's Smoothing)
    ema_up = up.ewm(com=13, adjust=False).mean()
    ema_down = down.ewm(com=13, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))

    # 2. Bollinger Bands
    df['SMA_20'] = price.rolling(20).mean()
    df['Std'] = price.rolling(20).std()
    df['Upper'] = df['SMA_20'] + (df['Std']*2)
    df['Lower'] = df['SMA_20'] - (df['Std']*2)

    # 3. EMA & MACD
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
    if st.button('🔄 Refresh Data'):
        st.cache_data.clear()

    with st.spinner(f'Analyzing {selected_contract}...'):
        df = fetch_data(config['ticker'], config['unit_mult'])
        df = add_indicators(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['MCX_Price'] - prev['MCX_Price']
        
        # 1. PRICE DISPLAY
        st.metric(
            label=f"Price (per {config['display_unit']})",
            value=f"₹ {latest['MCX_Price']:,.0f}",
            delta=f"₹ {change:,.0f}"
        )
        
        # 2. TECHNICAL METRICS (Yeh Missing tha!)
        st.write("---")
        c1, c2, c3 = st.columns(3)
        
        # RSI Display
        rsi_val = latest['RSI']
        rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "orange"
        c1.markdown(f"**RSI (14)**")
        c1.markdown(f":{rsi_color}[{rsi_val:.1f}]")
        
        # Trend Display
        trend = "BULLISH 📈" if latest['MCX_Price'] > latest['EMA_50'] else "BEARISH 📉"
        c2.markdown("**Trend**")
        c2.markdown(trend)
        
        # MACD Display
        macd_stat = "POS 🟢" if latest['MACD'] > latest['Signal'] else "NEG 🔴"
        c3.markdown("**MACD**")
        c3.markdown(macd_stat)

        # 3. AI SIGNAL
        st.write("---")
        st.subheader("🤖 AI Signal")
        verdict, color_class, reasons = get_signal(latest)
        st.markdown(f'<p class="big-font {color_class}">{verdict}</p>', unsafe_allow_html=True)
        for r in reasons:
            st.caption(f"• {r}")
            
        # 4. CHART
        st.write("---")
        st.subheader("📉 Chart")
        
        fig, ax1 = plt.subplots(figsize=(8, 4))
        ax1.plot(df.index, df['MCX_Price'], label='Price', color='black')
        ax1.plot(df.index, df['Upper'], color='green', linestyle='--', alpha=0.3)
        ax1.plot(df.index, df['Lower'], color='red', linestyle='--', alpha=0.3)
        ax1.plot(df.index, df['EMA_50'], color='orange', label='EMA 50')
        ax1.legend(loc='upper left', fontsize='small')
        ax1.set_title(f"{selected_contract} Trend")
        ax1.grid(alpha=0.3)
        st.pyplot(fig)

        # Raw Data
        with st.expander("📊 View Data"):
            st.dataframe(df.tail(5)[['MCX_Price', 'RSI', 'USDINR']])

except Exception as e:
    st.error(f"Error: {e}")
