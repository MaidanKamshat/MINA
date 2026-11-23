import unittest
from types import SimpleNamespace
from mina_chat_input import extract_chat_submission


class FakeAudio:
    def getvalue(self):
        return b'RIFF' + b'\x00' * 4 + b'WAVE' + b'\x00' * 200


class TestUnifiedChatInput(unittest.TestCase):
    def test_legacy_text(self):
        v = extract_chat_submission('  What time?  ')
        self.assertEqual(v.text, 'What time?')
        self.assertFalse(v.from_microphone)
    def test_none(self):
        v = extract_chat_submission(None)
        self.assertFalse(v.text or v.audio_wav)
    def test_new_streamlit_text(self):
        v = extract_chat_submission(SimpleNamespace(text='  Weather tomorrow? ', audio=None))
        self.assertEqual(v.text, 'Weather tomorrow?')
        self.assertIsNone(v.audio_wav)
    def test_voice_only(self):
        v = extract_chat_submission(SimpleNamespace(text='', audio=FakeAudio()))
        self.assertTrue(v.from_microphone)
        self.assertTrue(v.audio_wav.startswith(b'RIFF'))
    def test_audio_raw_bytes(self):
        v = extract_chat_submission({'text': '', 'audio': b'RIFFrecording'})
        self.assertTrue(v.from_microphone)
        self.assertEqual(v.audio_wav, b'RIFFrecording')
    def test_typed_text_overrides_audio(self):
        v = extract_chat_submission(SimpleNamespace(text='  typed instruction ', audio=FakeAudio()))
        self.assertEqual(v.text, 'typed instruction')
        self.assertFalse(v.from_microphone)
        self.assertIsNone(v.audio_wav)
    def test_empty_audio_fails(self):
        with self.assertRaisesRegex(ValueError, 'empty'):
            extract_chat_submission(SimpleNamespace(text='', audio=b''))
    def test_unsupported_audio_object_fails(self):
        with self.assertRaisesRegex(ValueError, 'could not be read'):
            extract_chat_submission(SimpleNamespace(text='', audio=object()))
    def test_empty_input(self):
        self.assertEqual(extract_chat_submission({'text': ' ', 'audio': None}).text, '')


if __name__ == '__main__':
    unittest.main()
