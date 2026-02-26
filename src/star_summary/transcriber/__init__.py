"""转录模块 - 根据引擎选择转录器"""

from star_summary.transcriber.base import AbstractTranscriber
from star_summary.transcriber.paraformer import ParaformerTranscriber
from star_summary.transcriber.whisper_local import WhisperLocalTranscriber


def get_transcriber(engine: str = "paraformer", **kwargs) -> AbstractTranscriber:
    """
    engine="paraformer" → ParaformerTranscriber（默认）
    engine="whisper"    → WhisperLocalTranscriber
    """
    if engine == "whisper":
        model_size = kwargs.get("model", "small")
        return WhisperLocalTranscriber(model_size=model_size)
    elif engine == "paraformer":
        api_key = kwargs.get("api_key", "")
        return ParaformerTranscriber(api_key=api_key)
    else:
        raise ValueError(f"Unknown engine: {engine}. Use 'paraformer' or 'whisper'.")
