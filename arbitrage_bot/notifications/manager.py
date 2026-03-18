import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)

class NotificationManager:
    def __init__(self):
        """只保留 nanobot（Lark）推送"""
        self.nanobot_url = os.getenv('NANOBOT_URL')
        logger.info("通知管理器初始化完成（已切换到 Lark）")

    async def _trigger_lark(self, message: str):
        """统一推送到 Lark（通过 nanobot）"""
        try:
            import requests
            if not self.nanobot_url:
                logger.warning("NANOBOT_URL 未配置")
                return
            
            payload = {
                "prompt": f"请用中文美化并推送到 Lark 单聊：\n{message}\n添加标题和表情🚀"
            }
            
            response = requests.post(
                f"{self.nanobot_url}/trigger",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info("✅ 已成功推送到 Lark")
            
        except Exception as e:
            logger.error(f"Lark 推送失败: {e}")

    async def test_connections(self) -> dict:
        """测试连接（占位函数）"""
        return {"lark": True, "nanobot_url": bool(self.nanobot_url)}
