import os
import requests
from datetime import datetime, timedelta
from notion_client import Client
import logging

logger = logging.getLogger(__name__)

class DailyAnalyzer:
    """每日分析器（替代外部 nanobot）"""
    
    def __init__(self):
        self.notion = Client(auth=os.getenv('NOTION_TOKEN'))
        self.db_id = os.getenv('NOTION_DB_ID')
        self.lark_webhook = os.getenv('LARK_WEBHOOK')
        
    def read_yesterday_trades(self):
        """从 Notion 读取昨日交易记录"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        try:
            response = self.notion.databases.query(
                database_id=self.db_id,
                filter={
                    "and": [
                        {"property": "Date", "date": {"equals": yesterday}},
                        {"property": "Type", "select": {"equals": "每日交易记录"}}
                    ]
                }
            )
            
            if not response['results']:
                logger.info(f"昨日 ({yesterday}) 无交易记录")
                return None
                
            page = response['results'][0]
            props = page['properties']
            
            content = ""
            if props['Content']['rich_text']:
                content = props['Content']['rich_text'][0]['text']['content']
                
            profit = props['Profit']['number'] or 0
            
            return {
                'date': yesterday,
                'content': content,
                'profit': profit,
                'url': page['url']
            }
            
        except Exception as e:
            logger.error(f"读取 Notion 失败: {e}")
            return None
    
    def generate_analysis(self, record):
        """生成分析报告"""
        if not record:
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            return f"""📊 套利日报 ({yesterday})

昨日无交易记录。
机器人运行正常，但未监测到套利机会。

⏰ 生成时间: {datetime.now().strftime('%H:%M:%S')}"""
        
        # 简单解析数据
        content = record['content']
        profit = record['profit']
        
        # 提取关键数字
        total_trades = 0
        for line in content.split('\n'):
            if '总交易数:' in line:
                try:
                    total_trades = int(line.split(':')[1].strip())
                except:
                    pass
        
        emoji = "🟢" if profit > 0 else "🔴" if profit < 0 else "⚪"
        
        return f"""{emoji} 套利日报 ({record['date']})

📊 核心数据:
• 总利润: {profit:.4f} USDT
• 交易笔数: {total_trades} 笔

📝 详细记录:
{content[:800]}{'...(详见Notion)' if len(content) > 800 else ''}

💡 建议:
• {'盈利良好，保持策略' if profit > 0 else '亏损建议检查风控' if profit < 0 else '无交易，市场平静'}

⏰ 生成时间: {datetime.now().strftime('%H:%M:%S')}"""
    
    def push_to_lark(self, text):
        """推送到 Lark"""
        if not self.lark_webhook:
            logger.warning("LARK_WEBHOOK 未设置，跳过推送")
            return False
        
        try:
            payload = {
                "msg_type": "text",
                "content": {"text": text}
            }
            
            response = requests.post(
                self.lark_webhook,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("✅ 分析已推送到 Lark")
            return True
            
        except Exception as e:
            logger.error(f"推送 Lark 失败: {e}")
            return False
    
    async def run_daily_analysis(self):
        """执行完整分析流程"""
        logger.info("🔍 开始执行每日分析...")
        
        # 1. 读取记录
        record = self.read_yesterday_trades()
        
        # 2. 生成分析
        analysis = self.generate_analysis(record)
        
        # 3. 推送
        success = self.push_to_lark(analysis)
        
        if success:
            logger.info("✅ 每日分析完成并推送")
        else:
            logger.error("❌ 每日分析推送失败")
            
        return success
