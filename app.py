import streamlit as st
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt

# ---------------------------------------------------------
# 📱 PAGE CONFIGURATION
# ---------------------------------------------------------
st.set_page_config(page_title="MCX Pro Tracker", layout="centered", page_icon="🏦")

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
    "GOLDTEN (Standard)": {"ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", "type": "GOLD"},
    "GOLDM (Mini)":       {"ticker": "GC=F", "unit_mult": 10, "display_unit": "10 Grams", "type": "GOLD"},
    "GOLDPETAL (1g)":     {"ticker": "GC=F", "unit_mult": 1,  "display_unit": "1 Gram",   "type": "GOLD"},
    "GOLDGUINEA (8g)":    {"ticker": "GC=F", "unit_mult": 8,  "display_unit": "8 Grams",  "type": "GOLD"},
    "SILVER (Standard)":  {"ticker": "SI=F", "unit_mult": 1000,"display_unit": "1 Kg",    "type": "SILVER"},
    "SILVERM (Mini)":     {"ticker": "SI=F", "unit_mult": 1000,"display_unit": "1 Kg",    "type": "SILVER"},
    "SILVERMIC (Micro)":  {"ticker": "SI=F", "unit_mult": 1000,"display_unit": "1 Kg",    "type": "SILVER"}
}

# ---------------------------------------------------------
# 🎛️ SIDEBAR CONTROLS (NEW!)
# ---------------------------------------------------------
st.sidebar.title("⚙️ Settings")

# 1. Select Contract
selected_contract = st.sidebar.selectbox("Select Contract:", list(CONTRACTS.keys()))

# 2. Select Period (Time Duration)
period_options = ['1mo', '3mo', '6mo', '1y', '2y', '5y', 'max']
selected_period = st.sidebar.selectbox("Select Period (Duration):", period_options, index=2) # Default '6mo'

# 3. Select Interval (Candle Size)
interval_options = ['1d', '5d', '1wk', '1mo']
selected_interval = st.sidebar.selectbox("Select Interval (Candle):", interval_options, index=0) # Default '1d'

config = CONTRACTS[selected_contract]
TAX_FACTOR = 1.12 

# ---------------------------------------------------------
# 🔄 DATA ENGINE
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_data(ticker, multiplier, period, interval):
    tickers = f"{ticker} INR=X"
    # User ke selected Period aur Interval ka use yahan ho raha hai
    data = yf.download(tickers, period=period, interval=interval, progress=False)
    
    df = data['Close'].copy()
    df.columns = ['Global_Price', 'USDINR']
    df = df.ffill().dropna()

    df['MCX_Price'] = (df['Global_Price'] * df['USDINR']) / 31.1035 * multiplier * TAX_FACTOR
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

    # Check agar data NaN hai (kam data ki wajah se)
    if pd.isna(row['RSI']): return "INSUFFICIENT DATA", "status-wait", ["Need more data duration"]

    if row['RSI'] < 30: score += 2; reasons.append("RSI Oversold (Cheap)")
    elif row['RSI'] > 70: score -= 2; reasons.append("RSI Overbought (Expensive)")
    
    if not pd.isna(row['Lower']) and row['MCX_Price'] < row['Lower']: score += 3; reasons.append("Price Crash (Below Band)")
    
    if row['MACD'] > row['Signal']: score += 1
    else: score -= 1

    if score >= 3: return "STRONG BUY", "status-buy", reasons
    elif score >= 1: return "BUY ON DIPS", "status-buy", reasons
    elif score <= -2: return "SELL / AVOID", "status-sell", reasons
    else: return "WAIT & WATCH", "status-wait", reasons

# ---------------------------------------------------------
# 📱 APP UI
# ---------------------------------------------------------
st.title(f"🏦 MCX Pro Tracker")
st.caption(f"Tracking: {selected_contract} | Period: {selected_period}")

try:
    if st.button('🔄 Refresh Data'):
        st.cache_data.clear()

    with st.spinner(f'Fetching Data ({selected_period})...'):
        # Pass user selections to function
        df = fetch_data(config['ticker'], config['unit_mult'], selected_period, selected_interval)
        df = add_indicators(df)
        
        if len(df) < 5:
            st.error("Not enough data to calculate indicators. Please increase the Period.")
        else:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            change = latest['MCX_Price'] - prev['MCX_Price']
            
            # 1. PRICE DISPLAY (UPDATED LOGIC)
            st.metric(
                label=f"Price (per {config['display_unit']})",
                value=f"₹ {latest['MCX_Price']:,.0f}",
                delta=f"{change:,.0f}",
                delta_color="inverse"
            )
            
            # 2. METRICS
            st.write("---")
            c1, c2, c3 = st.columns(3)
            
            # Handle NaN for short periods
            rsi_val = latest['RSI']
            if pd.isna(rsi_val):
                c1.metric("RSI", "N/A")
            else:
                rsi_color = "red" if rsi_val > 70 else "green" if rsi_val < 30 else "orange"
                c1.markdown(f"**RSI (14)**")
                c1.markdown(f":{rsi_color}[{rsi_val:.1f}]")
            
            trend = "N/A"
            if not pd.isna(latest['EMA_50']):
                trend = "BULLISH 📈" if latest['MCX_Price'] > latest['EMA_50'] else "BEARISH 📉"
            c2.markdown("**Trend**")
            c2.markdown(trend)
            
            macd_stat = "POS 🟢" if latest['MACD'] > latest['Signal'] else "NEG 🔴"
            c3.markdown("**MACD**")
            c3.markdown(macd_stat)

            # 3. SIGNAL
            st.write("---")
            st.subheader("🤖 AI Signal")
            verdict, color_class, reasons = get_signal(latest)
            st.markdown(f'<p class="big-font {color_class}">{verdict}</p>', unsafe_allow_html=True)
            for r in reasons:
                st.caption(f"• {r}")
                
            # 4. CHART
            st.write("---")
            st.subheader("📉 Technical Charts")
            
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
            
            ax1.plot(df.index, df['MCX_Price'], label='Price', color='black')
            ax1.plot(df.index, df['Upper'], color='green', linestyle='--', alpha=0.3)
            ax1.plot(df.index, df['Lower'], color='red', linestyle='--', alpha=0.3)
            ax1.plot(df.index, df['EMA_50'], color='orange', label='EMA 50')
            ax1.set_title(f"{selected_contract} ({selected_period})")
            ax1.legend(loc='upper left', fontsize='small')
            ax1.grid(alpha=0.3)
            
            ax2.plot(df.index, df['RSI'], label='RSI', color='blue')
            ax2.axhline(70, color='red', linestyle='--', alpha=0.5)
            ax2.axhline(30, color='green', linestyle='--', alpha=0.5)
            ax2.set_title("RSI Indicator")
            ax2.set_ylim(0, 100)
            ax2.grid(alpha=0.3)
            
            st.pyplot(fig)
            
            # 5. Warning for short data
            if selected_period in ['1mo'] and selected_interval == '1d':
                st.warning("⚠️ Note: '1mo' data is too short for EMA-50 trend line. Please select '3mo' or more for better accuracy.")

except Exception as e:
    st.error(f"Error: {e}")

