import plotly.graph_objects as go
import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel
import datetime

# --- 1. CREDENTIALS ---
CLIENT_ID = "BT8FRQLN19-200"           
SECRET_KEY = "0ivLeQN8vdI2VyKA"  
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/"  

st.set_page_config(page_title="Sniper Trade App", layout="wide")
st.title("🎯 Sniper Trade App (Auto-Login & Pro Signals)")
st.markdown("---")

if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None

session = fyersModel.SessionModel(
    client_id=CLIENT_ID,
    secret_key=SECRET_KEY,
    redirect_uri=REDIRECT_URI,
    response_type="code",
    grant_type="authorization_code"
)

# --- 2. AUTOMATIC TOKEN CAPTURE (NO COPY-PASTE) ---
query_params = st.query_params
if "auth_code" in query_params and st.session_state['access_token'] is None:
    auth_code = query_params["auth_code"]
    session.set_token(auth_code)
    response = session.generate_token()
    if "access_token" in response:
        st.session_state['access_token'] = response["access_token"]
        st.query_params.clear() # Clear auth_code from URL for security
        st.rerun() # Refresh app to open the main dashboard
    else:
        st.error("Token generation failed. Please check your credentials.")

# --- 3. 1-CLICK LOGIN SCREEN ---
if st.session_state['access_token'] is None:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    login_url = session.generate_authcode()
    st.markdown(f"**[👉 Click Here to Login to Fyers]({login_url})**")
    st.info("Just click the link above to login. The app will automatically capture the token and redirect you here!")

# --- 4. MAIN DASHBOARD & SIGNAL SYSTEM ---
else:
    st.success("🟢 Fyers Connected Successfully!")
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state['access_token'], log_path="")
    
    st.subheader("📈 Pro Indicators & Market Data")
    try:
        # Fetch data for technical analysis
        test_date = "2026-06-17" 
        
        data_vwap = {
            "symbol": "NSE:SBIN-EQ",
            "resolution": "5",
            "date_format": "1",
            "range_from": test_date,
            "range_to": test_date,
            "cont_flag": "1"
        }
        response_vwap = fyers.history(data=data_vwap)
        
        if response_vwap['s'] == 'ok':
            columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
            df = pd.DataFrame(response_vwap['candles'], columns=columns)
            
            # Formats to show only the 24-hour Railway Time (e.g., 09:15)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.strftime('%H:%M')
            
            # --- TECHNICAL INDICATORS LOGIC ---
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['Cumulative_Volume'] = df['Volume'].cumsum()
            df['Cumulative_TP_V'] = (df['Typical_Price'] * df['Volume']).cumsum()
            df['VWAP'] = (df['Cumulative_TP_V'] / df['Cumulative_Volume']).round(2)
            
            df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean().round(2)
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean().round(2)
            
            display_df = df[['Timestamp', 'Close', 'Volume', 'VWAP', 'EMA_20', 'EMA_50']].tail(5)
            # --- 📊 Zerodha Kite Style Candlestick Chart ---
            st.markdown("---")
            st.subheader(f"📊 Live Market Chart ({test_date}) - Zerodha Kite Style")
            
            fig = go.Figure(data=[go.Candlestick(
                x=df['Timestamp'],
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Candlestick'
            )])

            # 1. Zerodha Kite Custom Candle Colors (Teal Green & Coral Red)
            fig.update_traces(
                increasing_line_color='#26a69a', 
                increasing_fillcolor='#26a69a',
                decreasing_line_color='#ef5350', 
                decreasing_fillcolor='#ef5350'
            )

            # 2. Add EMA and VWAP Lines with professional styling
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_20'], line=dict(color='#2196f3', width=1.5), name='EMA 20'))
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_50'], line=dict(color='#ff9800', width=1.5), name='EMA 50'))
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=1.5, dash='dash'), name='VWAP'))

            # 3. Zerodha Kite Layout Styling (White Background, Rightside Price Scale, Light Gridlines)
            fig.update_layout(
                plot_bgcolor='white',
                paper_bgcolor='white',
                height=600,
                margin=dict(l=10, r=50, t=30, b=30),
                xaxis=dict(
                    gridcolor='#f2f2f2',
                    linecolor='#e0e0e0',
                    rangeslider_visible=False
                ),
                yaxis=dict(
                    gridcolor='#f2f2f2',
                    linecolor='#e0e0e0',
                    side='right' # Keeps price scale on the right side just like Zerodha
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(display_df, use_container_width=True)
            
            # --- 🎯 SNIPER SIGNAL ALGORITHM ---
            st.markdown("---")
            st.subheader("🎯 Live Signal System")
            
            latest = df.iloc[-1]
            close = latest['Close']
            vwap = latest['VWAP']
            ema20 = latest['EMA_20']
            ema50 = latest['EMA_50']
            
            # Buy Condition: Price must be above VWAP, EMA 20, and EMA 50
            if close > vwap and close > ema20 and close > ema50:
                st.success(f"🟢 STRONG BUY SIGNAL (Call Option) at ₹{close}")
            # Sell Condition: Price must be below VWAP, EMA 20, and EMA 50
            elif close < vwap and close < ema20 and close < ema50:
                st.error(f"🔴 STRONG SELL SIGNAL (Put Option) at ₹{close}")
            # No Signal Condition: Avoids fake breakouts and choppy markets
            else:
                st.warning(f"🟡 NO SIGNAL (Market in Range/Fake Move) at ₹{close}")
                
        else:
            st.error("Market data fetch error from Fyers Server.")
    except Exception as e:
        st.error(f"System Error: {e}")
