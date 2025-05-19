from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import time
import telebot
import requests
from datetime import datetime, timezone
import os
import matplotlib.pyplot as plt
import mplfinance as mpf

API_TOKEN = '8101318218:AAFTBP-D827m3GI3QPFk7KjqIR4j6zU0g9k'
CHAT_ID = '7248790632'
FMP_API_KEY = 'WJjcggzQs1iTnWniHLKrvXqIsueD7L2i'

username = 'ambimuhammad'
password = 'PamulangMeruyung2!'

bot = telebot.TeleBot(API_TOKEN)
tv = TvDatafeed(username, password)

def send_signal(message, df):
    print("Kirim sinyal:", message)
    df.index = pd.to_datetime(df['datetime'])
    df_plot = df[['open', 'high', 'low', 'close']].copy()
    df_plot.columns = ['Open', 'High', 'Low', 'Close']
    chart_file = '/tmp/chart.png'
    mpf.plot(df_plot[-50:], type='candle', style='charles', volume=False, savefig=chart_file)
    with open(chart_file, 'rb') as photo:
        bot.send_photo(CHAT_ID, photo, caption=message)

def get_trend_h1():
    df_h1 = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_1_hour, n_bars=50)
    if df_h1 is None or df_h1.empty:
        return None
    df_h1['ema50'] = df_h1['close'].ewm(span=50).mean()
    trend = 'bullish' if df_h1['close'].iloc[-1] > df_h1['ema50'].iloc[-1] else 'bearish'
    return trend

def is_engulfing(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    bullish = (
        prev['close'] < prev['open'] and
        last['close'] > last['open'] and
        last['open'] < prev['close'] and
        last['close'] > prev['open']
    )
    bearish = (
        prev['close'] > prev['open'] and
        last['close'] < last['open'] and
        last['open'] > prev['close'] and
        last['close'] < prev['open']
    )
    return 'bullish' if bullish else 'bearish' if bearish else None

def detect_order_block(df, bullish=True):
    try:
        if bullish:
            return (
                df['close'].iloc[-4] < df['open'].iloc[-4] and
                df['close'].iloc[-3] > df['open'].iloc[-3] and
                df['close'].iloc[-2] > df['open'].iloc[-2]
            )
        else:
            return (
                df['close'].iloc[-4] > df['open'].iloc[-4] and
                df['close'].iloc[-3] < df['open'].iloc[-3] and
                df['close'].iloc[-2] < df['open'].iloc[-2]
            )
    except:
        return False

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_macd(df):
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

def check_fundamentals(api_key):
    try:
        now = datetime.now(timezone.utc)
        today = now.strftime('%Y-%m-%d')
        url = f'https://financialmodelingprep.com/api/v3/economic_calendar?from={today}&to={today}&apikey={api_key}'
        res = requests.get(url)
        data = res.json()
        for event in data:
            if event.get('importance') == 'High':
                event_time_str = f"{event.get('date', today)} {event.get('time', '00:00:00')}"
                try:
                    event_time = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except:
                    continue
                if 0 <= (event_time - now).total_seconds() <= 3600:
                    print(f"⚠️ Upcoming High Impact News: {event.get('event')} at {event.get('time')}")
                    return False
        return True
    except Exception as e:
        print("Fundamental check error:", e)
        return True

while True:
    try:
        trend_h1 = get_trend_h1()
        if trend_h1 is None:
            print("❌ Tidak bisa menentukan trend H1")
            time.sleep(60)
            continue

        df = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_5_minute, n_bars=50)
        if df is None or df.empty:
            print("❌ Data kosong dari TradingView")
            time.sleep(60)
            continue

        pattern = is_engulfing(df)
        if not pattern:
            time.sleep(60)
            continue

        if pattern != trend_h1:
            print(f"📉 Sinyal {pattern} tidak searah dengan trend H1 ({trend_h1})")
            time.sleep(60)
            continue

        if not check_fundamentals(FMP_API_KEY):
            print("⏸ Fundamental tidak mendukung — sinyal dibatalkan.")
            time.sleep(60)
            continue

        if pattern == 'bullish' and not detect_order_block(df, bullish=True):
            print("❌ Tidak ada bullish order block")
            time.sleep(60)
            continue
        elif pattern == 'bearish' and not detect_order_block(df, bullish=False):
            print("❌ Tidak ada bearish order block")
            time.sleep(60)
            continue

        rsi = calculate_rsi(df)
        macd, signal = calculate_macd(df)
        if pattern == 'bullish' and (rsi < 50 or macd < signal):
            print("📉 RSI atau MACD tidak mendukung bullish")
            time.sleep(60)
            continue
        elif pattern == 'bearish' and (rsi > 50 or macd > signal):
            print("📈 RSI atau MACD tidak mendukung bearish")
            time.sleep(60)
            continue

        entry = df['close'].iloc[-1]
        sl = entry - 3 if pattern == 'bullish' else entry + 3
        tp = entry + 5 if pattern == 'bullish' else entry - 5

        msg = (
            f"{'🟢 BUY' if pattern == 'bullish' else '🔴 SELL'} XAU/USD (Scalping 5m)
"
            f"📍 Entry: {entry:.2f}\n"
            f"🛑 SL: {sl:.2f}\n"
            f"🎯 TP: {tp:.2f}\n"
            f"📊 Pattern: {pattern.title()} Engulfing + OB\n"
            f"🕐 Trend H1: {trend_h1.title()}\n"
            f"🌐 Data: OANDA via TradingView\n"
            f"📰 News Checked ✅\n"
            f"📈 RSI: {rsi:.2f} | 📊 MACD: {macd:.2f} | Signal: {signal:.2f}"
        )
        send_signal(msg, df)
        time.sleep(300)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)
