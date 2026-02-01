import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# 📱 PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="Gold Pro Tracker", layout="centered", page_icon="📈")

# Custom CSS for Mobile Styling
st.markdown("""
    <style>
    .big-font { font-size:22px !important; font-weight: bold; }
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; }
    .status-buy { color: #00C853; font-weight: 900; } /* Green */
    .status-sell { color: #D50000; font-weight: 900; } /* Red */
    .status-wait { color: #FF6D00; font-weight: 900; } /* Orange */
    </style>
    """, unsafe_allow_html=True)

# ---------------------------------------------------------
# ⚙️ SETTINGS
# ---------------------------------------------------------
COMMODITY = "GOLD"
PERIOD = "6mo"  # Graph ke liye thoda lamba data
TAX_FACTOR = 1.12

# ---------------------------------------------------------
# 🔄 DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300) # Data 5 min tak save rahega (Faster loading)
def fetch_data():
    # Symbol Selection
    if COMMODITY == "GOLD":
        global_symbol = "GC=F"
        unit_multiplier = 10
    else:
        global_symbol = "SI=F"
        unit_multiplier = 1000 

    # Download
    tickers = f"{global_symbol} INR=X"
    data = yf.download(tickers, period=PERIOD, interval="1d", progress=False)
    
    # Cleaning
    df = data['Close'].copy()
    df.columns = ['Global_Price', 'USDINR']
    df = df.ffill().dropna()

    # MCX Calculation
    df['MCX_Price'] = (df['Global_Price'] * df['USDINR']) / 31.1035 * unit_multiplier * TAX_FACTOR
    
    return df

def add_indicators(df):
    price = df['MCX_Price']
    
    # 1. RSI
    delta = price.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
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

    # RSI Logic
    if row['RSI'] < 30: score += 2; reasons.append("RSI Oversold (Sasta)")
    elif row['RSI'] > 70: score -= 2; reasons.append("RSI Overbought (Mehenga)")
    
    # Bollinger Logic
    if row['MCX_Price'] < row['Lower']: score += 3; reasons.append("Price Crash (Below Band)")
    
    # MACD Logic
    if row['MACD'] > row['Signal']: score += 1
    else: score -= 1

    # Final Verdict
    if score >= 3: return "STRONG BUY", "status-buy", reasons
    elif score >= 1: return "BUY ON DIPS", "status-buy", reasons
    elif score <= -2: return "SELL / AVOID", "status-sell", reasons
    else: return "WAIT & WATCH", "status-wait", reasons

# ---------------------------------------------------------
# 📱 APP UI
# ---------------------------------------------------------
st.title(f"📊 MCX {COMMODITY} Tracker")

if st.button('🔄 Refresh Data'):
    st.cache_data.clear()

try:
    with st.spinner('Analyzing Market...'):
        df = fetch_data()
        df = add_indicators(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        change = latest['MCX_Price'] - prev['MCX_Price']
        
        # --- SECTION 1: PRICE HEADER ---
        st.metric(
            label="Current MCX Price (Theoretical)",
            value=f"₹ {latest['MCX_Price']:,.0f}",
            delta=f"₹ {change:,.0f}"
        )
        
        # --- SECTION 2: AI VERDICT ---
        st.write("---")
        st.subheader("🤖 AI Signal")
        verdict, color_class, reasons = get_signal(latest)
        
        st.markdown(f'<p class="big-font {color_class}">{verdict}</p>', unsafe_allow_html=True)
        for r in reasons:
            st.caption(f"• {r}")
            
        # --- SECTION 3: TECHNICAL METRICS ---
        st.write("---")
        c1, c2, c3 = st.columns(3)
        
        # RSI Color
        rsi_val = latest['RSI']
        rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "orange"
        c1.markdown(f"**RSI (14)**")
        c1.markdown(f":{rsi_color}[{rsi_val:.1f}]")
        
        # Trend
        trend = "BULLISH 📈" if latest['MCX_Price'] > latest['EMA_50'] else "BEARISH 📉"
        c2.markdown("**Trend (EMA)**")
        c2.markdown(f"{trend}")
        
        # MACD
        macd_stat = "POS 🟢" if latest['MACD'] > latest['Signal'] else "NEG 🔴"
        c3.markdown("**MACD**")
        c3.markdown(f"{macd_stat}")

        # --- SECTION 4: CHART ---
        st.write("---")
        st.subheader("📉 Price Action")
        
        # Charting (Matplotlib for reliability)
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
        
        # Price Chart
        ax1.plot(df.index, df['MCX_Price'], label='Price', color='black')
        ax1.plot(df.index, df['Upper'], color='green', linestyle='--', alpha=0.3)
        ax1.plot(df.index, df['Lower'], color='red', linestyle='--', alpha=0.3)
        ax1.fill_between(df.index, df['Upper'], df['Lower'], color='gray', alpha=0.1)
        ax1.plot(df.index, df['EMA_50'], color='orange', label='EMA 50')
        ax1.legend(loc='upper left', fontsize='small')
        ax1.set_title("Price vs Bands")
        ax1.grid(alpha=0.3)
        
        # RSI Chart
        ax2.plot(df.index, df['RSI'], color='blue')
        ax2.axhline(70, color='red', linestyle='--')
        ax2.axhline(30, color='green', linestyle='--')
        ax2.set_title("RSI Indicator")
        ax2.grid(alpha=0.3)
        
        st.pyplot(fig)
        
        with st.expander("Show Raw Data"):
            st.dataframe(df.tail(10)[['MCX_Price', 'RSI', 'MACD', 'Global_Price', 'USDINR']])

except Exception as e:
    st.error(f"Error: {e}")