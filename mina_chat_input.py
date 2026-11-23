"""Pure adapter for Streamlit's unified text/audio chat composer.

No Streamlit dependency here: the input contract can be regression tested offline.
Audio bytes are never retained or persisted by this adapter.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatSubmission:
    text: str
    audio_wav: bytes | None
    from_microphone: bool


def extract_chat_submission(value: Any) -> ChatSubmission:
    """Accept classic string input or Streamlit ChatInputValue(text, audio).

    Explicitly typed text wins when both are supplied, avoiding unintended voice
    processing or unnecessary paid transcription. Audio-only submits once.
    """
    if value is None:
        return ChatSubmission('', None, False)
    if isinstance(value, str):
        return ChatSubmission(value.strip(), None, False)

    typed = getattr(value, 'text', None)
    if typed is None and isinstance(value, dict):
        typed = value.get('text')
    typed = typed.strip() if isinstance(typed, str) else ''
    if typed:
        return ChatSubmission(typed, None, False)

    audio = getattr(value, 'audio', None)
    if audio is None and isinstance(value, dict):
        audio = value.get('audio')
    if audio is not None:
        if isinstance(audio, bytes):
            audio_bytes = audio
        elif callable(getattr(audio, 'getvalue', None)):
            audio_bytes = audio.getvalue()
        else:
            raise ValueError('Audio recording could not be read. Try again.')
        if not isinstance(audio_bytes, bytes) or not audio_bytes:
            raise ValueError('Audio recording is empty. Try again.')
        return ChatSubmission('', audio_bytes, True)

    return ChatSubmission('', None, False)
