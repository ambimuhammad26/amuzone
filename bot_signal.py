import MetaTrader5 as mt5
import pandas as pd
import time
import telebot
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

# =================== KONFIGURASI =================== #
PAIRS = ['XAUUSD', 'EURUSD', 'GBPJPY']
API_TOKEN = '8101318218:AAFTBP-D827m3GI3QPFk7KjqIR4j6zU0g9k'
CHAT_ID = '7248790632'
bot = telebot.TeleBot(API_TOKEN)

# Inisialisasi koneksi MT5
if not mt5.initialize():
    print("❌ Gagal terhubung ke MetaTrader5")
    quit()

# =================== HELPER FUNCTIONS =================== #
def get_mt5_data(symbol, timeframe, bars=100):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    return df[['datetime', 'open', 'high', 'low', 'close', 'tick_volume']]

def send_signal(message, df):
    print("Kirim sinyal:", message)
    df_plot = df[['datetime', 'open', 'high', 'low', 'close']].copy()
    df_plot.set_index('datetime', inplace=True)
    df_plot.columns = ['Open', 'High', 'Low', 'Close']
    chart_file = '/tmp/chart.png'
    mpf.plot(df_plot[-50:], type='candle', style='charles', volume=False, savefig=chart_file)
    with open(chart_file, 'rb') as photo:
        bot.send_photo(CHAT_ID, photo, caption=message)

def get_trend_h1(symbol):
    df = get_mt5_data(symbol, mt5.TIMEFRAME_H1, 100)
    if df is None:
        return None
    df['ema50'] = df['close'].ewm(span=50).mean()
    return 'bullish' if df['close'].iloc[-1] > df['ema50'].iloc[-1] else 'bearish'

def detect_liquidity_sweep(df):
    high_sweep = df['high'].iloc[-1] > df['high'].iloc[-2] and df['close'].iloc[-1] < df['open'].iloc[-1]
    low_sweep = df['low'].iloc[-1] < df['low'].iloc[-2] and df['close'].iloc[-1] > df['open'].iloc[-1]
    return 'bearish' if high_sweep else 'bullish' if low_sweep else None

def detect_fvg(df):
    try:
        fvg_up = df['low'].iloc[-3] > df['high'].iloc[-1]
        fvg_down = df['high'].iloc[-3] < df['low'].iloc[-1]
        if fvg_up:
            return (True, df['low'].iloc[-3])
        elif fvg_down:
            return (True, df['high'].iloc[-3])
        else:
            return (False, None)
    except:
        return (False, None)

def estimate_volatility(df):
    return df['high'].rolling(10).max().iloc[-1] - df['low'].rolling(10).min().iloc[-1]

def detect_market_structure(df):
    last_highs = df['high'].rolling(3).max()
    last_lows = df['low'].rolling(3).min()
    higher_high = last_highs.iloc[-1] > last_highs.iloc[-2]
    higher_low = last_lows.iloc[-1] > last_lows.iloc[-2]
    lower_high = last_highs.iloc[-1] < last_highs.iloc[-2]
    lower_low = last_lows.iloc[-1] < last_lows.iloc[-2]
    if higher_high and higher_low:
        return 'bullish'
    elif lower_high and lower_low:
        return 'bearish'
    else:
        return 'ranging'

def is_engulfing(df):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    last = df.iloc[-1]
    bullish = prev['close'] < prev['open'] and last['close'] > last['open'] and last['open'] < prev['close'] and last['close'] > prev['open']
    bearish = prev['close'] > prev['open'] and last['close'] < last['open'] and last['open'] > prev['close'] and last['close'] < prev['open']
    return 'bullish' if bullish else 'bearish' if bearish else None

def is_trading_hours():
    now = datetime.now().time()
    return 8 <= now.hour <= 22

# =================== MAIN LOOP =================== #
while True:
    try:
        if not is_trading_hours():
            print("⏸ Di luar jam trading (08:00–22:00 WIB)")
            time.sleep(60)
            continue

        for symbol in PAIRS:
            trend_h1 = get_trend_h1(symbol)
            if trend_h1 is None:
                print(f"❌ Tidak bisa dapatkan trend H1 untuk {symbol}")
                continue

            df = get_mt5_data(symbol, mt5.TIMEFRAME_M5, 50)
            if df is None or df.empty:
                print(f"❌ Data kosong dari MT5 untuk {symbol}")
                continue

            sweep = detect_liquidity_sweep(df)
            if sweep != trend_h1:
                continue

            market_structure = detect_market_structure(df)
            if market_structure != trend_h1:
                continue

            engulfing = is_engulfing(df)
            if engulfing != sweep:
                continue

            fvg_ok, entry = detect_fvg(df)
            if not fvg_ok or entry is None:
                continue

            if not (df['low'].iloc[-1] <= entry <= df['high'].iloc[-1]):
                continue

            volatility = estimate_volatility(df)
            risk = volatility * 0.3
            rr = 3 if volatility < 2 else 2
            sl = entry - risk if sweep == 'bullish' else entry + risk
            tp = entry + risk * rr if sweep == 'bullish' else entry - risk * rr
            confidence = 90 if volatility < 2 else 80

            msg = f"""
{'🟢 BUY' if sweep == 'bullish' else '🔴 SELL'} {symbol} (SMC Scalping 5m)
📍 Entry (FVG): {entry:.2f}
🛑 SL: {sl:.2f}
🎯 TP: {tp:.2f} (RR ~1:{rr})
📊 Confidence: {confidence}%
🧠 Setup: Liquidity Sweep + FVG + Market Structure + Engulfing + Trend H1
🕐 Trend H1: {trend_h1.title()}
📡 Data: MT5 (Exness)
            """
            send_signal(msg, df)
            time.sleep(2)

        time.sleep(60)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)
