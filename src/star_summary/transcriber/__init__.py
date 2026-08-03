"""转录模块 - 根据引擎选择转录器"""

from star_summary.transcriber.base import AbstractTranscriber
from star_summary.transcriber.groq import GroqTranscriber
from star_summary.transcriber.paraformer import ParaformerTranscriber
from star_summary.transcriber.qwen import QwenASRTranscriber
from star_summary.transcriber.whisper_local import WhisperLocalTranscriber

# 引擎清单（Web UI / CLI 共用，改这里两边一起生效）
ENGINES: dict[str, dict[str, str]] = {
    "qwen": {
        "label": "阿里 qwen3-asr-flash（中文首选 ⭐）",
        "desc": "中文/歌曲/术语最准，不编字幕水印；需 DASHSCOPE_API_KEY",
    },
    "groq": {
        "label": "Groq whisper-large-v3",
        "desc": "英文够用、免费额度大；中文同音词错误多且会幻觉",
    },
    "whisper": {
        "label": "本地 faster-whisper",
        "desc": "离线不上传，吃本机 CPU、慢且发热，仅在断网时用",
    },
    "paraformer": {
        "label": "阿里 fun-asr-realtime（旧）",
        "desc": "老引擎，保留兼容，新用途请选 qwen",
    },
}

DEFAULT_ENGINE = "qwen"


def get_transcriber(engine: str = DEFAULT_ENGINE, **kwargs) -> AbstractTranscriber:
    """
    engine="qwen"       → QwenASRTranscriber（默认，阿里 qwen3-asr-flash，中文最准）
    engine="groq"       → GroqTranscriber（云端 whisper-large-v3，免费额度、不要外币卡）
    engine="whisper"    → WhisperLocalTranscriber（本地 faster-whisper）
    engine="paraformer" → ParaformerTranscriber（阿里旧实时引擎，兼容保留）
    """
    if engine == "qwen":
        return QwenASRTranscriber(
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("qwen_model", "qwen3-asr-flash"),
            context=kwargs.get("context", ""),
        )
    elif engine == "groq":
        return GroqTranscriber(
            api_key=kwargs.get("groq_api_key", ""),
            model=kwargs.get("groq_model", "whisper-large-v3"),
        )
    elif engine == "whisper":
        model_size = kwargs.get("model", "small")
        return WhisperLocalTranscriber(model_size=model_size)
    elif engine == "paraformer":
        api_key = kwargs.get("api_key", "")
        asr_model = kwargs.get("asr_model", "fun-asr-realtime")
        return ParaformerTranscriber(api_key=api_key, model=asr_model)
    else:
        raise ValueError(
            f"Unknown engine: {engine}. Use one of: {', '.join(ENGINES)}."
        )
