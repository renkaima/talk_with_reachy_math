"""Tests for playing Reachy's voice more slowly without changing its pitch."""

import numpy as np
import pytest

from talk_with_reachy_math import slow_speech
from talk_with_reachy_math.slow_speech import SpeechSlower


RATE = 16000


def _tone(seconds: float, hz: float = 220.0) -> np.ndarray:
    return (np.sin(2 * np.pi * hz * np.arange(int(RATE * seconds)) / RATE) * 8000).astype(np.int16)


def _slow(chunks: list[np.ndarray], factor: float = 0.85) -> np.ndarray:
    slower = SpeechSlower(factor)
    return np.concatenate([*(slower.process(c) for c in chunks), slower.flush()])


@pytest.mark.parametrize(("raw", "expected"), [(None, 0.85), ("1", 1.0), ("0.7", 0.7), ("0.2", 0.5), ("2", 1.0)])
def test_the_speed_comes_from_the_environment_within_limits(
    raw: str | None, expected: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default is 0.85; values are kept between 0.5 and 1, and a typo falls back to the default."""
    if raw is None:
        monkeypatch.delenv(slow_speech.SPEED_ENV, raising=False)
    else:
        monkeypatch.setenv(slow_speech.SPEED_ENV, raw)
    assert slow_speech.speed() == expected
    monkeypatch.setenv(slow_speech.SPEED_ENV, "slow")
    assert slow_speech.speed() == slow_speech.DEFAULT_SPEED


def test_slowed_speech_lasts_longer_and_keeps_its_pitch() -> None:
    """At 0.85, one second lasts about 1.18 seconds, and a 440 Hz tone stays at 440 Hz."""
    tone = _tone(1.0, 440.0)
    out = _slow([tone])
    assert 1.15 < out.size / tone.size < 1.21
    spectrum = np.abs(np.fft.rfft(out[2000:18000] * np.hanning(16000)))
    assert abs(np.fft.rfftfreq(16000, 1 / RATE)[np.argmax(spectrum)] - 440) <= 2


def test_streaming_in_small_chunks_gives_the_same_audio_and_keeps_the_end() -> None:
    """Chunks of any size give the same result as one piece, and the last word is not cut off."""
    tone = _tone(0.5)
    whole = _slow([tone])
    pieces = _slow(np.array_split(tone, 37))
    np.testing.assert_array_equal(whole, pieces)
    assert np.abs(whole[-160:]).max() > 4000


def test_a_speed_of_one_plays_the_audio_unchanged_and_reset_drops_held_audio() -> None:
    """Speed 1 passes chunks through; after the child interrupts, nothing held back is played."""
    tone = _tone(0.1)
    np.testing.assert_array_equal(SpeechSlower(1.0).process(tone), tone)
    assert SpeechSlower(1.0).flush().size == 0
    slower = SpeechSlower(0.85)
    slower.process(tone)
    slower.reset()
    assert slower.flush().size == 0
