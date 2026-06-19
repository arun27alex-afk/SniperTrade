import plotly.graph_objects as go
import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel
import datetime

# ==========================================
# ⚠️ UPDATE YOUR FYERS API DETAILS HERE ⚠️
# ==========================================
CLIENT_ID = "BT8FRQLN19-200"       
SECRET_KEY = "0ivLeQN8vdI2VyKA"         
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/" 
# ==========================================

st.set_page_config(page_title="Sniper Trade App - Nifty 50", page_icon="🎯", layout="wide")
st.title("🎯 Sniper Trade App (NIFTY 50 Live & Algo Execution)")
st.markdown("---")

if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None

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

if not st.session_state['access_token']:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, 
        response_type="code", grant_type="authorization_code"
    )
    auth_url = session.generate_authcode()
    st.markdown(f"**[👉 Click Here to Login to Fyers]({auth_url})**")

if st.session_state['access_token']:
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state['access_token'], log_path="")
    
    today_date = datetime.date.today().strftime('%Y-%m-%d')
    data = {
        "symbol": "NSE:NIFTY50-INDEX",  
        "resolution": "5",
        "date_format": "1",
        "range_from": today_date,
        "range_to": today_date,
        "cont_flag": "1"
    }
    res = fyers.history(data=data)
    
    if res.get("s") == "ok":
        df = pd.DataFrame(res['candles'])
        df.columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.strftime('%H:%M')
        
        # --- Indicators ---
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        df['VWAP'] = df['VWAP'].fillna(df['Close']) 
        
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        df['RSI'] = df['RSI'].fillna(50)
        
        df = df.round(2)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = latest['Close']
        
        # --- 📌 Sidebar Menu with Expiry & Nifty 50 Lot Selection ---
        with st.sidebar:
            st.header("📈 Live Market")
            st.markdown("---")
            change = close - prev['Close']
            st.metric(label="NIFTY 50 (Spot)", value=f"{close:,.2f}", delta=f"{change:.2f}")
            st.markdown("---")
            st.subheader("⚙️ Options Settings")
            expiry_str = st.text_input("Enter Expiry (e.g., 23JUN - Tuesday)", "23JUN") 
            
            # NIFTY 50 Lot Selection (1 Lot = 65 Qty)
            num_lots = st.number_input("Select Number of Lots", min_value=1, max_value=50, value=1, step=1)
            total_qty = num_lots * 65  
            st.write(f"Total Quantity to Trade: **{total_qty} shares**")

        # --- 🎯 PRO SIGNAL & LIVE ORDER EXECUTION ---
        st.markdown("---")
        st.subheader("🎯 Live NIFTY 50 Premium & Target")
        
        atm_strike = int(round(close / 50) * 50) 
        
        macd_bullish = latest['MACD_Line'] > latest['Signal_Line']
        macd_bearish = latest['MACD_Line'] < latest['Signal_Line']
        
        long_condition = (latest['RSI'] > 60) and (close > latest['VWAP']) and macd_bullish
        short_condition = (latest['RSI'] < 40) and (close < latest['VWAP']) and macd_bearish
        
        def get_premium(opt_type):
            symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{opt_type}"
            try:
                quote_res = fyers.quotes(data={"symbols": symbol})
                if quote_res.get("s") == "ok":
                    return quote_res['d'][0]['v']['lp']
            except:
                pass
            return 0.0

        if long_condition:
            premium = get_premium("CE")
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}CE"
            st.success(f"### 🟢 MARKET GOING UP - BUY CE")
            if premium > 0:
                st.markdown(f"""
                **Buy Strike:** `{atm_strike} CE` | **Lots Selected:** {num_lots} ({total_qty} Qty)
                * **Buy Zone (Premium):** ₹{premium - 2:.2f} to ₹{premium + 2:.2f}
                * **Current Premium:** **₹{premium}**
                * **Target:** ₹{premium + 20:.2f} | **Stop Loss:** ₹{premium - 10:.2f}
                """)
                if st.button(f"🚀 BUY {atm_strike} CE ({num_lots} Lot)", type="primary"):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    if order_res.get("s") == "ok":
                        st.balloons()
                        st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}")
                    else:
                        st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.write(f"Buy Strike: {atm_strike} CE (Market Closed or Check Expiry Format)")
            
        elif short_condition:
            premium = get_premium("PE")
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}PE"
            st.error(f"### 🔴 MARKET GOING DOWN - BUY PE")
            if premium > 0:
                st.markdown(f"""
                **Buy Strike:** `{atm_strike} PE` | **Lots Selected:** {num_lots} ({total_qty} Qty)
                * **Buy Zone (Premium):** ₹{premium - 2:.2f} to ₹{premium + 2:.2f}
                * **Current Premium:** **₹{premium}**
                * **Target:** ₹{premium + 20:.2f} | **Stop Loss:** ₹{premium - 10:.2f}
                """)
                if st.button(f"🚀 BUY {atm_strike} PE ({num_lots} Lot)", type="primary"):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    if order_res.get("s") == "ok":
                        st.balloons()
                        st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}")
                    else:
                        st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.write(f"Buy Strike: {atm_strike} PE (Market Closed or Check Expiry Format)")
            
        else:
            st.warning(f"### 🟡 WAITING FOR PERFECT SETUP")
            st.markdown(f"**Current NIFTY 50 Trend is Weak.** \n* Spot Price: {close} \n* RSI: {latest['RSI']:.2f}")

        # --- 📊 Live Market Chart ---
        st.markdown("---")
        st.subheader("📊 Live NIFTY 50 Chart")
        fig = go.Figure(data=[go.Candlestick(x=df['Timestamp'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Candlestick')])
        fig.update_traces(increasing_line_color='#26a69a', increasing_fillcolor='#26a69a', decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350')
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=1.5, dash='dash'), name='VWAP'))

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=600, margin=dict(l=10, r=50, t=30, b=80),
            dragmode='pan',
            xaxis=dict(gridcolor='#f2f2f2', linecolor='#e0e0e0', rangeslider_visible=False),
            yaxis=dict(gridcolor='#f2f2f2', linecolor='#e0e0e0', side='right', fixedrange=False),
            legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
