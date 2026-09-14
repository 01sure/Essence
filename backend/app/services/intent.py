"""意图识别与实体抽取（LLM JSON 模式）"""
import logging

from app.core.config import get_settings
from app.services.llm import llm_service

logger = logging.getLogger(__name__)

INTENTS = ["pre_sale", "order_service", "complaint", "chitchat", "human_request"]

INTENT_SYSTEM = """你是电商客服的意图识别引擎。分析用户最新消息与近期对话，输出 JSON（仅输出 JSON）：
{
  "intent": "pre_sale|order_service|complaint|chitchat|human_request",
  "order_no": "订单号，未提及则为空字符串",
  "phone": "11位手机号，未提及则为空字符串",
  "keywords": "用于检索商品的简化关键词，如 '运动手表 续航'，无则为空字符串",
  "sentiment": "positive|neutral|negative",
  "needs_human": true或false
}

意图定义：
- pre_sale: 售前咨询，商品功能、价格、对比、推荐、下单引导
- order_service: 订单售后，查订单、查物流、退换货申请、维修
- complaint: 投诉、强烈不满、要求赔偿
- chitchat: 打招呼、闲聊、无业务含义
- human_request: 用户明确要求转人工客服

判断规则：
- 用户出现退换货/物流/订单状态/保修维修等，归 order_service
- 咨询商品功能、价格、买哪个好，归 pre_sale
- 用户情绪激烈（骂人、威胁差评、要求赔偿），归 complaint 且 needs_human 通常为 true
- 明确说"转人工/真人客服"，intent=human_request
- 拿不准时偏向 pre_sale
- 简单问候或寒暄（如"你好""在吗""有人吗"）一律归 chitchat：即使近期对话中出现过转人工，也不算再次要求人工
- needs_human=true 仅当：用户当前消息明确要求人工客服，或情绪激烈需要安抚升级；历史对话要求过人工但当前消息没有，则为 false"""


class IntentService:
    async def classify(self, user_message: str, recent_dialog: str) -> dict:
        fallback = {
            "intent": "pre_sale",
            "order_no": "",
            "phone": "",
            "keywords": user_message[:50],
            "sentiment": "neutral",
            "needs_human": False,
        }
        # 兜底：无 API Key 或调用失败时走规则
        try:
            user_content = (
                f"近期对话：\n{recent_dialog}\n\n用户最新消息：{user_message}"
                if recent_dialog
                else f"用户最新消息：{user_message}"
            )
            result = await llm_service.chat_json(INTENT_SYSTEM, user_content)
        except Exception:
            logger.warning("意图识别 LLM 调用失败，使用规则兜底")
            return self._rule_based(user_message, fallback)

        intent = result.get("intent")
        if intent not in INTENTS:
            return self._rule_based(user_message, fallback)
        # 关键词强制转人工
        for kw in get_settings().handoff_keywords_list:
            if kw in user_message:
                result["intent"] = "human_request"
                result["needs_human"] = True
                break
        return result

    @staticmethod
    def _rule_based(user_message: str, fallback: dict) -> dict:
        msg = user_message.lower()
        if any(k in user_message for k in get_settings().handoff_keywords_list):
            return {**fallback, "intent": "human_request", "needs_human": True}
        if any(k in msg for k in ("订单", "物流", "快递", "退货", "换货", "退款", "保修", "维修")):
            return {**fallback, "intent": "order_service"}
        if any(k in msg for k in ("投诉", "骗子", "差评", "315")):
            return {**fallback, "intent": "complaint", "sentiment": "negative"}
        if any(k in msg for k in ("你好", "您好", "hi", "hello", "在吗", "嗨")) and len(msg) <= 8:
            return {**fallback, "intent": "chitchat", "keywords": ""}
        return fallback


intent_service = IntentService()
