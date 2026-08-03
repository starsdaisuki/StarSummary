"""配置管理 - 从环境变量和 CLI 参数构造统一配置"""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """统一配置，CLI 解析完参数后构造"""
    # 输入
    input: str = ""

    # ASR 引擎
    engine: str = "qwen"               # qwen / groq / whisper / paraformer
    whisper_model: str = "small"       # tiny/base/small/medium/large-v2/large-v3
    language: str | None = None        # zh/en/ja，None 为自动检测
    # 专有名词提示（仅 qwen 引擎）。默认空——实测乱给 context 会把本来对的词带偏，
    # 只在明确知道音频里有哪些人名/术语时才填，且要写全。
    asr_context: str = ""

    # 总结
    summarize: bool = False
    deepseek_api_key: str = ""

    # 下载
    cookies: str | None = None
    cookies_from_browser: str | None = None

    # 输出
    output_dir: str = "./star_summary_output"
    keep_audio: bool = False
    copy: bool = False

    # API Keys (从环境变量读取)
    groq_api_key: str = ""
    dashscope_api_key: str = ""

    def __post_init__(self) -> None:
        """从环境变量补充未设置的值"""
        if not self.groq_api_key:
            self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        if not self.dashscope_api_key:
            self.dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not self.deepseek_api_key:
            self.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.cookies:
            env_cookies = os.environ.get("STAR_SUMMARY_COOKIES", "")
            if env_cookies:
                self.cookies = env_cookies
