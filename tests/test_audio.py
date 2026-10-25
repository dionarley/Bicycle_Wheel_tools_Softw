import math
import random
import wave
from array import array

import pytest

from wheel_lab.core import (
    Side,
    ToneReading,
    analyze_wav_file,
    estimate_tone,
    read_wav_mono,
    tension_from_tone_hz,
)


def write_wav(path, frames, rate=8000, sampwidth=2):
    """Escreve um WAV PCM; ``frames`` pode ser mono ou lista de tuplas."""

    if frames and not isinstance(frames[0], tuple):
        frames = [(value,) for value in frames]
    channels = len(frames[0]) if frames else 1
    flat = [value for frame in frames for value in frame]

    if sampwidth == 1:
        payload = bytes(
            max(0, min(255, int(round(value * 127.0 + 128.0))))
            for value in flat
        )
    elif sampwidth == 2:
        payload = array(
            "h",
            [
                max(-32768, min(32767, int(round(value * 32767.0))))
                for value in flat
            ],
        ).tobytes()
    elif sampwidth == 3:
        payload = b"".join(
            max(
                -8_388_608,
                min(8_388_607, int(round(value * 8_388_607.0))),
            ).to_bytes(3, "little", signed=True)
            for value in flat
        )
    elif sampwidth == 4:
        payload = array(
            "i",
            [
                max(
                    -2_147_483_648,
                    min(2_147_483_647, int(round(value * 2_147_483_647.0))),
                )
                for value in flat
            ],
        ).tobytes()
    else:
        raise ValueError("largura de amostra não suportada")

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sampwidth)
        handle.setframerate(rate)
        handle.writeframes(payload)


def sine(frequency_hz, rate=8000, seconds=0.5, amplitude=0.5):
    count = int(rate * seconds)
    return [
        amplitude * math.sin(2.0 * math.pi * frequency_hz * index / rate)
        for index in range(count)
    ]


def test_estimate_tone_from_samples():
    reading = estimate_tone(sine(440.0), 8000)
    assert reading.frequency_hz == pytest.approx(440.0, abs=1.5)
    assert reading.confidence > 0.8
    assert reading.rms == pytest.approx(0.5 / math.sqrt(2.0), rel=0.01)
    assert reading.duration_s == pytest.approx(0.5)
    assert reading.warnings == ()
    assert "LEITURA DE TOM" in reading.summary_text()


def test_read_wav_mono_and_analyze_file(tmp_path):
    path = tmp_path / "tom.wav"
    write_wav(path, sine(440.0), rate=8000)
    samples, rate = read_wav_mono(path)
    assert rate == 8000
    assert len(samples) == 4000

    reading = analyze_wav_file(path)
    assert reading.frequency_hz == pytest.approx(440.0, abs=1.5)
    assert reading.sample_rate_hz == 8000


def test_read_wav_mono_respects_max_seconds(tmp_path):
    path = tmp_path / "longo.wav"
    write_wav(path, sine(440.0, seconds=1.0), rate=8000)
    samples, _ = read_wav_mono(path, max_seconds=0.25)
    assert len(samples) == 2000


def test_stereo_is_mixed_to_mono(tmp_path):
    path = tmp_path / "stereo.wav"
    frames = [(value, 0.0) for value in sine(440.0)]
    write_wav(path, frames, rate=8000, sampwidth=2)
    samples, _ = read_wav_mono(path)
    reading = estimate_tone(samples, 8000)
    assert reading.frequency_hz == pytest.approx(440.0, abs=1.5)
    assert reading.rms == pytest.approx(0.25 / math.sqrt(2.0), rel=0.03)


@pytest.mark.parametrize("sampwidth", [1, 2, 3, 4])
def test_wav_sample_widths(tmp_path, sampwidth):
    path = tmp_path / f"tom_{sampwidth}.wav"
    write_wav(path, sine(660.0), rate=8000, sampwidth=sampwidth)
    reading = analyze_wav_file(path)
    assert reading.frequency_hz == pytest.approx(660.0, abs=3.0)
    assert reading.confidence > 0.5


def test_analyze_file_converts_tone_to_tension(tmp_path):
    path = tmp_path / "tensao.wav"
    write_wav(path, sine(880.0, rate=44100), rate=44100)
    reading = analyze_wav_file(
        path,
        side=Side.RIGHT,
        expected_tension_n=223.0,
        spoke_length_mm=300.0,
        linear_density_kg_per_m_value=0.0008,
    )
    assert reading.side is Side.RIGHT
    assert reading.expected_tension_n == pytest.approx(223.0)
    assert reading.tension_n == pytest.approx(223.0, rel=0.02)
    assert reading.tension_n == pytest.approx(
        tension_from_tone_hz(reading.frequency_hz, 300.0, 0.0008)
    )


def test_tone_reading_normalizes_side_and_serializes():
    reading = ToneReading(
        frequency_hz=440.0,
        confidence=0.9,
        rms=0.1,
        peak_amplitude=0.2,
        sample_rate_hz=8000,
        duration_s=0.5,
        side="left",  # type: ignore[arg-type]
    )
    assert reading.side is Side.LEFT
    payload = reading.to_dict()
    assert payload["side"] == "left"
    assert payload["frequency_hz"] == 440.0


def test_noise_has_low_confidence():
    rng = random.Random(42)
    samples = [rng.uniform(-0.5, 0.5) for _ in range(4000)]
    reading = estimate_tone(samples, 8000)
    assert reading.confidence < 0.2
    assert any("Confiança baixa" in warning for warning in reading.warnings)


def test_silent_signal_is_rejected():
    with pytest.raises(ValueError, match="silencioso"):
        estimate_tone([0.0] * 4000, 8000)


def test_invalid_frequency_range_and_sample_rate():
    with pytest.raises(ValueError, match="mínima"):
        estimate_tone(sine(440.0), 8000, min_hz=1000.0, max_hz=100.0)
    with pytest.raises(ValueError, match="insuficiente"):
        estimate_tone(sine(440.0), 4000, max_hz=2000.0)


def test_invalid_wav_and_empty_file(tmp_path):
    with pytest.raises(ValueError, match="abrir"):
        read_wav_mono(tmp_path / "nao_existe.wav")

    empty = tmp_path / "vazio.wav"
    with wave.open(str(empty), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"")
    with pytest.raises(ValueError, match="vazio"):
        read_wav_mono(empty)
