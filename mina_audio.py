"""Optional voice I/O for Streamlit push-to-talk.

Audio leaves the machine only after the user clicks Transcribe; not saved to disk
or appended to the audit log. TTS audio is held in Streamlit session memory.
"""
from __future__ import annotations

import os
from pathlib import Path

MAX_RECORDING_BYTES = 12 * 1024 * 1024
MAX_SPOKEN_CHARACTERS = 2600
STT_MODEL = 'gpt-transcribe'
TTS_MODEL = 'gpt-4o-mini-tts'  # Deprecated; provider schedules retirement 2027-01-06.


class VoiceInputError(ValueError):
    pass


def _client():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / '.env', override=False)
    from openai import OpenAI
    return OpenAI(timeout=40.0, max_retries=1)


def transcribe_wav(wav: bytes, *, client=None) -> str:
    """Convert one finished WAV recording to text; review it before running MINA."""
    if not isinstance(wav, bytes) or not 100 < len(wav) <= MAX_RECORDING_BYTES:
        raise VoiceInputError('Please record a shorter voice message using the microphone.')
    if not (wav.startswith(b'RIFF') and wav[8:12] == b'WAVE'):
        raise VoiceInputError('Unsupported recording format; please use Streamlit microphone WAV input.')
    client = client if client is not None else _client()
    response = client.audio.transcriptions.create(
        model=STT_MODEL,
        file=('mina_microphone.wav', wav, 'audio/wav'),
    )
    text = getattr(response, 'text', None)
    if not isinstance(text, str) or not text.strip():
        raise VoiceInputError('The recording was not understood. Try again or type your request.')
    return text.strip()


def generate_spoken_reply(text: str, *, client=None, voice: str = 'coral') -> bytes:
    """Optional speech output, requested by user; keep transcription and TTS separate."""
    if not isinstance(text, str) or not text.strip():
        raise VoiceInputError('Nothing to read aloud.')
    if voice not in {'coral', 'alloy', 'sage', 'nova', 'shimmer'}:
        raise VoiceInputError('Unsupported voice.')
    client = client if client is not None else _client()
    response = client.audio.speech.create(
        model=TTS_MODEL,
        voice=voice,
        input=text.strip()[:MAX_SPOKEN_CHARACTERS],
        response_format='mp3',
    )
    content = getattr(response, 'content', None)
    if isinstance(content, bytes) and content:
        return content
    if hasattr(response, 'read'):
        audio = response.read()
        if isinstance(audio, bytes) and audio:
            return audio
    raise VoiceInputError('Speech output could not be generated.')
