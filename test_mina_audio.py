import unittest
from types import SimpleNamespace
from mina_audio import (
    MAX_RECORDING_BYTES, MAX_SPOKEN_CHARACTERS, STT_MODEL, TTS_MODEL,
    VoiceInputError, transcribe_wav, generate_spoken_reply,
)


class StubAudio:
    def __init__(self, text='Return library books', speech=b'mp3 audio'):
        self.calls = []
        self.transcriptions = SimpleNamespace(create=self.transcribe)
        self.speech = SimpleNamespace(create=self.speak)
        self.text = text
        self.binary = speech
    def transcribe(self, **kwargs):
        self.calls.append(('transcribe', kwargs))
        return SimpleNamespace(text=self.text)
    def speak(self, **kwargs):
        self.calls.append(('speak', kwargs))
        return SimpleNamespace(content=self.binary)


class TestMINAAudio(unittest.TestCase):
    def setUp(self):
        self.audio = StubAudio()
        self.client = SimpleNamespace(audio=self.audio)
        self.wav = b'RIFF' + b'0000' + b'WAVE' + b'abc' * 40

    def test_transcribe_is_explicit_and_uses_gpt_transcribe(self):
        self.assertEqual(transcribe_wav(self.wav, client=self.client), 'Return library books')
        label, arguments = self.audio.calls[0]
        self.assertEqual(label, 'transcribe')
        self.assertEqual(arguments['model'], STT_MODEL)
        self.assertEqual(arguments['file'][2], 'audio/wav')

    def test_reject_non_wav(self):
        with self.assertRaises(VoiceInputError):
            transcribe_wav(b'x'*200, client=self.client)
        self.assertFalse(self.audio.calls)

    def test_reject_oversized(self):
        with self.assertRaises(VoiceInputError):
            transcribe_wav(b'RIFF0000WAVE' + b'x'*MAX_RECORDING_BYTES, client=self.client)
        self.assertFalse(self.audio.calls)

    def test_reject_empty_transcript(self):
        self.audio.text = '  '
        with self.assertRaises(VoiceInputError):
            transcribe_wav(self.wav, client=self.client)

    def test_tts_only_on_demand_and_limited(self):
        audio = generate_spoken_reply('Hi.' * 3000, client=self.client, voice='coral')
        self.assertEqual(audio, b'mp3 audio')
        label, args = self.audio.calls[0]
        self.assertEqual(label, 'speak')
        self.assertEqual(args['model'], TTS_MODEL)
        self.assertLessEqual(len(args['input']), MAX_SPOKEN_CHARACTERS)

    def test_reject_unsupported_voice(self):
        with self.assertRaises(VoiceInputError):
            generate_spoken_reply('hello', client=self.client, voice='bad')
        self.assertFalse(self.audio.calls)

    def test_reject_empty_reply(self):
        with self.assertRaises(VoiceInputError):
            generate_spoken_reply('', client=self.client)

    def test_tts_read_response_supported(self):
        self.audio.binary = None
        def speak(**kw):
            return SimpleNamespace(read=lambda: b'valid mp3')
        self.audio.speech.create = speak
        self.assertEqual(generate_spoken_reply('hello', client=self.client), b'valid mp3')
