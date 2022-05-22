import time
import pyupbit
import datetime
from pytz import timezone
import requests
import math
import numpy as np
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

access = os.getenv('ACCESS')
secret = os.getenv('SECRET')
myToken = os.getenv('TOKEN')

def post_message( text, channel='#auto-trading', token=myToken):
    """슬랙 메시지 전송"""
    response = requests.post("https://slack.com/api/chat.postMessage",
        headers={"Authorization": "Bearer "+token},
        data={"channel": channel,"text": text}
    )

# 로그인
upbit = pyupbit.Upbit(access, secret)
print("autotrade start")
# 시작 메세지 슬랙 전송
post_message("autotrade start")

def get_start_time(ticker):
    """시작 시간 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
    start_time = df.index[0]
    return start_time

def get_balance(ticker):
    """잔고 조회"""
    balances = upbit.get_balances()
    for b in balances:
        if b['currency'] == ticker:
            if b['balance'] is not None:
                return float(b['balance'])
            else:
                return 0
    return 0

def get_current_price(ticker):
    """현재가 조회"""
    return pyupbit.get_orderbook(ticker=ticker)["orderbook_units"][0]["ask_price"]

def get_ror(df, strategy='normal', k=0.5):    
    df = df.copy()
    df['range'] = (df['high'] - df['low']) * k
    df['target'] = df['open'] + df['range'].shift(1)
    
    df['ma5'] = df['close'].rolling(window=5).mean().shift(1)
    df['short_ema'] = df['close'].ewm(span=12).mean()
    df['long_ema'] = df['close'].ewm(span=26).mean()
    
    df['macd'] = df['short_ema'] - df['long_ema']
    df['signal'] = df['macd'].ewm(span=9).mean()
    
    ma5_bull = df['open'] > df['ma5']
    ema5_bull = df['open'] > df['long_ema']
    
    macd_bull = df['macd'] > df['signal']
    
    df['bull'] = True
    
    if strategy=='ma':
        df['bull'] = ma5_bull
    elif strategy=='ema':
        df['bull'] = ema5_bull
    elif strategy=='macd':
        df['bull'] = macd_bull
    else:
        df['bull'] = True
    
    fee = 0.0032
    
    df['ror'] = np.where((df['close'] > df['target']) & df['bull'], df['close'] / df['target'] - fee, 1)
    df['hpr'] = df['ror'].cumprod()
    df['dd'] = (df['hpr'].cummax() - df['hpr']) / df['hpr'].cummax() * 100
    df['mdd'] = df['dd'].max()

    return (df, df['hpr'][-2])

def get_best_k(df, strategy='normal'):
    best_k = 0.1
    c_ror = 0
    for i in np.arange(0.1, 1.0, 0.1):
        (_,ror) = get_ror(df, strategy=strategy, k=i)
        
        if(ror > c_ror):
            best_k = i
            c_ror = ror
    return best_k

def get_best(strategy, now):
    hprs = []
    tickers = pyupbit.get_tickers('KRW')
    
    past = '%d-%d' % (now.year, (now.month - 1))

    for i in range(len(tickers)):
        ticker = tickers[i]
        data = pyupbit.get_ohlcv(ticker, count=2000)
        if past in data.index:
            data = data.loc[past]
            k = get_best_k(data, strategy = strategy)
            (df, hpr) = get_ror(data, strategy=strategy, k=k)
            hprs.append((ticker, hpr, k))

    sorted_hpr = sorted(hprs, key=lambda x:x[1], reverse=True)
    return sorted_hpr[0]

def get_target_price(ticker, k):
    """변동성 돌파 전략으로 매수 목표가 조회"""
    df = pyupbit.get_ohlcv(ticker, interval="day", count=2)
    target_price = df.iloc[0]['close'] + (df.iloc[0]['high'] - df.iloc[0]['low']) * k
    return target_price

def get_macd_condition(ticker):
    df = pyupbit.get_ohlcv(ticker, interval='day', count=26)
    
    df['short_ema'] = df['close'].ewm(span=12).mean()
    df['long_ema'] = df['close'].ewm(span=26).mean()
    
    df['macd'] = df['short_ema'] - df['long_ema']
    df['signal'] = df['macd'].ewm(span=9).mean()

    df['bool'] = df['macd'] - df['signal']
    
    return df['bool'].iloc[-1]

past_best = pd.read_csv('../best_ticker.csv')

if past_best.count().normal_ticker != 1 :
    now = datetime.datetime.now(timezone('Asia/Seoul'))
    (normal_ticker, _, normal_k) = get_best('normal', now)
    (macd_ticker, _, macd_k) = get_best('macd', now)

else:
    normal_ticker = past_best.normal_ticker.iloc[0]
    normal_k = past_best.normal_k.iloc[0]
    macd_ticker = past_best.macd_ticker.iloc[0]
    macd_k = past_best.macd_k.iloc[0]

print('Current ticker(only Volatility) : %s, k : %.1f' % (normal_ticker, normal_k))
post_message('Current ticker(only Volatility) : %s, k : %.1f' % (normal_ticker, normal_k))
print('Current ticker(Volatility + MACD) : %s, k : %.1f' % (macd_ticker, macd_k))
post_message('Current ticker(Volatility + MACD) : %s, k : %.1f' % (macd_ticker, macd_k))

while True:
    try:
        now = datetime.datetime.now(timezone('Asia/Seoul'))
        start_time = get_start_time("KRW-BTC")
        end_time = start_time + datetime.timedelta(days=1)
        
        if now.day == 1:
            (normal_ticker, _, normal_k) = get_best('normal', now)
            (macd_ticker, _, macd_k) = get_best('macd', now)
            print('Current ticker(only Volatility) : %s, k : %.1f' % (normal_ticker, normal_k))
            post_message('Current ticker(only Volatility) : %s, k : %.1f' % (normal_ticker, normal_k))
            print('Current ticker(only Volatility) : %s, k : %.1f' % (macd_ticker, macd_k))
            post_message('Current ticker(only Volatility) : %s, k : %.1f' % (macd_ticker, macd_k))

            headers = ['normal_ticker', 'normal_k', 'macd_ticker','macd_k']
            csv_data = pd.DataFrame([[normal_ticker, normal_k, macd_ticker, macd_k]], columns=headers)
            csv_data.to_csv('../best_ticker.csv', index=False)

        if start_time < now < end_time - datetime.timedelta(seconds=10):
            # 변동성 매매만
            normal_target = get_target_price(normal_ticker, normal_k)
            current_normal_price = get_current_price(normal_ticker)

            if normal_target < current_normal_price:
                krw = get_balance('KRW') / 2
                if krw > 10000:
                    buy_result = upbit.buy_market_order(normal_ticker, krw*0.9995)
                    post_message(normal_ticker+' buy : '+str(buy_result))

            # 변동성 + MACD
            macd_target = get_target_price(macd_ticker, macd_k)
            macd_condition = get_macd_condition(macd_ticker)
            current_macd_price = get_current_price(macd_ticker)

            if macd_target < current_macd_price and macd_condition:
                krw = get_balance('KRW')
                if krw > 10000:
                    buy_result = upbit.buy_market_order(macd_ticker, krw * 0.9995)
                    post_message(macd_ticker + 'buy : ' + str(buy_result))
        else:
            normal_coin = get_balance(normal_ticker.split('-')[1])
            macd_coin = get_balance(macd_ticker.split('-')[1])
            
            normal_market_condition = get_current_price(normal_ticker) * normal_coin
            macd_market_condition = get_current_price(macd_ticker) * macd_coin

            if normal_market_condition > 5000:
                sell_result = upbit.sell_market_order(normal_ticker, normal_coin * 0.9995)
                post_message(nomral_ticker + ' buy : ' + str(sell_result))

            if macd_market_condition > 5000:
                sell_result = upbit.sell_market_order(macd_ticker, macd_coin * 0.9995)
                post_message(macd_ticker + ' buy : ' + str(sell_result))

        time.sleep(1)
    except Exception as e:
        print(e)
        post_message( e)
        time.sleep(1)