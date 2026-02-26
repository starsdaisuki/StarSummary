"""DeepSeek API 总结实现"""

import time

from star_summary.models import SummaryResult
from star_summary.summarizer.base import AbstractSummarizer
from star_summary.utils import log_step, log_info, log_success, log_error, log_warn


class DeepSeekSummarizer(AbstractSummarizer):
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    _DEFAULT_SYSTEM_PROMPT = "你是一个专业的内容总结助手，擅长从视频转录文本中提取关键信息。"

    _DEFAULT_USER_PROMPT = """请对以下视频/音频转录文本进行总结。要求：
1. 先用一两句话概括核心主题
2. 然后分点列出关键内容和要点
3. 如果有重要的观点、数据或结论，请特别标注
4. 保持简洁，用中文回答

转录文本：
{text}"""

    def summarize(self, text: str, system_prompt: str | None = None) -> SummaryResult:
        try:
            from openai import OpenAI
        except ImportError:
            log_error("openai package not installed")
            log_info("Install it: uv add openai")
            raise RuntimeError("openai not installed")

        log_step("🤖", "Summarizing with DeepSeek...")

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com",
        )

        # 文本过长时截断
        max_chars = 60000
        if len(text) > max_chars:
            log_warn(f"Transcript too long ({len(text)} chars), truncating to {max_chars}")
            text = text[:max_chars]

        if system_prompt:
            sys_msg = system_prompt
            user_prompt = f"请根据要求处理以下转录文本，用中文回答。\n\n转录文本：\n{text}"
        else:
            sys_msg = self._DEFAULT_SYSTEM_PROMPT
            user_prompt = self._DEFAULT_USER_PROMPT.format(text=text)

        try:
            t0 = time.time()
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            elapsed = time.time() - t0
            summary_text = response.choices[0].message.content or ""
            log_success(f"Summary generated in {elapsed:.1f}s")

            return SummaryResult(
                text=summary_text,
                model="deepseek-chat",
                summarize_time=elapsed,
            )

        except Exception as e:
            log_error(f"DeepSeek API error: {e}")
            return SummaryResult(text="", model="deepseek-chat")
