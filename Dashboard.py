import streamlit as st
import yfinance as yf
import pandas as pd
import ta
import math
import plotly.graph_objects as go

# --- PAGE CONFIGURATION & UI SETUP ---
st.set_page_config(page_title="SniperTrade Algo", page_icon="🎯", layout="wide")

@st.cache_data(ttl=60) 
def get_nifty_data():
    nifty = yf.Ticker("^NSEI")
    data = nifty.history(period="5d", interval="5m") 
    return data

try:
    data = get_nifty_data()
    
    if not data.empty:
        
        # --- INDICATORS CALCULATION ---
        data['EMA_20'] = ta.trend.ema_indicator(close=data['Close'], window=20)
        data['RSI_14'] = ta.momentum.rsi(close=data['Close'], window=14)
        data['ATR_14'] = ta.volatility.average_true_range(high=data['High'], low=data['Low'], close=data['Close'], window=14)
        
        current_candle = data.iloc[-1]
        prev_candle = data.iloc[-2]
        current_price = current_candle['Close']
        
        # --- ATM STRIKE PRICE CALCULATION ---
        # Nifty strike prices are in multiples of 50. We round the current price to the nearest 50.
        atm_strike = int(round(current_price / 50.0) * 50)
        
        # --- CANDLESTICK PATTERN LOGIC ---
        is_prev_bearish = prev_candle['Close'] < prev_candle['Open']
        is_curr_bullish = current_candle['Close'] > current_candle['Open']
        does_bullish_engulf = (current_candle['Close'] >= prev_candle['Open']) and (current_candle['Open'] <= prev_candle['Close'])
        bullish_engulfing = is_prev_bearish and is_curr_bullish and does_bullish_engulf
        
        body_size = abs(current_candle['Close'] - current_candle['Open'])
        lower_shadow = min(current_candle['Open'], current_candle['Close']) - current_candle['Low']
        upper_shadow = current_candle['High'] - max(current_candle['Open'], current_candle['Close'])
        is_hammer = (lower_shadow >= (2 * body_size)) and (upper_shadow <= (0.5 * body_size)) and (body_size > 0)
        
        is_prev_bullish = prev_candle['Close'] > prev_candle['Open']
        is_curr_bearish = current_candle['Close'] < current_candle['Open']
        does_bearish_engulf = (current_candle['Close'] <= prev_candle['Open']) and (current_candle['Open'] >= prev_candle['Close'])
        bearish_engulfing = is_prev_bullish and is_curr_bearish and does_bearish_engulf
        
        is_shooting_star = (upper_shadow >= (2 * body_size)) and (lower_shadow <= (0.5 * body_size)) and (body_size > 0)

        if is_hammer: pattern = "Hammer 🔨"
        elif bullish_engulfing: pattern = "Bullish Engulfing 📈"
        elif is_shooting_star: pattern = "Shooting Star 🌠"
        elif bearish_engulfing: pattern = "Bearish Engulfing 📉"
        else: pattern = "No Active Pattern"

        # --- UI: SIDEBAR DESIGN ---
        with st.sidebar:
            st.title("🎯 SniperTrade")
            st.write("Precision Algo Engine")
            st.write("---")
            st.metric(label="Current Nifty 50 Price", value=f"₹{current_price:.2f}")
            st.metric(label="Nearest ATM Strike", value=f"{atm_strike}")
            st.write("---")
            st.write("### 📊 Live Insights")
            st.metric(label="RSI (14)", value=f"{current_candle['RSI_14']:.2f}")
            st.metric(label="EMA (20)", value=f"{current_candle['EMA_20']:.2f}")
            st.info(f"**Live Pattern:**\n{pattern}")

        # --- UI: MAIN AREA & TABS ---
        st.title("Welcome to SniperTrade Dashboard")
        st.write("Get high-probability trading signals with smart risk management.")
        
        tab1, tab2 = st.tabs(["🎯 Live Trade Signals", "📊 Raw Data & Indicators"])
        
        with tab1:
            st.subheader("Live Setup & Entry Zones")
            
            trend_is_up = current_price > current_candle['EMA_20']
            rsi_is_bullish = current_candle['RSI_14'] > 55
            buy_trigger = bullish_engulfing or is_hammer
            
            trend_is_down = current_price < current_candle['EMA_20']
            rsi_is_bearish = current_candle['RSI_14'] < 45
            sell_trigger = bearish_engulfing or is_shooting_star
            
            if trend_is_up and rsi_is_bullish and buy_trigger:
                st.success("## 🟢 STRONG BUY SIGNAL (CALL OPTION)")
                st.write(f"### 🛒 **Suggested Trade:** Buy Nifty **{atm_strike} CE**")
                
                stop_loss = current_price - (current_candle['ATR_14'] * 1.5)
                risk_points = current_price - stop_loss
                target = current_price + (risk_points * 2)
                safe_entry_max = current_price + 15
                
                # Risk calculation for 1 Lot (25 Qty)
                max_risk_rupees = risk_points * 25
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Signal Price", f"₹{current_price:.2f}")
                col2.metric("🎯 Target", f"₹{target:.2f}")
                col3.metric("🛡️ Stop Loss", f"₹{stop_loss:.2f}")
                
                st.write(f"**Max Risk (1 Lot / 25 Qty):** ₹{max_risk_rupees:.2f} | **Safe Entry Max Price:** ₹{safe_entry_max:.2f}")
                
                if current_price > safe_entry_max:
                    st.warning("⚠️ **Late Entry Warning:** The ideal buying zone has passed. Entering now reduces the signal accuracy and increases your risk. Proceed at your own risk.")
                else:
                    st.info("👍 **Safe Entry Zone:** You are in the optimal buying range. Good to enter!")
                    
            elif trend_is_down and rsi_is_bearish and sell_trigger:
                st.error("## 🔴 STRONG SELL SIGNAL (PUT OPTION)")
                st.write(f"### 🛒 **Suggested Trade:** Buy Nifty **{atm_strike} PE**")
                
                stop_loss = current_price + (current_candle['ATR_14'] * 1.5)
                risk_points = stop_loss - current_price
                target = current_price - (risk_points * 2)
                safe_entry_min = current_price - 15
                
                # Risk calculation for 1 Lot (25 Qty)
                max_risk_rupees = risk_points * 25
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Signal Price", f"₹{current_price:.2f}")
                col2.metric("🎯 Target", f"₹{target:.2f}")
                col3.metric("🛡️ Stop Loss", f"₹{stop_loss:.2f}")
                
                st.write(f"**Max Risk (1 Lot / 25 Qty):** ₹{max_risk_rupees:.2f} | **Safe Entry Min Price:** ₹{safe_entry_min:.2f}")
                
                if current_price < safe_entry_min:
                    st.warning("⚠️ **Late Entry Warning:** The ideal buying zone has passed. Entering now reduces the signal accuracy and increases your risk. Proceed at your own risk.")
                else:
                    st.info("👍 **Safe Entry Zone:** You are in the optimal buying range. Good to enter!")
                    
            else:
                st.warning("### 🟡 NEUTRAL / NO TRADE")
                st.write("**Status:** Sniper is waiting for the perfect setup. Capital protection is our first priority.")

        with tab2:
            st.subheader("Data Table (Last 10 5-Min Candles)")
            display_cols = ['Open', 'High', 'Low', 'Close', 'EMA_20', 'RSI_14', 'ATR_14']
            
            table_data = data[display_cols].tail(10).copy()
            if table_data.index.tz is not None:
                table_data.index = table_data.index.tz_localize(None)
            table_data.index = table_data.index.strftime('%d-%m-%Y %H:%M')
            table_data.index.name = 'Date & Time'
            
            st.dataframe(table_data, use_container_width=True)
        
    else:
        st.warning("Currently no live data available.")
        
except Exception as e:
    st.error(f"Error fetching data: {e}")
