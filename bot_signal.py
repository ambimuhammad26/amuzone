import MetaTrader5 as mt5
import pandas as pd
import time
import telebot
import matplotlib.pyplot as plt
import mplfinance as mpf
from datetime import datetime

# === KONFIGURASI ===
TELEGRAM_TOKEN = '8101318218:AAFTBP-D827m3GI3QPFk7KjqIR4j6zU0g9k'
CHAT_ID = '7248790632'
SYMBOL = 'XAUUSD'
MAX_SL_PIP = 50  # 50 pip = 5.0 USD untuk XAUUSD (1 pip = 0.1 USD)
MAX_SL = MAX_SL_PIP * 0.1  # 5.0 USD max SL

# === INIT TELEGRAM DAN MT5 ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)
if not mt5.initialize():
    print("❌ Gagal inisialisasi MetaTrader5")
    exit()

# === HELPER FUNCTION ===
def get_candles(symbol, timeframe, n=100):
    tf_map = {
        '5m': mt5.TIMEFRAME_M5,
        '1h': mt5.TIMEFRAME_H1
    }
    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, n)
    
    if rates is None or len(rates) == 0:
        print(f"❌ Gagal mengambil data {symbol} timeframe {timeframe}")
        return None

    df = pd.DataFrame(rates)
    if 'time' not in df.columns:
        print("❌ Kolom 'time' tidak ditemukan pada data")
        return None
    
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    return df

def send_signal(message, df):
    df_plot = df[['open', 'high', 'low', 'close']].copy()
    df_plot.columns = ['Open', 'High', 'Low', 'Close']
    chart_path = '/tmp/chart.png'
    mpf.plot(df_plot[-50:], type='candle', style='charles', volume=False, savefig=chart_path)
    with open(chart_path, 'rb') as chart:
        bot.send_photo(CHAT_ID, chart, caption=message)

def get_trend_h1(symbol):
    df = get_candles(symbol, '1h', 100)
    if df is None or df.empty:
        return None
    df['ema50'] = df['close'].ewm(span=50).mean()
    return 'bullish' if df['close'].iloc[-1] > df['ema50'].iloc[-1] else 'bearish'

def is_engulfing(df):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    bullish = (prev['close'] < prev['open'] and curr['close'] > curr['open'] and curr['open'] < prev['close'] and curr['close'] > prev['open'])
    bearish = (prev['close'] > prev['open'] and curr['close'] < curr['open'] and curr['open'] > prev['close'] and curr['close'] < prev['open'])
    return 'bullish' if bullish else 'bearish' if bearish else None

def detect_market_structure(df):
    highs = df['high'].rolling(3).max()
    lows = df['low'].rolling(3).min()
    hh = highs.iloc[-1] > highs.iloc[-2]
    hl = lows.iloc[-1] > lows.iloc[-2]
    lh = highs.iloc[-1] < highs.iloc[-2]
    ll = lows.iloc[-1] < lows.iloc[-2]
    if hh and hl:
        return 'bullish'
    elif lh and ll:
        return 'bearish'
    else:
        return 'ranging'

def get_sr_levels(df):
    high = df['high'].rolling(20).max().iloc[-1]
    low = df['low'].rolling(20).min().iloc[-1]
    return high, low

def get_sd_zones(df):
    # Kasar: gunakan swing high / low terakhir sebagai supply & demand
    supply = df['high'].iloc[-3]
    demand = df['low'].iloc[-3]
    return supply, demand

# === MAIN LOOP ===
while True:
    try:
        df = get_candles(SYMBOL, '5m', 50)
        if df is None or df.empty:
            time.sleep(30)
            continue

        trend = get_trend_h1(SYMBOL)
        if trend is None:
            print("❌ Gagal mendapatkan trend H1")
            time.sleep(30)
            continue

        engulf = is_engulfing(df)
        structure = detect_market_structure(df)
        sr_high, sr_low = get_sr_levels(df)
        supply, demand = get_sd_zones(df)
        entry = df['close'].iloc[-1]

        if trend == 'bullish' and engulf == 'bullish' and structure == 'bullish':
            sl = demand
            sl_distance = entry - sl
            if sl_distance <= 0 or sl_distance > MAX_SL:
                print(f"❌ SL BUY terlalu jauh: {sl_distance:.2f} > {MAX_SL:.2f}")
                time.sleep(30)
                continue
            tp = entry + sl_distance * 3
            confidence = 90
            message = f"""
🟢 BUY {SYMBOL} (SMC 5m)
📍 Entry: {entry:.2f}
🛑 SL: {sl:.2f} (⛔ {sl_distance:.2f})
🎯 TP: {tp:.2f} (RR 1:3)
📊 Confidence: {confidence}%
📈 Trend H1: {trend.upper()}
🔎 Confirm: Engulfing + Structure + Demand
            """
            send_signal(message, df)

        elif trend == 'bearish' and engulf == 'bearish' and structure == 'bearish':
            sl = supply
            sl_distance = sl - entry
            if sl_distance <= 0 or sl_distance > MAX_SL:
                print(f"❌ SL SELL terlalu jauh: {sl_distance:.2f} > {MAX_SL:.2f}")
                time.sleep(30)
                continue
            tp = entry - sl_distance * 3
            confidence = 90
            message = f"""
🔴 SELL {SYMBOL} (SMC 5m)
📍 Entry: {entry:.2f}
🛑 SL: {sl:.2f} (⛔ {sl_distance:.2f})
🎯 TP: {tp:.2f} (RR 1:3)
📊 Confidence: {confidence}%
📉 Trend H1: {trend.upper()}
🔎 Confirm: Engulfing + Structure + Supply
            """
            send_signal(message, df)

        time.sleep(60)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)
