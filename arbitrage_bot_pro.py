import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import ccxt.async_support as ccxt
from notion_client import Client
import requests

load_dotenv()

DRY_RUN = os.getenv('DRY_RUN', 'True').lower() == 'true'
NANOBOT_URL = os.getenv('NANOBOT_URL')

binance = ccxt.binance({'apiKey': os.getenv('BINANCE_API'), 'secret': os.getenv('BINANCE_SECRET'), 'enableRateLimit': True, 'options': {'defaultType': 'spot'}, 'timeout': 30000})
okx = ccxt.okx({'apiKey': os.getenv('OKX_API'), 'secret': os.getenv('OKX_SECRET'), 'enableRateLimit': True, 'options': {'defaultType': 'spot'}, 'timeout': 30000})

notion = Client(auth=os.getenv('NOTION_TOKEN'))
DB_ID = os.getenv('NOTION_DB_ID')

FEE = 0.001
SLIPPAGE_BUFFER = 0.002
MIN_PROFIT = 0.006
TRADE_AMOUNT_USDT = 50

def write_to_notion(type_, content, profit=0, exchange=""):
    try:
        notion.pages.create(parent={"database_id": DB_ID}, properties={
            "Date": {"date": {"start": datetime.now().isoformat()}},
            "Type": {"select": {"name": type_}},
            "Content": {"rich_text": [{"text": {"content": str(content)[:2000]}}]},
            "Profit": {"number": round(float(profit), 4)},
            "Exchange": {"select": {"name": exchange}}
        })
        print(f"Notion 写入成功: {type_}")
    except Exception as e:
        print(f"Notion 写入失败: {e}")

async def triangular_loop(ex, name):
    while True:
        try:
            await ex.load_markets()
            tickers = await ex.fetch_tickers(['BTC/USDT', 'ETH/BTC', 'ETH/USDT'])
            btc_ask = tickers['BTC/USDT']['ask']
            eth_btc_ask = tickers['ETH/BTC']['ask']
            eth_bid = tickers['ETH/USDT']['bid']
            ratio = eth_bid / (btc_ask * eth_btc_ask)
            profit = ratio - 1
            print(f"{name} 实时价格: BTC/USDT={btc_ask:.2f} | ETH/BTC={eth_btc_ask:.6f} | ETH/USDT={eth_bid:.2f} → 利润率 {profit:.4%}")
            if profit > MIN_PROFIT + SLIPPAGE_BUFFER:
                msg = f"{name} 三角套利 真实利润率 {profit:.4%}"
                print(msg)
                write_to_notion("交易明细", msg, profit * TRADE_AMOUNT_USDT, name)
                if not DRY_RUN: print("✅ 执行订单")
        except Exception as e:
            print(f"{name} 循环错误: {type(e).__name__}")
        await asyncio.sleep(5)

async def cross_loop():
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    while True:
        try:
            bin_t = await binance.fetch_tickers(symbols)
            okx_t = await okx.fetch_tickers(symbols)
            for sym in symbols:
                bt = bin_t.get(sym)
                ot = okx_t.get(sym)
                if not (bt and ot and bt.get('bid') and bt.get('ask') and ot.get('bid') and ot.get('ask')): continue
                p_bin = (bt['bid'] + bt['ask']) / 2
                p_okx = (ot['bid'] + ot['ask']) / 2
                diff = abs(p_bin - p_okx) / ((p_bin + p_okx) / 2)
                if diff > 0.0065 + 2 * FEE + SLIPPAGE_BUFFER:
                    msg = f"跨CEX {sym} 差价 {diff:.4%}"
                    print(msg)
                    write_to_notion("交易明细", msg, diff * TRADE_AMOUNT_USDT, "Cross")
        except Exception as e:
            print(f"跨CEX 循环错误: {type(e).__name__}")
        await asyncio.sleep(5)

async def daily_summary():
    while True:
        await asyncio.sleep(60)
        if datetime.now().hour == 23 and datetime.now().minute == 0:
            full_summary = f"🚀 每日套利总结\n日期：{datetime.now().date()}\n详见 Notion 数据库"
            write_to_notion("每日总结", full_summary)
            print(full_summary)
            if NANOBOT_URL:
                requests.post(NANOBOT_URL + "/trigger", json={"prompt": f"请美化后推送到 QQ：\n{full_summary}"})
                print("✅ 已推送到 QQ")

async def main():
    print("🚀 机器人启动（DRY_RUN=" + str(DRY_RUN) + "）")
    try:
        await asyncio.gather(triangular_loop(binance, "Binance"), triangular_loop(okx, "OKX"), cross_loop(), daily_summary())
    finally:
        await binance.close()
        await okx.close()

if __name__ == "__main__":
    asyncio.run(main())
