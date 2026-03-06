import os
import csv
import math
import random
from pathlib import Path

import numpy as np


def write_pgm(path, img):
    img = np.asarray(img)
    if img.ndim != 2:
        raise ValueError("PGM image must be 2D")
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)

    h, w = img.shape
    with open(path, "wb") as f:
        f.write(f"P5\n{w} {h}\n255\n".encode("ascii"))
        f.write(img.tobytes())


def _freq_to_bin(freq_hz, fft_size, sample_rate):
    frac = (freq_hz + sample_rate / 2.0) / sample_rate
    idx = int(frac * fft_size)
    return max(0, min(fft_size - 1, idx))


def _draw_gaussian_band(column, center_bin, bw_bins, peak=1.0):
    rows = np.arange(len(column))
    sigma = max(1.0, bw_bins / 2.355)
    band = peak * np.exp(-0.5 * ((rows - center_bin) / sigma) ** 2)
    column += band


class JammerAwareHopModel:
    def __init__(
        self,
        seed=12345,
        chan_spacing=200e3,
        chan_bw_hz=60e3,
        guard_hz=2e3,
        num_chans=8,
        max_attempts=64,
        center_channels_around_dc=True,
    ):
        self.rng = random.Random(int(seed))
        self.chan = 0
        self.chan_spacing = float(chan_spacing)
        self.chan_bw_hz = float(chan_bw_hz)
        self.guard_hz = float(guard_hz)
        self.num_chans = int(num_chans)
        self.max_attempts = int(max_attempts)

        self.jam_lo = None
        self.jam_hi = None
        self.center_channels_around_dc = bool(center_channels_around_dc)

    def set_jammer(self, jam_lo, jam_hi):
        jam_lo = float(jam_lo)
        jam_hi = float(jam_hi)
        if jam_hi < jam_lo:
            jam_lo, jam_hi = jam_hi, jam_lo
        self.jam_lo = jam_lo
        self.jam_hi = jam_hi

    def _is_no_jammer(self):
        return (
            self.jam_lo is None or self.jam_hi is None or
            (self.jam_lo == 0.0 and self.jam_hi == 0.0)
        )

    def _overlap(self, a_lo, a_hi, b_lo, b_hi):
        return (a_lo <= b_hi) and (b_lo <= a_hi)

    def _hop_band(self, f_center):
        half = 0.5 * self.chan_bw_hz
        return (f_center - half - self.guard_hz, f_center + half + self.guard_hz)

    def _hop_overlaps_jam(self, f_center):
        if self._is_no_jammer():
            return False
        c_lo, c_hi = self._hop_band(f_center)
        return self._overlap(c_lo, c_hi, self.jam_lo, self.jam_hi)

    def _grid_freq(self, chan):
        if self.center_channels_around_dc:
            offset = chan - (self.num_chans - 1) / 2.0
            return float(offset * self.chan_spacing)
        return float(chan) * self.chan_spacing

    def _pick_next_chan(self):
        step = self.rng.randint(1, self.num_chans - 1)
        return (self.chan + step) % self.num_chans

    def _move_center_to_clear_jam(self, f_center):
        if not self._hop_overlaps_jam(f_center):
            return f_center

        half = 0.5 * self.chan_bw_hz
        need_below = self.jam_lo - self.guard_hz - half
        need_above = self.jam_hi + self.guard_hz + half

        if abs(f_center - need_below) <= abs(need_above - f_center):
            target = need_below
            snapped = math.floor(target / self.chan_spacing) * self.chan_spacing
        else:
            target = need_above
            snapped = math.ceil(target / self.chan_spacing) * self.chan_spacing

        return float(snapped)

    def _fallback_safe_freq(self):
        for c in range(self.num_chans):
            f = self._grid_freq(c)
            if not self._hop_overlaps_jam(f):
                return f
        return 0.0

    def next_freq(self):
        chosen = None
        attempts = 0

        while attempts < self.max_attempts:
            self.chan = self._pick_next_chan()
            f = self._grid_freq(self.chan)
            f2 = self._move_center_to_clear_jam(f)

            if not self._hop_overlaps_jam(f2):
                chosen = f2
                break

            attempts += 1

        if chosen is None:
            chosen = self._fallback_safe_freq()

        return float(chosen)


def create_fhss_cnn_pgms_jammer_aware_clean(
    output_dir,
    jam_bandwidths_hz,
    n_images_per_bw=100,
    *,
    sample_rate=2.0e6,
    chan_spacing=200e3,
    chan_bw_hz=60e3,
    guard_hz=2e3,
    num_chans=8,
    max_attempts=64,
    fft_size=128,
    time_bins=256,
    hop_every_cols=6,
    mute_time_cols=2,
    signal_peak=1.0,
    seed=12345,
    jammer_mode="random",   # still used for hop decisions only
    center_channels_around_dc=True,
    vertical=True,
    add_labels_csv=True,
):
    """
    Generate clean grayscale PGM spectrograms.

    Important:
    - jammer IS used to influence hop selection
    - jammer is NOT drawn in the image
    - background noise is NOT added
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    jam_bandwidths_hz = list(jam_bandwidths_hz)
    all_records = []

    if center_channels_around_dc:
        chan_freqs = np.array(
            [(c - (num_chans - 1) / 2.0) * chan_spacing for c in range(num_chans)],
            dtype=float
        )
    else:
        chan_freqs = np.array([c * chan_spacing for c in range(num_chans)], dtype=float)

    if np.max(np.abs(chan_freqs)) >= sample_rate / 2:
        raise ValueError(
            "FHSS channel set exceeds spectrogram span. Increase sample_rate "
            "or reduce num_chans/chan_spacing."
        )

    image_counter = 0

    for bw_hz in jam_bandwidths_hz:
        bw_dir = output_dir / f"jam_bw_{int(round(bw_hz))}Hz"
        bw_dir.mkdir(parents=True, exist_ok=True)

        for i in range(n_images_per_bw):
            img_seed = seed + 7919 * image_counter + 31 * i
            rng = np.random.default_rng(img_seed)

            # clean background
            spec = np.zeros((fft_size, time_bins), dtype=float)

            if jammer_mode == "centered":
                jammer_center_hz = 0.0
            elif jammer_mode == "random":
                margin = bw_hz / 2.0
                lo = -sample_rate / 2.0 + margin
                hi = sample_rate / 2.0 - margin
                jammer_center_hz = float(rng.uniform(lo, hi))
            elif jammer_mode == "cochannel":
                jammer_center_hz = float(rng.choice(chan_freqs))
            elif jammer_mode == "sweep":
                jammer_center_hz = 0.0
            else:
                raise ValueError("jammer_mode must be 'centered', 'random', 'cochannel', or 'sweep'")

            jam_lo = jammer_center_hz - bw_hz / 2.0
            jam_hi = jammer_center_hz + bw_hz / 2.0

            hop_model = JammerAwareHopModel(
                seed=img_seed,
                chan_spacing=chan_spacing,
                chan_bw_hz=chan_bw_hz,
                guard_hz=guard_hz,
                num_chans=num_chans,
                max_attempts=max_attempts,
                center_channels_around_dc=center_channels_around_dc,
            )

            chosen_freqs = np.zeros(time_bins, dtype=float)
            current_freq = hop_model._grid_freq(hop_model.chan)

            for t in range(time_bins):
                if jammer_mode == "sweep":
                    frac = t / max(1, time_bins - 1)
                    jammer_center_hz_t = (-sample_rate / 4.0) + frac * (sample_rate / 2.0)
                    jam_lo_t = jammer_center_hz_t - bw_hz / 2.0
                    jam_hi_t = jammer_center_hz_t + bw_hz / 2.0
                else:
                    jam_lo_t = jam_lo
                    jam_hi_t = jam_hi

                hop_model.set_jammer(jam_lo_t, jam_hi_t)

                if t % hop_every_cols == 0:
                    current_freq = hop_model.next_freq()

                chosen_freqs[t] = current_freq

            sig_bw_bins = max(1.5, chan_bw_hz / sample_rate * fft_size)

            for t in range(time_bins):
                muted = (t % hop_every_cols) < mute_time_cols if mute_time_cols > 0 else False
                if muted:
                    continue

                sig_bin = _freq_to_bin(chosen_freqs[t], fft_size, sample_rate)
                _draw_gaussian_band(
                    spec[:, t],
                    center_bin=sig_bin,
                    bw_bins=sig_bw_bins,
                    peak=signal_peak,
                )

            # simple normalization to 8-bit
            maxval = np.max(spec)
            if maxval <= 0:
                img = np.zeros_like(spec, dtype=np.uint8)
            else:
                img = (255.0 * spec / maxval).astype(np.uint8)

            if vertical:
                img = img[::-1, :]
                img = img.T
            else:
                img = np.flipud(img)

            fname = (
                f"spec_bw{int(round(bw_hz))}"
                f"_img{i:04d}"
                f"_mode-{jammer_mode}.pgm"
            )
            fpath = bw_dir / fname
            write_pgm(fpath, img)

            rec = {
                "file": str(fpath),
                "jam_bw_hz": float(bw_hz),
                "jammer_mode": jammer_mode,
                "sample_rate": float(sample_rate),
                "chan_spacing": float(chan_spacing),
                "chan_bw_hz": float(chan_bw_hz),
                "guard_hz": float(guard_hz),
                "num_chans": int(num_chans),
                "max_attempts": int(max_attempts),
                "fft_size": int(fft_size),
                "time_bins": int(time_bins),
                "hop_every_cols": int(hop_every_cols),
                "mute_time_cols": int(mute_time_cols),
                "center_channels_around_dc": bool(center_channels_around_dc),
            }
            all_records.append(rec)
            image_counter += 1

    if add_labels_csv:
        csv_path = output_dir / "labels.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "file",
                    "jam_bw_hz",
                    "jammer_mode",
                    "sample_rate",
                    "chan_spacing",
                    "chan_bw_hz",
                    "guard_hz",
                    "num_chans",
                    "max_attempts",
                    "fft_size",
                    "time_bins",
                    "hop_every_cols",
                    "mute_time_cols",
                    "center_channels_around_dc",
                ],
            )
            writer.writeheader()
            writer.writerows(all_records)

    return all_records

records = create_fhss_cnn_pgms_jammer_aware_clean(
    output_dir="cnn_fhss_clean_pgms",
    jam_bandwidths_hz=[200e3, 400e3, 600e3],
    n_images_per_bw=200,
    sample_rate=2.0e6,
    chan_spacing=200e3,
    chan_bw_hz=60e3,
    guard_hz=2e3,
    num_chans=8,
    max_attempts=64,
    fft_size=128,
    time_bins=256,
    hop_every_cols=6,
    mute_time_cols=2,
    signal_peak=1.0,
    seed=12345,
    jammer_mode="centered",
    center_channels_around_dc=True,
    vertical=True,
)