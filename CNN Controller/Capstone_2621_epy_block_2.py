import os
import time
import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """
    Capture receiver-side FFT power vectors and persist spectrogram image snippets
    for CNN training. Labels are saved from jammer band edges as avoided FHSS channels.
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

        self._rows = []
        self._count = 0
        self.jam_lo = 0.0
        self.jam_hi = 0.0

        self.message_port_register_in(pmt.intern("edges"))
        self.set_msg_handler(pmt.intern("edges"), self._on_edges)

        os.makedirs(self.out_dir, exist_ok=True)

    def _on_edges(self, msg):
        try:
            if not pmt.is_dict(msg):
                return
            lo_p = pmt.dict_ref(msg, pmt.intern("f_lo_hz"), pmt.PMT_NIL)
            hi_p = pmt.dict_ref(msg, pmt.intern("f_hi_hz"), pmt.PMT_NIL)
            if lo_p is pmt.PMT_NIL or hi_p is pmt.PMT_NIL:
                return
            lo = float(pmt.to_double(lo_p))
            hi = float(pmt.to_double(hi_p))
            if hi < lo:
                lo, hi = hi, lo
            self.jam_lo, self.jam_hi = lo, hi
        except Exception:
            return

    def _channel_list(self):
        if self.jam_lo == 0.0 and self.jam_hi == 0.0:
            return []
        chans = []
        half = 0.5 * self.chan_bw_hz
        for c in range(self.num_chans):
            center = c * self.chan_spacing
            lo = center - half
            hi = center + half
            if (lo <= self.jam_hi) and (self.jam_lo <= hi):
                chans.append(c)
        return chans

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

        chans = self._channel_list()
        with open(stem + ".txt", "w", encoding="utf-8") as f:
            f.write(f"jam_lo_hz={self.jam_lo}\n")
            f.write(f"jam_hi_hz={self.jam_hi}\n")
            f.write("avoid_channels=" + ",".join(str(c) for c in chans) + "\n")

    def work(self, input_items, output_items):
        specs = input_items[0]
        for v in specs:
            p_db = 10.0 * np.log10(np.maximum(v, 1e-20))
            self._rows.append(p_db)
            if len(self._rows) > self.history_len:
                self._rows = self._rows[-self.history_len:]

            self._count += 1
            if self._count % self.save_every == 0:
                self._write_training_pair()

        return len(specs)
