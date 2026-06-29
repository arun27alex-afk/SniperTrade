import datetime
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from fyers_apiv3 import fyersModel

# ==========================================
# ⚠️ UPDATE YOUR FYERS API DETAILS HERE ⚠️
# ==========================================
CLIENT_ID = "BT8FRQLN19-200"
SECRET_KEY = "0ivLeQN8vdI2VyKA"
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/"
# ==========================================

st.set_page_config(page_title="Sniper Trade App - NIFTY 50", page_icon="🎯", layout="wide")

# --- STRATEGY CONSTANTS ---
MARKET_OPEN = datetime.time(9, 15)
ORB_END = datetime.time(9, 30)
NO_TRADE_START = datetime.time(12, 0)
NO_TRADE_END = datetime.time(13, 30)
LAST_ENTRY_TIME = datetime.time(14, 45)
MAX_TRADES_PER_DAY = 3
RISK_ATR_MULTIPLIER = 1.25
REWARD_R_MULTIPLIER = 2.25
TRAIL_TRIGGER_R = 1.0
TRAIL_ATR_MULTIPLIER = 1.0
MACD_CONFIRMATION_LOOKBACK = 3
DIAGNOSTIC_FILTERS = [
    "Higher Timeframe Trend",
    "ADX Filter",
    "ORB Filter",
    "VWAP Breakout/Retest",
    "MACD Confirmation",
    "RSI Momentum",
    "Volume Filter",
]

@dataclass(frozen=True)
class SignalDecision:
    signal: Optional[str]
    score: int
    checklist: Dict[str, bool]
    reason: str
    sl_points: float
    target_points: float

# --- STRATEGY FUNCTIONS ---
def _rma(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().sort_values("Timestamp").reset_index(drop=True)
    out["Session_Date"] = out["Timestamp"].dt.date
    out["Typical_Price"] = (out["High"] + out["Low"] + out["Close"]) / 3
    session_pv = (out["Typical_Price"] * out["Volume"]).groupby(out["Session_Date"]).cumsum()
    session_volume = out["Volume"].replace(0, np.nan).groupby(out["Session_Date"]).cumsum()
    out["VWAP"] = (session_pv / session_volume).fillna(out["Close"])

    out["EMA_9"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["EMA_21"] = out["Close"].ewm(span=21, adjust=False).mean()
    out["EMA_50"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["EMA_50_Slope"] = out["EMA_50"].diff(3)

    out["EMA_12"] = out["Close"].ewm(span=12, adjust=False).mean()
    out["EMA_26"] = out["Close"].ewm(span=26, adjust=False).mean()
    out["MACD_Line"] = out["EMA_12"] - out["EMA_26"]
    out["Signal_Line"] = out["MACD_Line"].ewm(span=9, adjust=False).mean()
    out["MACD_Hist"] = out["MACD_Line"] - out["Signal_Line"]

    delta = out["Close"].diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    rs = _rma(gain, 14) / _rma(loss, 14).replace(0, np.nan)
    out["RSI"] = (100 - (100 / (1 + rs))).fillna(50)
    out["RSI_Slope"] = out["RSI"].diff(3)

    prev_close = out["Close"].shift(1)
    tr = pd.concat([(out["High"] - out["Low"]), (out["High"] - prev_close).abs(), (out["Low"] - prev_close).abs()], axis=1).max(axis=1)
    out["TR"] = tr
    out["ATR"] = _rma(tr, 14).bfill()
    out["ATR_Pct"] = out["ATR"] / out["Close"] * 100

    up_move = out["High"].diff()
    down_move = -out["Low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=out.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=out.index)
    atr = _rma(tr, 14).replace(0, np.nan)
    out["Plus_DI"] = 100 * _rma(plus_dm, 14) / atr
    out["Minus_DI"] = 100 * _rma(minus_dm, 14) / atr
    dx = ((out["Plus_DI"] - out["Minus_DI"]).abs() / (out["Plus_DI"] + out["Minus_DI"]).replace(0, np.nan)) * 100
    out["ADX"] = _rma(dx, 14).fillna(0)

    out["Volume_SMA_20"] = out["Volume"].rolling(20, min_periods=5).mean()
    out["Volume_Ratio"] = out["Volume"] / out["Volume_SMA_20"].replace(0, np.nan)

    htf_frames = []
    for _, session_df in out.set_index("Timestamp").groupby("Session_Date"):
        htf = session_df.resample("15min", label="right", closed="right").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        htf["HTF_EMA_9"] = htf["Close"].ewm(span=9, adjust=False).mean()
        htf["HTF_EMA_21"] = htf["Close"].ewm(span=21, adjust=False).mean()
        htf["HTF_EMA_21_Slope"] = htf["HTF_EMA_21"].diff(2)
        htf_frames.append(htf.shift(1)) 
    htf_all = pd.concat(htf_frames).sort_index() if htf_frames else pd.DataFrame(columns=["HTF_EMA_9", "HTF_EMA_21", "HTF_EMA_21_Slope"])
    out = pd.merge_asof(out, htf_all[["HTF_EMA_9", "HTF_EMA_21", "HTF_EMA_21_Slope"]].reset_index(), on="Timestamp", direction="backward")

    orb_mask = out["Timestamp"].dt.time <= ORB_END
    out["ORB_High"] = out["High"].where(orb_mask).groupby(out["Session_Date"]).transform("max")
    out["ORB_Low"] = out["Low"].where(orb_mask).groupby(out["Session_Date"]).transform("min")
    out["VWAP_Distance_ATR"] = (out["Close"] - out["VWAP"]).abs() / out["ATR"].replace(0, np.nan)
    return out.round(2)


def _fresh_cross(df: pd.DataFrame, i: int, side: str, lookback: int = MACD_CONFIRMATION_LOOKBACK) -> bool:
    start = max(1, i - lookback + 1)
    window = df.iloc[start:i + 1]
    prev_window = df.iloc[start - 1:i]
    row = df.iloc[i]
    if side == "CE":
        recent_cross = ((window["MACD_Line"].to_numpy() > window["Signal_Line"].to_numpy()) & (prev_window["MACD_Line"].to_numpy() <= prev_window["Signal_Line"].to_numpy())).any()
        return bool(recent_cross and row["MACD_Line"] > row["Signal_Line"] and row["MACD_Line"] > 0)
    recent_cross = ((window["MACD_Line"].to_numpy() < window["Signal_Line"].to_numpy()) & (prev_window["MACD_Line"].to_numpy() >= prev_window["Signal_Line"].to_numpy())).any()
    return bool(recent_cross and row["MACD_Line"] < row["Signal_Line"] and row["MACD_Line"] < 0)


def _vwap_breakout_retest(df: pd.DataFrame, i: int, side: str) -> bool:
    start = max(0, i - 6)
    window = df.iloc[start:i + 1]
    row = df.iloc[i]
    tol = max(row["ATR"] * 0.18, 3)
    if side == "CE":
        breakout_seen = ((window["Close"] > window["VWAP"] + tol) & (window["Close"].shift(1) <= window["VWAP"].shift(1) + tol)).any()
        retest_hold = row["Low"] <= row["VWAP"] + tol and row["Close"] > row["VWAP"] + tol
    else:
        breakout_seen = ((window["Close"] < window["VWAP"] - tol) & (window["Close"].shift(1) >= window["VWAP"].shift(1) - tol)).any()
        retest_hold = row["High"] >= row["VWAP"] - tol and row["Close"] < row["VWAP"] - tol
    return bool(breakout_seen or retest_hold)


def _filter_states(df: pd.DataFrame, i: int, side: str, last_signal_side: Optional[str] = None) -> Dict[str, bool]:
    row = df.iloc[i]
    candle_time = row["Timestamp"].time()
    tradable_time = MARKET_OPEN < candle_time <= LAST_ENTRY_TIME and not (NO_TRADE_START <= candle_time <= NO_TRADE_END)
    bull = side == "CE"
    return {
        "Tradable Time": tradable_time,
        "5m Trend": (row["EMA_9"] > row["EMA_21"] > row["EMA_50"] and row["EMA_50_Slope"] > 0) if bull else (row["EMA_9"] < row["EMA_21"] < row["EMA_50"] and row["EMA_50_Slope"] < 0),
        "Higher Timeframe Trend": (row["HTF_EMA_9"] > row["HTF_EMA_21"] and row["HTF_EMA_21_Slope"] > 0) if bull else (row["HTF_EMA_9"] < row["HTF_EMA_21"] and row["HTF_EMA_21_Slope"] < 0),
        "ADX Filter": (row["ADX"] >= 22 and row["Plus_DI"] > row["Minus_DI"]) if bull else (row["ADX"] >= 22 and row["Minus_DI"] > row["Plus_DI"]),
        "VWAP Breakout/Retest": _vwap_breakout_retest(df, i, side),
        "MACD Confirmation": _fresh_cross(df, i, side),
        "RSI Momentum": (55 <= row["RSI"] <= 72 and row["RSI_Slope"] > 0) if bull else (28 <= row["RSI"] <= 45 and row["RSI_Slope"] < 0),
        "Volume Filter": row["Volume_Ratio"] >= 1.25,
        "ORB Filter": row["Close"] > row["ORB_High"] if bull else row["Close"] < row["ORB_Low"],
        "Volatility Regime": row["ATR_Pct"] >= 0.045 and row["VWAP_Distance_ATR"] <= 1.6,
        "Duplicate Guard": last_signal_side != side,
    }


def evaluate_signal(df: pd.DataFrame, i: int, last_signal_side: Optional[str] = None) -> SignalDecision:
    row = df.iloc[i]
    sl_points = round(RISK_ATR_MULTIPLIER * row["ATR"], 2)
    target_points = round(sl_points * REWARD_R_MULTIPLIER, 2)

    def side_check(side: str) -> Tuple[int, Dict[str, bool]]:
        states = _filter_states(df, i, side, last_signal_side)
        checks = {
            "Tradable time; avoids lunch chop and late entries": states["Tradable Time"],
            "Strong 5m trend: EMA 9/21/50 stacked with EMA50 slope": states["5m Trend"],
            "Completed 15m trend confirms direction": states["Higher Timeframe Trend"],
            "ADX trend-strength filter: ADX >= 22 and DI agrees": states["ADX Filter"],
            "VWAP breakout/retest confirmation; not simple above/below": states["VWAP Breakout/Retest"],
            "Recent MACD crossover with zero-line confirmation": states["MACD Confirmation"],
            "RSI momentum with slope, avoiding exhausted extremes": states["RSI Momentum"],
            "Volume expansion confirms institutional participation": states["Volume Filter"],
            "ORB participation confirms range expansion": states["ORB Filter"],
            "Volatility regime is tradable, not compressed/sideways": states["Volatility Regime"],
            "Duplicate signal guard": states["Duplicate Guard"],
        }
        score = int(sum(checks.values()))
        return score, checks

    ce_score, ce_checks = side_check("CE")
    pe_score, pe_checks = side_check("PE")
    if ce_score == len(ce_checks) and ce_score >= pe_score:
        return SignalDecision("CE", ce_score, ce_checks, "Premium-quality BUY CE setup confirmed.", sl_points, target_points)
    if pe_score == len(pe_checks):
        return SignalDecision("PE", pe_score, pe_checks, "Premium-quality BUY PE setup confirmed.", sl_points, target_points)
    best_signal, best_score, best_checks = ("CE", ce_score, ce_checks) if ce_score >= pe_score else ("PE", pe_score, pe_checks)
    return SignalDecision(None, best_score, best_checks, f"Waiting: best candidate is {best_signal}, but all institutional filters are not aligned.", sl_points, target_points)


def build_diagnostic_report(df: pd.DataFrame, start_index: int = 50) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    combo_rows = []
    sides = ("CE", "PE")
    filter_order = DIAGNOSTIC_FILTERS
    base_filters = ["Tradable Time", "5m Trend", "Volatility Regime"]
    sample_count = max(0, len(df) - start_index) * len(sides)

    states_by_side = {side: [] for side in sides}
    for i in range(start_index, len(df)):
        for side in sides:
            states_by_side[side].append(_filter_states(df, i, side))

    for filter_name in filter_order:
        for side in sides:
            passed = sum(1 for states in states_by_side[side] if states[filter_name])
            total = len(states_by_side[side])
            rows.append({
                "Filter": filter_name,
                "Side": side,
                "Passed Candles": passed,
                "Failed Candles": total - passed,
                "Pass %": round((passed / total * 100) if total else 0, 2),
            })
        combined_passed = sum(1 for side in sides for states in states_by_side[side] if states[filter_name])
        rows.append({
            "Filter": filter_name,
            "Side": "Combined",
            "Passed Candles": combined_passed,
            "Failed Candles": sample_count - combined_passed,
            "Pass %": round((combined_passed / sample_count * 100) if sample_count else 0, 2),
        })

    cumulative = base_filters.copy()
    for filter_name in filter_order:
        cumulative.append(filter_name)
        passed = sum(
            1
            for side in sides
            for states in states_by_side[side]
            if all(states[name] for name in cumulative)
        )
        combo_rows.append({
            "Cumulative Filters Through": filter_name,
            "Passed Candidates": passed,
            "Blocked Candidates": sample_count - passed,
            "Pass %": round((passed / sample_count * 100) if sample_count else 0, 2),
        })

    return pd.DataFrame(rows), pd.DataFrame(combo_rows)

def run_intraday_backtest(df: pd.DataFrame) -> Tuple[Dict[str, int], List[dict], Optional[dict]]:
    stats = {"signals": 0, "targets": 0, "stops": 0, "breakeven": 0}
    trades: List[dict] = []
    active: Optional[dict] = None
    last_side: Optional[str] = None
    for i in range(50, len(df)):
        row = df.iloc[i]
        if active:
            long = active["side"] == "CE"
            reached_1r = row["High"] >= active["entry"] + active["risk"] if long else row["Low"] <= active["entry"] - active["risk"]
            if reached_1r:
                active["sl"] = active["entry"]
                active["trail"] = True
            if active.get("trail"):
                active["sl"] = max(active["sl"], row["Close"] - TRAIL_ATR_MULTIPLIER * row["ATR"]) if long else min(active["sl"], row["Close"] + TRAIL_ATR_MULTIPLIER * row["ATR"])
            hit_target = row["High"] >= active["target"] if long else row["Low"] <= active["target"]
            hit_sl = row["Low"] <= active["sl"] if long else row["High"] >= active["sl"]
            if hit_target or hit_sl:
                stats["targets" if hit_target else "breakeven" if active.get("trail") else "stops"] += 1
                active = None
        if active or stats["signals"] >= MAX_TRADES_PER_DAY:
            continue
        decision = evaluate_signal(df, i, last_side)
        if decision.signal:
            direction = 1 if decision.signal == "CE" else -1
            active = {"side": decision.signal, "entry": row["Close"], "risk": decision.sl_points, "sl": row["Close"] - direction * decision.sl_points, "target": row["Close"] + direction * decision.target_points, "trail": False, "time": row["Timestamp"]}
            trades.append(active.copy())
            stats["signals"] += 1
            last_side = decision.signal
    return stats, trades, active

# --- UI & APP FUNCTIONS ---
def play_alert_sound():
    st.components.v1.html('<audio autoplay="true"><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mpeg"></audio>', width=0, height=0, scrolling=False)

def get_premium(fyers, expiry_str, atm_strike, opt_type):
    symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{opt_type}"
    try:
        quote_res = fyers.quotes(data={"symbols": symbol})
        if quote_res.get("s") == "ok":
            return quote_res["d"][0]["v"]["lp"]
    except Exception as exc:
        st.caption(f"Premium quote unavailable: {exc}")
    return 0.0

st.title("🎯 Sniper Trade App (NIFTY 50 Live & Algo Execution)")
st.markdown("---")
st.info("Strategy upgraded: fewer, higher-probability trades only. The UI and Fyers flow are intentionally unchanged.")

with st.expander("Why this strategy is stricter"):
    st.markdown(
        """
        * **Trend stack + 15m confirmation** rejects counter-trend scalps and aligns 5-minute entries with the higher timeframe.
        * **ADX + DI filter** avoids weak/sideways sessions where EMA/VWAP signals usually fail.
        * **VWAP breakout/retest** replaces basic above/below VWAP logic, reducing late chase entries.
        * **Recent MACD crossover + zero-line** keeps momentum confirmation but allows the cross to occur up to 3 candles before VWAP/ORB confirmation.
        * **RSI slope and range limits** confirm momentum while avoiding overextended option-premium entries.
        * **Volume + ORB confirmation** requires participation and range expansion before buying CE/PE.
        * **ATR risk with 1:2.25 reward and trailing stop** preserves dynamic exits while keeping reward between 1:2 and 1:2.5.
        * **Duplicate and max-trade guards** cap signals at premium setups only.
        """
    )

if "access_token" not in st.session_state:
    st.session_state["access_token"] = None

query_params = st.query_params
if "auth_code" in query_params:
    session = fyersModel.SessionModel(client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code")
    session.set_token(query_params["auth_code"])
    response = session.generate_token()
    if response.get("s") == "ok":
        st.session_state["access_token"] = response["access_token"]
        st.success("✅ Fyers Connected Successfully!")
    else:
        st.error("Login Failed. Please try again.")

if not st.session_state["access_token"]:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    session = fyersModel.SessionModel(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code")
    st.markdown(f"**[👉 Click Here to Login to Fyers]({session.generate_authcode()})**")

if st.session_state["access_token"]:
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state["access_token"], log_path="")
    today = datetime.date.today()
    today_date = (today - datetime.timedelta(days=1 if today.weekday() == 5 else 2 if today.weekday() == 6 else 0)).strftime("%Y-%m-%d")
    res = fyers.history(data={"symbol": "NSE:NIFTY50-INDEX", "resolution": "5", "date_format": "1", "range_from": today_date, "range_to": today_date, "cont_flag": "1"})

    if res.get("s") == "ok" and res.get("candles"):
        df = pd.DataFrame(res["candles"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="s").dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
        df = add_indicators(df)
        stats, trades, active_trade = run_intraday_backtest(df)
        filter_report, combination_report = build_diagnostic_report(df)
        buy_x = [t["time"] for t in trades if t["side"] == "CE"]
        buy_y = [t["entry"] - 15 for t in trades if t["side"] == "CE"]
        sell_x = [t["time"] for t in trades if t["side"] == "PE"]
        sell_y = [t["entry"] + 15 for t in trades if t["side"] == "PE"]

        st.subheader("📊 Today's Auto-Backtest Scorecard")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Signals Triggered", stats["signals"])
        col2.metric("🎯 Targets Hit", stats["targets"])
        col3.metric("🛡️ Cost-to-Cost", stats["breakeven"])
        col4.metric("🛑 Stop Loss Hit", stats["stops"])
        closed = stats["targets"] + stats["stops"] + stats["breakeven"]
        col5.metric("🏆 Win Rate (%)", f"{(stats['targets'] / closed * 100) if closed else 0:.1f}%")
        st.markdown("---")

        with st.expander("🔎 Strategy Diagnostic Report — filter pass/fail counts", expanded=stats["signals"] == 0):
            st.caption("Use this report to debug over-filtering. Individual counts show each filter by itself; cumulative counts show where candidates disappear as filters are layered.")
            st.markdown("**Individual Filter Pass/Fail Counts**")
            st.dataframe(filter_report, use_container_width=True, hide_index=True)
            st.markdown("**Cumulative Blocking Analysis**")
            st.dataframe(combination_report, use_container_width=True, hide_index=True)
            if not combination_report.empty:
                first_zero = combination_report[combination_report["Passed Candidates"] == 0].head(1)
                if not first_zero.empty:
                    st.warning(f"First cumulative blocker: **{first_zero.iloc[0]['Cumulative Filters Through']}**. Review this filter with the previous row to identify the restrictive combination.")
                else:
                    st.success("No cumulative zero-blocker found in today's sample.")

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = latest["Close"]
        decision = evaluate_signal(df, len(df) - 1, trades[-1]["side"] if trades else None)

        with st.sidebar:
            st.header("📈 Live Market")
            st.metric(label="NIFTY 50 (Spot)", value=f"{close:,.2f}", delta=f"{close - prev['Close']:.2f}")
            st.markdown("---")
            st.subheader("⚙️ Options Settings")
            expiry_str = st.text_input("Enter Expiry (e.g., 26JUN)", "26JUN")
            num_lots = st.number_input("Select Number of Lots", min_value=1, max_value=50, value=1, step=1)
            total_qty = num_lots * 65
            st.write(f"Total Quantity: **{total_qty} shares**")
            st.markdown("---")
            auto_refresh = st.checkbox("🔄 Auto Refresh (10 Sec)", value=True)

        st.subheader("🎯 Live Signal Alert")
        atm_strike = int(round(close / 50) * 50)
        signal_time = latest["Timestamp"].strftime("%I:%M %p")
        if NO_TRADE_START <= latest["Timestamp"].time() <= NO_TRADE_END:
            st.warning("⏳ **NO TRADE ZONE (12:00 PM to 1:30 PM)**")
        elif decision.signal:
            play_alert_sound()
            premium = get_premium(fyers, expiry_str, atm_strike, decision.signal)
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{decision.signal}"
            alert = st.success if decision.signal == "CE" else st.error
            alert(f"### {'🟢 MARKET GOING UP - BUY CE' if decision.signal == 'CE' else '🔴 MARKET GOING DOWN - BUY PE'} (Score: {decision.score}/{len(decision.checklist)}) @ {signal_time}")
            st.markdown("### 📊 Institutional Checklist")
            for label, ok in decision.checklist.items():
                st.markdown(f"{'✅' if ok else '❌'} **{label}**")
            
            if premium > 0:
                # 🚀 PERCENTAGE-BASED TARGET AND STOP LOSS FOR PREMIUM 
                target_pct = 0.20  # 20% Target
                sl_pct = 0.10      # 10% Stop Loss
                
                target_price = round(premium + (premium * target_pct), 2)
                sl_price = round(premium - (premium * sl_pct), 2)
                
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("📌 Strike Rate", f"{atm_strike} {decision.signal}")
                c2.metric("🚪 Entry Price", f"₹{premium}")
                c3.metric(f"🎯 Target (+20%)", f"₹{target_price}")
                c4.metric(f"🛑 Stop Loss (-10%)", f"₹{sl_price}")
                c5.metric("⏰ Signal Time", signal_time)
                st.info(f"💡 **Safe Entry Range:** ₹{premium} to ₹{round(premium + 4, 2)} only. Avoid chasing beyond this range.")
                
                if st.button(f"🚀 BUY {atm_strike} {decision.signal} NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}") if order_res.get("s") == "ok" else st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.warning(f"Strike: {atm_strike} {decision.signal} - **Market Closed or Expiry Incorrect**")
        else:
            st.warning("### 🟡 WAITING FOR PERFECT SETUP")
            st.markdown(f"**{decision.reason}**\n\n* **Best Score:** {decision.score}/{len(decision.checklist)}")
            for label, ok in decision.checklist.items():
                st.markdown(f"{'✅' if ok else '❌'} {label}")

        st.markdown("---")
        st.subheader("🖥️ Live Market HUD")
        h1, h2, h3, h4 = st.columns(4)
        h1.info(f"**RSI (14):** {latest['RSI']:.2f}\n\n{'🟢 Momentum' if latest['RSI'] > 55 else '🔴 Momentum' if latest['RSI'] < 45 else '🟡 Neutral'}")
        h2.info(f"**ADX (14):** {latest['ADX']:.2f}\n\n{'🟢 Trending' if latest['ADX'] >= 22 else '🔴 Sideways'}")
        h3.info(f"**15m Trend:**\n\n{'🟢 Bullish' if latest['HTF_EMA_9'] > latest['HTF_EMA_21'] else '🔴 Bearish'}")
        h4.info(f"**VWAP Setup:**\n\nDistance {latest['VWAP_Distance_ATR']:.2f} ATR")

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.75, 0.25])
        fig.add_trace(go.Candlestick(x=df["Timestamp"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Candles"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["VWAP"], line=dict(color="#795548", width=2, dash="dash"), name="VWAP"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["EMA_9"], line=dict(color="#2196f3", width=1.5), name="EMA 9"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["EMA_21"], line=dict(color="#f44336", width=1.5), name="EMA 21"), row=1, col=1)
        fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode="markers", marker=dict(symbol="triangle-up", size=16, color="#00e5a0"), name="BUY CE"), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode="markers", marker=dict(symbol="triangle-down", size=16, color="#ff4d6d"), name="BUY PE"), row=1, col=1)
        if active_trade:
            fig.add_hline(y=active_trade["target"], line_dash="dash", line_color="#00e5a0", annotation_text="Target", row=1, col=1)
            fig.add_hline(y=active_trade["sl"], line_dash="dash", line_color="#ff4d6d", annotation_text="Stop Loss", row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["MACD_Line"], line=dict(color="#2196f3", width=1.5), name="MACD"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["Signal_Line"], line=dict(color="#ff9800", width=1.5), name="Signal"), row=2, col=1)
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white", height=650, margin=dict(l=10, r=10, t=30, b=10), dragmode="pan", hovermode="x unified", showlegend=False)
        fig.update_xaxes(fixedrange=False, rangeslider_visible=False, tickformat="%H:%M")
        fig.update_yaxes(fixedrange=False)
        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True, "displaylogo": False})
        if auto_refresh:
            time.sleep(10)
            st.rerun()
    else:
        st.info("Market data is not available for today yet or it is a trading holiday.")
