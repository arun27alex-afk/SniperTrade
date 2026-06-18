import plotly.graph_objects as go
import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel
import datetime

# ==========================================
# ⚠️ UPDATE YOUR FYERS API DETAILS HERE ⚠️
# ==========================================
CLIENT_ID = "BT8FRQLN19-200"       # Enter your Client ID here
SECRET_KEY = "0ivLeQN8vdI2VyKA"         # Enter your Secret Key here
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/ " # Enter your Streamlit App URL here
# ==========================================

app_id = CLIENT_ID[:-4]

st.set_page_config(page_title="Sniper Trade App", page_icon="🎯", layout="wide")

# --- 📌 Sidebar Menu (Market Snapshot) ---
with st.sidebar:
    st.header("📈 Market Snapshot")
    st.markdown("---")
    st.metric(label="NIFTY 50 (Spot)", value="24,150.00", delta="120.50")
    st.metric(label="BANKNIFTY", value="51,200.00", delta="-45.00")
    st.markdown("---")
    st.info("💡 Note: Live Nifty options data will be connected in the next step.")

st.title("🎯 Sniper Trade App (Auto-Login & Pro Signals)")
st.markdown("---")

# --- Session State ---
if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None

# --- Token Capture (Auto-Redirect) ---
query_params = st.query_params
if "auth_code" in query_params:
    auth_code = query_params["auth_code"]
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, secret_key=SECRET_KEY, 
        redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code"
    )
    session.set_token(auth_code)
    response = session.generate_token()
    if response.get("s") == "ok":
        st.session_state['access_token'] = response["access_token"]
        st.success("✅ Fyers Connected Successfully!")
    else:
        st.error("Login Failed. Please try again.")

# --- Step 1: Login ---
if not st.session_state['access_token']:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, 
        response_type="code", grant_type="authorization_code"
    )
    auth_url = session.generate_authcode()
    st.markdown(f"**[👉 Click Here to Login to Fyers]({auth_url})**")
    st.info("Just click the link above to login. The app will automatically capture the token and redirect you here!")

# --- Step 2: Dashboard ---
if st.session_state['access_token']:
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state['access_token'], log_path="")
    
    # Testing Data Fetching (SBIN)
    data = {
        "symbol": "NSE:SBIN-EQ",
        "resolution": "5",
        "date_format": "1",
        "range_from": "2026-06-17",
        "range_to": "2026-06-17",
        "cont_flag": "1"
    }
    res = fyers.history(data=data)
    
    if res.get("s") == "ok":
        df = pd.DataFrame(res['candles'])
        df.columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
        
        # Format Timestamp to Railway Time
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.strftime('%H:%M')
        
        # 1. EMA & VWAP
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        
        # 2. MACD Calculation
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD_Line'] - df['Signal_Line']
        
        # 3. RSI (14) Calculation
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        df['RSI'] = df['RSI'].fillna(50)
        
        df = df.round(2)

        # --- 🎯 SNIPER SIGNAL ALGORITHM ---
        st.markdown("---")
        st.subheader("🎯 Live Signal System")
        
        latest = df.iloc[-1]
        close = latest['Close']
        vwap = latest['VWAP']
        ema20 = latest['EMA_20']
        macd_hist = latest['MACD_Histogram']
        
        long_condition = (close > ema20) and (close > vwap) and (macd_hist > 0)
        short_condition = (close < ema20) and (close < vwap) and (macd_hist < 0)
        
        if long_condition:
            st.success(f"🟢 STRONG BUY SIGNAL (Call Option) | Price: ₹{close} | RSI: {latest['RSI']}")
        elif short_condition:
            st.error(f"🔴 STRONG SELL SIGNAL (Put Option) | Price: ₹{close} | RSI: {latest['RSI']}")
        else:
            st.warning(f"🟡 NO SIGNAL (Waiting for Setup) | Price: ₹{close} | RSI: {latest['RSI']}")

        # --- 📊 Zerodha Kite Style Chart ---
        st.markdown("---")
        st.subheader("📊 Live Market Chart - Zerodha Kite Style")
        
        fig = go.Figure(data=[go.Candlestick(
            x=df['Timestamp'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Candlestick'
        )])

        fig.update_traces(increasing_line_color='#26a69a', increasing_fillcolor='#26a69a', decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350')
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_20'], line=dict(color='#2196f3', width=1.5), name='EMA 20'))
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_50'], line=dict(color='#ff9800', width=1.5), name='EMA 50'))
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=1.5, dash='dash'), name='VWAP'))

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=600, margin=dict(l=10, r=50, t=30, b=30),
            dragmode='pan',
            xaxis=dict(gridcolor='#f2f2f2', linecolor='#e0e0e0', rangeslider_visible=False),
            yaxis=dict(gridcolor='#f2f2f2', linecolor='#e0e0e0', side='right', fixedrange=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
        
        with st.expander("👁️ View Full Market Data & Indicators"):
            st.dataframe(df.tail(15))
    else:
        st.error("Error fetching data from Fyers.")
