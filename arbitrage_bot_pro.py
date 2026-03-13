import os
from datetime import datetime

print("=== RAILWAY 环境变量检查 ===")
print("BINANCE_API 已设置?", "是" if os.getenv('BINANCE_API') else "否（空！）")
print("BINANCE_SECRET 已设置?", "是" if os.getenv('BINANCE_SECRET') else "否（空！）")
print("OKX_API 已设置?", "是" if os.getenv('OKX_API') else "否（空！）")
print("OKX_SECRET 已设置?", "是" if os.getenv('OKX_SECRET') else "否（空！）")
print("NOTION_TOKEN 已设置?", "是" if os.getenv('NOTION_TOKEN') else "否（空！）")
print("NOTION_DB_ID 已设置?", "是" if os.getenv('NOTION_DB_ID') else "否（空！）")
print("NANOBOT_URL 已设置?", "是" if os.getenv('NANOBOT_URL') else "否（空！）")
print("DRY_RUN 值 =", os.getenv('DRY_RUN', '未设置'))
print("=== 检查结束 ===")
print(f"当前时间: {datetime.now()} - 测试代码运行正常")

# 保持运行 60 秒不崩溃
import asyncio
async def main():
    await asyncio.sleep(60)
asyncio.run(main())
