import logging
import tempfile
from pathlib import Path

import httpx
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        logger.info("Loading Whisper model (first time takes a few minutes)...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _model


async def transcribe_audio(media_url: str) -> str:
    """Download audio from URL and transcribe to Hebrew text."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(media_url)
            response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(response.content)
            audio_path = f.name

        model = _get_model()
        segments, info = model.transcribe(audio_path, language="he")
        text = " ".join(seg.text.strip() for seg in segments)

        Path(audio_path).unlink(missing_ok=True)

        logger.info("Transcribed %ds of audio → %d chars", int(info.duration), len(text))
        return text

    except Exception as exc:
        logger.error("Whisper transcription failed: %s", exc)
        return ""
