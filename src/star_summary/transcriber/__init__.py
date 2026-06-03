"""转录模块 - 根据引擎选择转录器"""

from star_summary.transcriber.base import AbstractTranscriber
from star_summary.transcriber.groq import GroqTranscriber
from star_summary.transcriber.paraformer import ParaformerTranscriber
from star_summary.transcriber.whisper_local import WhisperLocalTranscriber


def get_transcriber(engine: str = "groq", **kwargs) -> AbstractTranscriber:
    """
    engine="groq"       → GroqTranscriber（默认，云端 whisper-large-v3，免费额度、不要外币卡）
    engine="paraformer" → ParaformerTranscriber（阿里云实时，超长音频兜底）
    engine="whisper"    → WhisperLocalTranscriber（本地 faster-whisper）
    """
    if engine == "groq":
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
        raise ValueError(f"Unknown engine: {engine}. Use 'groq', 'paraformer' or 'whisper'.")
