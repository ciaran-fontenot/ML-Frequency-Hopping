import os
import time
import numpy as np
import pmt
from gnuradio import gr


class blk(gr.sync_block):
    """
    Capture receiver-side FFT power vectors and persist spectrogram image snippets
    for CNN training. Labels are inferred from the TX hop sequence itself by
    identifying channels that are not being visited over a rolling hop window.
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
        self._tx_chan_history = []
        self._last_avoid_channels = []

        self.message_port_register_in(pmt.intern("tx_freq"))
        self.set_msg_handler(pmt.intern("tx_freq"), self._on_tx_freq)
        self.message_port_register_out(pmt.intern("avoid_channels"))

        os.makedirs(self.out_dir, exist_ok=True)

    def _on_tx_freq(self, msg):
        try:
            tx_f = None
            if pmt.is_pair(msg):
                key = pmt.car(msg)
                val = pmt.cdr(msg)
                if pmt.is_symbol(key) and pmt.symbol_to_string(key) == "freq":
                    tx_f = float(pmt.to_double(val))
            elif pmt.is_dict(msg):
                f_p = pmt.dict_ref(msg, pmt.intern("freq"), pmt.PMT_NIL)
                if f_p is not pmt.PMT_NIL:
                    tx_f = float(pmt.to_double(f_p))

            if tx_f is None:
                return

            chan = int(round(tx_f / self.chan_spacing))
            chan = chan % self.num_chans
            self._tx_chan_history.append(chan)
            if len(self._tx_chan_history) > self.hop_history:
                self._tx_chan_history = self._tx_chan_history[-self.hop_history:]

            self._last_avoid_channels = self._infer_avoid_channels()
        except Exception:
            return

    def _infer_avoid_channels(self):
        if len(self._tx_chan_history) < self.hop_history:
            return []

        counts = np.zeros(self.num_chans, dtype=np.int32)
        for ch in self._tx_chan_history:
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
            self._rows.append(p_db)
            if len(self._rows) > self.history_len:
                self._rows = self._rows[-self.history_len:]

            self._count += 1
            if self._count % self.save_every == 0:
                self._write_training_pair()

        return len(specs)
