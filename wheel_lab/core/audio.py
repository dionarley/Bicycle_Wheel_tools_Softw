"""Leitura de tom de raios a partir de gravações WAV (Fase 4).

O microfone (ou o celular) grava o som de um raio; este módulo estima a
frequência fundamental e, se o comprimento e a densidade linear do raio forem
informados, converte o tom em tensão pela equação da corda fixa.

Não há dependência de NumPy: a FFT é implementada em Python puro. O sinal é
decimado para ~8 kHz antes da análise, o que é suficiente para o tom de raios
(geralmente entre 100 e 1500 Hz) e mantém o processamento rápido.
"""

from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from .models import Side
from .tension import tension_from_tone_hz


@dataclass(frozen=True)
class ToneReading:
    """Resultado da análise de uma gravação de tom."""

    frequency_hz: float
    confidence: float
    rms: float
    peak_amplitude: float
    sample_rate_hz: int
    duration_s: float
    side: Side | None = None
    tension_n: float | None = None
    expected_tension_n: float | None = None
    spoke_length_mm: float | None = None
    linear_density_kg_per_m: float | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.side is not None and not isinstance(self.side, Side):
            object.__setattr__(self, "side", Side(self.side))

    def to_dict(self) -> dict:
        return {
            "frequency_hz": self.frequency_hz,
            "confidence": self.confidence,
            "rms": self.rms,
            "peak_amplitude": self.peak_amplitude,
            "sample_rate_hz": self.sample_rate_hz,
            "duration_s": self.duration_s,
            "side": self.side.value if self.side is not None else None,
            "tension_n": self.tension_n,
            "expected_tension_n": self.expected_tension_n,
            "spoke_length_mm": self.spoke_length_mm,
            "linear_density_kg_per_m": self.linear_density_kg_per_m,
            "warnings": list(self.warnings),
        }

    def summary_lines(self) -> list[str]:
        lines = [
            "=== LEITURA DE TOM ===",
            f"Frequência: {_fmt(self.frequency_hz, 1)} Hz",
            f"Confiança: {_fmt(self.confidence * 100.0, 0)}%",
            (
                f"RMS: {_fmt(self.rms, 4)} | pico: "
                f"{_fmt(self.peak_amplitude, 3)}"
            ),
            (
                f"Duração: {_fmt(self.duration_s, 2)} s | "
                f"taxa: {self.sample_rate_hz} Hz"
            ),
        ]
        if self.side is not None:
            lines.append(f"Lado: {self.side.label_pt}")
        if self.tension_n is not None:
            lines.append(f"Tensão estimada: {_fmt(self.tension_n, 0)} N")
        if self.expected_tension_n is not None:
            lines.append(
                f"Tensão esperada: {_fmt(self.expected_tension_n, 0)} N"
            )
        if self.warnings:
            lines.append("")
            lines.append("Avisos:")
            lines.extend(f"• {warning}" for warning in self.warnings)
        return lines

    def summary_text(self) -> str:
        return "\n".join(self.summary_lines())


def read_wav_mono(
    path: str | Path, max_seconds: float = 5.0
) -> tuple[list[float], int]:
    """Lê um WAV PCM e devolve amostras mono normalizadas e a taxa.

    ``max_seconds`` limita a leitura para evitar arquivos longos. O arquivo
    pode ter 8, 16, 24 ou 32 bits por amostra e um ou mais canais.
    """

    if not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("O tempo máximo de leitura deve ser positivo.")
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            if channels <= 0 or sample_rate <= 0 or frame_count <= 0:
                raise ValueError("O arquivo WAV está vazio ou inválido.")
            if sample_width not in (1, 2, 3, 4):
                raise ValueError(
                    "Formato WAV não suportado: use PCM de 8, 16, 24 ou "
                    "32 bits."
                )
            frames_to_read = min(
                frame_count, max(1, int(sample_rate * max_seconds))
            )
            raw = handle.readframes(frames_to_read)
    except wave.Error as exc:
        raise ValueError(f"Não foi possível ler o WAV: {exc}") from exc
    except (OSError, EOFError) as exc:
        raise ValueError(f"Não foi possível abrir o WAV: {exc}") from exc

    samples = _decode_pcm(raw, sample_width, channels)
    if not samples:
        raise ValueError("O arquivo WAV não contém amostras.")
    return samples, sample_rate


def estimate_tone(
    samples: list[float] | tuple[float, ...],
    sample_rate_hz: int,
    min_hz: float = 80.0,
    max_hz: float = 2000.0,
    side: Side | None = None,
    expected_tension_n: float | None = None,
    spoke_length_mm: float | None = None,
    linear_density_kg_per_m_value: float | None = None,
) -> ToneReading:
    """Estima a frequência fundamental de uma sequência de amostras."""

    if not samples:
        raise ValueError("Não há amostras para analisar.")
    if not isinstance(sample_rate_hz, int) or sample_rate_hz <= 0:
        raise ValueError("A taxa de amostragem deve ser um inteiro positivo.")
    for name, value in (
        ("frequência mínima", min_hz),
        ("frequência máxima", max_hz),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"A {name} deve ser positiva.")
    if min_hz >= max_hz:
        raise ValueError("A frequência mínima deve ser menor que a máxima.")
    if expected_tension_n is not None:
        if not math.isfinite(expected_tension_n) or expected_tension_n <= 0:
            raise ValueError("A tensão esperada deve ser positiva.")
    if spoke_length_mm is not None:
        if not math.isfinite(spoke_length_mm) or spoke_length_mm <= 0:
            raise ValueError("O comprimento do raio deve ser positivo.")
    if linear_density_kg_per_m_value is not None:
        if (
            not math.isfinite(linear_density_kg_per_m_value)
            or linear_density_kg_per_m_value <= 0
        ):
            raise ValueError("A densidade linear do raio deve ser positiva.")

    duration = len(samples) / sample_rate_hz
    centered = [float(value) for value in samples]
    mean = sum(centered) / len(centered)
    centered = [value - mean for value in centered]
    rms = math.sqrt(
        sum(value * value for value in centered) / len(centered)
    )
    peak = max(abs(value) for value in centered)
    if rms < 1e-8:
        raise ValueError("Sinal praticamente silencioso; não há tom para ler.")

    analysis_rate, decimated = _decimate(centered, sample_rate_hz)
    if max_hz >= analysis_rate / 2.0:
        raise ValueError(
            "A taxa de amostragem é insuficiente para a faixa de frequência "
            "escolhida."
        )
    if len(decimated) < 64:
        raise ValueError("Gravação muito curta para estimar o tom.")

    windowed = _hann_window(decimated)
    fft_size = _next_power_of_two(max(len(windowed), 4096))
    values = [complex(value, 0.0) for value in windowed]
    values.extend([0j] * (fft_size - len(values)))
    spectrum = _fft(values)
    magnitudes = [
        abs(spectrum[index]) for index in range(fft_size // 2 + 1)
    ]

    min_bin = max(
        1, int(math.floor(min_hz * fft_size / analysis_rate))
    )
    max_bin = min(
        len(magnitudes) - 1,
        int(math.ceil(max_hz * fft_size / analysis_rate)),
    )
    if min_bin > max_bin:
        raise ValueError("Faixa de frequência fora do espectro analisado.")
    band = magnitudes[min_bin : max_bin + 1]
    peak_offset = max(range(len(band)), key=lambda index: band[index])
    peak_bin = min_bin + peak_offset
    peak_magnitude = magnitudes[peak_bin]
    if peak_magnitude <= 0.0:
        raise ValueError("Não foi possível encontrar um pico de tom.")

    band_power = sum(value * value for value in band)
    concentration = (
        (peak_magnitude * peak_magnitude) / band_power
        if band_power > 0.0
        else 0.0
    )
    # Um tom puro concentra a maior parte da energia em poucos bins; ruído
    # espalha a energia pela banda. A escala foi calibrada para dar ~1,0 em
    # um tom limpo e ~0,0 em ruído branco.
    confidence = max(0.0, min(1.0, (concentration - 0.10) / 0.45))
    frequency = _interpolated_frequency(
        magnitudes, peak_bin, analysis_rate, fft_size
    )

    warnings: list[str] = []
    if confidence < 0.5:
        warnings.append(
            "Confiança baixa; aproxime o microfone, reduza ruído ou bata "
            "levemente no raio."
        )
    if rms < 0.01:
        warnings.append("Sinal fraco; aumente o ganho da gravação.")
    if duration < 0.2:
        warnings.append(
            "Gravação curta; use pelo menos 0,2 s para melhorar a leitura."
        )
    if peak_bin <= min_bin + 1 or peak_bin >= max_bin - 1:
        warnings.append(
            "Pico próximo do limite da faixa; ajuste as frequências mínima "
            "e máxima."
        )

    tension = None
    if (
        spoke_length_mm is not None
        and linear_density_kg_per_m_value is not None
    ):
        tension = tension_from_tone_hz(
            frequency,
            spoke_length_mm,
            linear_density_kg_per_m_value,
        )

    return ToneReading(
        frequency_hz=frequency,
        confidence=confidence,
        rms=rms,
        peak_amplitude=peak,
        sample_rate_hz=sample_rate_hz,
        duration_s=duration,
        side=side,
        tension_n=tension,
        expected_tension_n=expected_tension_n,
        spoke_length_mm=spoke_length_mm,
        linear_density_kg_per_m=linear_density_kg_per_m_value,
        warnings=tuple(warnings),
    )


def analyze_wav_file(
    path: str | Path,
    min_hz: float = 80.0,
    max_hz: float = 2000.0,
    max_seconds: float = 5.0,
    side: Side | None = None,
    expected_tension_n: float | None = None,
    spoke_length_mm: float | None = None,
    linear_density_kg_per_m_value: float | None = None,
) -> ToneReading:
    """Lê um WAV e devolve a leitura de tom."""

    samples, sample_rate = read_wav_mono(path, max_seconds=max_seconds)
    return estimate_tone(
        samples,
        sample_rate,
        min_hz=min_hz,
        max_hz=max_hz,
        side=side,
        expected_tension_n=expected_tension_n,
        spoke_length_mm=spoke_length_mm,
        linear_density_kg_per_m_value=linear_density_kg_per_m_value,
    )


def _decode_pcm(
    raw: bytes, sample_width: int, channels: int
) -> list[float]:
    if sample_width == 1:
        values = array("B")
        values.frombytes(raw)
        decoded = [(value - 128) / 128.0 for value in values]
    elif sample_width == 2:
        values = array("h")
        values.frombytes(raw)
        if sys.byteorder == "big":
            values.byteswap()
        decoded = [value / 32768.0 for value in values]
    elif sample_width == 3:
        decoded = []
        for offset in range(0, len(raw) - 2, 3):
            value = int.from_bytes(
                raw[offset : offset + 3], "little", signed=True
            )
            decoded.append(value / 8_388_608.0)
    else:
        values = array("i")
        values.frombytes(raw)
        if sys.byteorder == "big":
            values.byteswap()
        decoded = [value / 2_147_483_648.0 for value in values]

    if channels == 1:
        return decoded
    frame_count = len(decoded) // channels
    mono: list[float] = []
    for frame in range(frame_count):
        start = frame * channels
        mono.append(
            sum(decoded[start : start + channels]) / float(channels)
        )
    return mono


def _decimate(
    samples: list[float], sample_rate_hz: int
) -> tuple[float, list[float]]:
    target_rate = 8000.0
    factor = max(1, int(round(sample_rate_hz / target_rate)))
    if factor == 1:
        return float(sample_rate_hz), samples
    usable = len(samples) - len(samples) % factor
    if usable < 64:
        raise ValueError("Gravação muito curta para estimar o tom.")
    decimated = [
        sum(samples[offset : offset + factor]) / float(factor)
        for offset in range(0, usable, factor)
    ]
    return sample_rate_hz / factor, decimated


def _hann_window(samples: list[float]) -> list[float]:
    count = len(samples)
    if count <= 1:
        return list(samples)
    denominator = count - 1
    return [
        value
        * (0.5 - 0.5 * math.cos(2.0 * math.pi * index / denominator))
        for index, value in enumerate(samples)
    ]


def _next_power_of_two(value: int) -> int:
    result = 1
    while result < value:
        result <<= 1
    return result


def _fft(values: list[complex]) -> list[complex]:
    """FFT radix-2 iterativa, in-place, em Python puro."""

    count = len(values)
    if count & (count - 1):
        raise ValueError("A FFT exige um comprimento potência de 2.")
    j = 0
    for index in range(1, count):
        bit = count >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if index < j:
            values[index], values[j] = values[j], values[index]

    length = 2
    while length <= count:
        angle = -2.0 * math.pi / length
        root = complex(math.cos(angle), math.sin(angle))
        half = length // 2
        for start in range(0, count, length):
            factor = 1.0 + 0.0j
            for index in range(start, start + half):
                even = values[index]
                odd = values[index + half] * factor
                values[index] = even + odd
                values[index + half] = even - odd
                factor *= root
        length <<= 1
    return values


def _interpolated_frequency(
    magnitudes: list[float],
    peak_bin: int,
    sample_rate_hz: float,
    fft_size: int,
) -> float:
    delta = 0.0
    if 0 < peak_bin < len(magnitudes) - 1:
        alpha = magnitudes[peak_bin - 1]
        beta = magnitudes[peak_bin]
        gamma = magnitudes[peak_bin + 1]
        denominator = alpha - 2.0 * beta + gamma
        if abs(denominator) > 1e-12:
            delta = 0.5 * (alpha - gamma) / denominator
            delta = max(-0.5, min(0.5, delta))
    return (peak_bin + delta) * sample_rate_hz / fft_size


def _fmt(value: float, decimals: int = 1) -> str:
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


__all__ = [
    "ToneReading",
    "analyze_wav_file",
    "estimate_tone",
    "read_wav_mono",
]
