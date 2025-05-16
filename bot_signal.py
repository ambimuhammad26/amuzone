import os
import requests
import time
import pandas as pd
import numpy as np
import telebot

# Ambil dari env vars Render
API_TOKEN = os.getenv('API_TOKEN')
CHAT_ID = os.getenv('CHAT_ID')

bot = telebot.TeleBot(API_TOKEN)

SYMBOL = 'XAUUSDT'
INTERVAL = '5m'
LIMIT = 50

EMA_FAST_PERIOD = 10
EMA_SLOW_PERIOD = 50
RSI_PERIOD = 14
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
STOP_LOSS_PIPS = 30

def get_klines(symbol, interval, limit=50):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=['open_time', 'open', 'high', 'low', 'close', 'volume',
                                     'close_time', 'quote_asset_vol', 'trades', 'taker_buy_base',
                                     'taker_buy_quote', 'ignore'])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)
    return df

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def is_bullish_engulfing(df):
    prev_open = df['open'].iloc[-2]
    prev_close = df['close'].iloc[-2]
    curr_open = df['open'].iloc[-1]
    curr_close = df['close'].iloc[-1]
    return prev_close < prev_open and curr_close > curr_open and curr_open < prev_close and curr_close > prev_open

def is_bearish_engulfing(df):
    prev_open = df['open'].iloc[-2]
    prev_close = df['close'].iloc[-2]
    curr_open = df['open'].iloc[-1]
    curr_close = df['close'].iloc[-1]
    return prev_close > prev_open and curr_close < curr_open and curr_open > prev_close and curr_close < prev_open

def detect_order_block(df, bullish=True):
    if bullish:
        return (df['close'].iloc[-4] < df['open'].iloc[-4] and
                df['close'].iloc[-3] > df['open'].iloc[-3] and
                df['close'].iloc[-2] > df['open'].iloc[-2])
    else:
        return (df['close'].iloc[-4] > df['open'].iloc[-4] and
                df['close'].iloc[-3] < df['open'].iloc[-3] and
                df['close'].iloc[-2] < df['open'].iloc[-2])

def send_signal(signal_type, entry, tp, sl, pattern, ema_fast, ema_slow, rsi_val):
    text = (
        f"{'🟢' if signal_type=='BUY' else '🔴'} *{signal_type} Signal XAU/USD*\n"
        f"⏳ Timeframe: 5m\n"
        f"📊 Pattern: {pattern}\n"
        f"📍 Entry: {entry:.2f}\n"
        f"🎯 TP: {tp:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"📈 EMA: {ema_fast:.2f}/{ema_slow:.2f} | RSI: {rsi_val:.2f}"
    )
    bot.send_message(CHAT_ID, text, parse_mode='Markdown')

def main():
    last_signal = None
    while True:
        try:
            df = get_klines(SYMBOL, INTERVAL, LIMIT)
            df['ema_fast'] = ema(df['close'], EMA_FAST_PERIOD)
            df['ema_slow'] = ema(df['close'], EMA_SLOW_PERIOD)
            df['rsi'] = rsi(df['close'], RSI_PERIOD)

            ema_fast = df['ema_fast'].iloc[-1]
            ema_slow = df['ema_slow'].iloc[-1]
            rsi_val = df['rsi'].iloc[-1]
            close_price = df['close'].iloc[-1]

            if (ema_fast > ema_slow and
                rsi_val < RSI_OVERSOLD and
                is_bullish_engulfing(df) and
                detect_order_block(df, bullish=True)):

                entry = close_price
                tp = entry + STOP_LOSS_PIPS * 0.1
                sl = entry - STOP_LOSS_PIPS * 0.1
                pattern = "Bullish Engulfing + Order Block"
                signal = f"BUY_{entry}"

                if signal != last_signal:
                    send_signal('BUY', entry, tp, sl, pattern, ema_fast, ema_slow, rsi_val)
                    last_signal = signal

            elif (ema_fast < ema_slow and
                  rsi_val > RSI_OVERBOUGHT and
                  is_bearish_engulfing(df) and
                  detect_order_block(df, bullish=False)):

                entry = close_price
                tp = entry - STOP_LOSS_PIPS * 0.1
                sl = entry + STOP_LOSS_PIPS * 0.1
                pattern = "Bearish Engulfing + Order Block"
                signal = f"SELL_{entry}"

                if signal != last_signal:
                    send_signal('SELL', entry, tp, sl, pattern, ema_fast, ema_slow, rsi_val)
                    last_signal = signal

            time.sleep(300)

        except Exception as e:
            print("Error:", e)
            time.sleep(60)

if __name__ == '__main__':
    main()