"""LLM 服务：OpenAI 兼容接口（默认 DeepSeek），支持流式与 JSON 模式"""
import json
import logging
import re

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self) -> None:
        self._client = None  # 懒加载，避免无 API Key 时启动失败

    @property
    def client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            s = get_settings()
            if not s.LLM_API_KEY:
                raise RuntimeError("未配置 LLM_API_KEY，请在 .env 中填写")
            self._client = AsyncOpenAI(
                base_url=s.LLM_BASE_URL, api_key=s.LLM_API_KEY, timeout=60
            )
        return self._client

    async def chat_stream(self, messages: list[dict], temperature: float | None = None):
        """流式对话，逐段 yield 文本增量"""
        s = get_settings()
        stream = await self.client.chat.completions.create(
            model=s.LLM_MODEL,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature if temperature is not None else s.LLM_TEMPERATURE,
            max_tokens=s.LLM_MAX_TOKENS,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_json(self, system: str, user: str, temperature: float | None = None) -> dict:
        """JSON 模式（意图识别等结构化输出），带一次重试与鲁棒解析"""
        s = get_settings()
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for attempt in range(2):
            try:
                resp = await self.client.chat.completions.create(
                    model=s.LLM_MODEL,
                    messages=messages,  # type: ignore[arg-type]
                    temperature=temperature if temperature is not None else 0.1,
                    max_tokens=300,
                    response_format={"type": "json_object"},
                )
                content = resp.choices[0].message.content or "{}"
                return self._parse_json(content)
            except Exception:
                logger.warning("chat_json 第 %s 次调用失败", attempt + 1, exc_info=True)
        return {}

    @staticmethod
    def _parse_json(content: str) -> dict:
        content = content.strip()
        # 去掉可能的 markdown 代码块包裹
        content = re.sub(r"^```(json)?|```$", "", content, flags=re.M).strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return {}


llm_service = LLMService()
