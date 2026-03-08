import os
import asyncio
import json
from datetime import datetime
from dotenv import load_dotenv
import ccxt.async_support as ccxt
from notion_client import Client
import requests

load_dotenv()

DRY_RUN = os.getenv('DRY_RUN', 'True').lower() == 'true'
NANOBOT_URL = os.getenv('NANOBOT_URL')

binance = ccxt.binance({'apiKey': os.getenv('BINANCE_API'), 'secret': os.getenv('BINANCE_SECRET'), 'enableRateLimit': True})
okx = ccxt.okx({'apiKey': os.getenv('OKX_API'), 'secret': os.getenv('OKX_SECRET'), 'enableRateLimit': True})

notion = Client(auth=os.getenv('NOTION_TOKEN'))
DB_ID = os.getenv('NOTION_DB_ID')

FEE = 0.001
SLIPPAGE_BUFFER = 0.002
MIN_PROFIT = 0.006
TRADE_AMOUNT_USDT = 50

def write_to_notion(type_, content, profit=0, exchange=""):
    notion.pages.create(parent={"database_id": DB_ID}, properties={
        "Date": {"date": {"start": datetime.now().isoformat()}},
        "Type": {"select": {"name": type_}},
        "Content": {"rich_text": [{"text": {"content": content[:2000]}}]},
        "Profit": {"number": round(float(profit), 4)},
        "Exchange": {"select": {"name": exchange}}
    })

async def triangular_loop(ex, name):
    await ex.load_markets()
    bases = ['BTC', 'ETH', 'SOL']
    quotes = ['USDT', 'BTC', 'ETH']
    triangles = []
    for b in bases:
        for q1 in quotes:
            for q2 in quotes:
                if q1 == q2: continue
                s1 = f"{b}/{q1}"
                s2 = f"{q1 if q1 != b else b}/{q2}"
                s3 = f"{q2 if q2 != b else b}/{b}"
                if all(s in ex.markets for s in [s1, s2, s3]):
                    triangles.append((s1, s2, s3))

    while True:
        try:
            tickers = await ex.fetch_tickers([s for t in triangles for s in t])
            for s1, s2, s3 in triangles:
                if not all(s in tickers for s in [s1, s2, s3]): continue
                for direction in [1, -1]:
                    if direction == 1:
                        p = (1 / tickers[s1]['bid']) * tickers[s2]['bid'] * tickers[s3]['ask']
                    else:
                        p = tickers[s1]['ask'] * (1 / tickers[s2]['ask']) * (1 / tickers[s3]['bid'])
                    profit = p - 1
                    if profit > MIN_PROFIT + SLIPPAGE_BUFFER:
                        executable = TRADE_AMOUNT_USDT * 0.95
                        profit_usdt = profit * executable
                        msg = f"{name} 三角套利 {s1}-{s2}-{s3} 利润率 {profit:.4%}"
                        print(msg)
                        write_to_notion("交易明细", msg, profit_usdt, name)
                        if not DRY_RUN:
                            print("✅ 执行订单（DRY_RUN=False 时）")
        except Exception as e:
            print(e)
        await asyncio.sleep(2)

async def cross_loop():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    while True:
        try:
            bin_t = await binance.fetch_tickers(symbols)
            okx_t = await okx.fetch_tickers(symbols)
            for sym in symbols:
                p_bin = (bin_t[sym]['bid'] + bin_t[sym]['ask']) / 2
                p_okx = (okx_t[sym]['bid'] + okx_t[sym]['ask']) / 2
                diff = abs(p_bin - p_okx) / ((p_bin + p_okx) / 2)
                if diff > 0.0065 + 2 * FEE + SLIPPAGE_BUFFER:
                    msg = f"跨CEX {sym} 差价 {diff:.4%}"
                    print(msg)
                    write_to_notion("交易明细", msg, diff * TRADE_AMOUNT_USDT, "Cross")
        except:
            pass
        await asyncio.sleep(2)

async def daily_summary():
    while True:
        await asyncio.sleep(60)
        if datetime.now().hour == 23 and datetime.now().minute == 0:
            # 简单总结（实际用 Notion 查询）
            full_summary = f"🚀 每日套利总结\n日期：{datetime.now().date()}\n详见 Notion"
            write_to_notion("每日总结", full_summary)
            if NANOBOT_URL:
                requests.post(NANOBOT_URL + "/trigger", json={"prompt": f"请美化后推送到 QQ：\n{full_summary}"})

async def main():
    print("🚀 机器人启动（DRY_RUN=" + str(DRY_RUN) + "）")
    await asyncio.gather(triangular_loop(binance, "Binance"), triangular_loop(okx, "OKX"), cross_loop(), daily_summary())

if __name__ == "__main__":
    asyncio.run(main())
