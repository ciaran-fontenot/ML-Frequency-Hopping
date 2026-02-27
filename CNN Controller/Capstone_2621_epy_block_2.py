import os
import time
import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """
    Capture receiver-side FFT power vectors and persist spectrogram image snippets
    for CNN training. Labels are inferred from observed hops on the RX antenna
    by identifying channels that are not being visited over a rolling hop window.
    """

    def __init__(
        self,
        nfft=1024,
        history_len=128,
        save_every=200,
        out_dir="cnn_training_data",
        samp_rate=4.8e6,
        chan_spacing=200e3,
        chan_bw_hz=60e3,
        num_chans=10,
        hop_history=64,
        min_absence_ratio=0.6,
    ):
        gr.sync_block.__init__(
            self,
            name="rx_spectrogram_capture",
            in_sig=[(np.float32, int(nfft))],
            out_sig=None,
        )

        self.nfft = int(nfft)
        self.history_len = int(history_len)
        self.save_every = max(1, int(save_every))
        self.out_dir = str(out_dir)
        self.samp_rate = float(samp_rate)
        self.chan_spacing = float(chan_spacing)
        self.chan_bw_hz = float(chan_bw_hz)
        self.num_chans = int(num_chans)
        self.hop_history = max(4, int(hop_history))
        self.min_absence_ratio = float(min_absence_ratio)

        self._rows = []
        self._count = 0
        self._rx_chan_history = []
        self._last_avoid_channels = []
        self.message_port_register_out(pmt.intern("avoid_channels"))

        os.makedirs(self.out_dir, exist_ok=True)

    def _infer_rx_hop_channel(self, p_db):
        df = self.samp_rate / float(self.nfft)
        half_bw_bins = max(1, int(round((0.5 * self.chan_bw_hz) / df)))

        best_chan = None
        best_power = -1e30
        for chan in range(self.num_chans):
            center_f = chan * self.chan_spacing
            center_bin = int(round((center_f + (0.5 * self.samp_rate)) / df))

            lo = max(0, center_bin - half_bw_bins)
            hi = min(self.nfft, center_bin + half_bw_bins + 1)
            if hi <= lo:
                continue

            avg_p = float(np.mean(p_db[lo:hi]))
            if avg_p > best_power:
                best_power = avg_p
                best_chan = chan

        return best_chan

    def _append_rx_hop_channel(self, chan):
        if chan is None:
            return
        self._rx_chan_history.append(chan)
        if len(self._rx_chan_history) > self.hop_history:
            self._rx_chan_history = self._rx_chan_history[-self.hop_history:]
        self._last_avoid_channels = self._infer_avoid_channels()

    def _infer_avoid_channels(self):
        if len(self._rx_chan_history) < self.hop_history:
            return []

        counts = np.zeros(self.num_chans, dtype=np.int32)
        for ch in self._rx_chan_history:
            if 0 <= ch < self.num_chans:
                counts[ch] += 1

        threshold = self.hop_history * (1.0 - self.min_absence_ratio)
        return [int(idx) for idx, c in enumerate(counts) if float(c) <= threshold]

    def _pub_avoid_channels(self):
        vec = pmt.init_u32vector(len(self._last_avoid_channels), self._last_avoid_channels)
        self.message_port_pub(pmt.intern("avoid_channels"), vec)

    def _write_training_pair(self):
        if len(self._rows) < self.history_len:
            return

        arr = np.asarray(self._rows[-self.history_len:], dtype=np.float32)
        arr = np.nan_to_num(arr, nan=-140.0, posinf=10.0, neginf=-140.0)
        arr = np.clip(arr, -140.0, 10.0)
        # map [-140, 10] dB to [0,255]
        img = ((arr + 140.0) * (255.0 / 150.0)).astype(np.uint8)

        ts = int(time.time() * 1000)
        stem = os.path.join(self.out_dir, f"rx_spec_{ts}_{self._count}")

        # Portable Graymap (PGM): lightweight image format supported by many loaders.
        with open(stem + ".pgm", "wb") as f:
            header = f"P5\n{self.nfft} {self.history_len}\n255\n".encode("ascii")
            f.write(header)
            f.write(img.tobytes())

        chans = list(self._last_avoid_channels)
        with open(stem + ".txt", "w", encoding="utf-8") as f:
            f.write(f"hop_history={self.hop_history}\n")
            f.write("avoid_channels=" + ",".join(str(c) for c in chans) + "\n")

        self._pub_avoid_channels()

    def work(self, input_items, output_items):
        specs = input_items[0]
        for v in specs:
            p_db = 10.0 * np.log10(np.maximum(v, 1e-20))
            rx_chan = self._infer_rx_hop_channel(p_db)
            self._append_rx_hop_channel(rx_chan)
            self._rows.append(p_db)
            if len(self._rows) > self.history_len:
                self._rows = self._rows[-self.history_len:]

            self._count += 1
            if self._count % self.save_every == 0:
                self._write_training_pair()

        return len(specs)