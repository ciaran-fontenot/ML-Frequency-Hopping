import numpy as np
import pmt
from gnuradio import gr

class blk(gr.sync_block):
    def __init__(self, samp_rate=1e6, nfft=1024, thresh_db=8.0, publish_every=10):
        gr.sync_block.__init__(
            self,
            name="noise_edges_safe",
            in_sig=[(np.float32, int(nfft))],
            out_sig=None
        )
        self.samp_rate = float(samp_rate)
        self.nfft = int(nfft)
        self.thresh_db = float(thresh_db)
        self.publish_every = int(publish_every)
        self._count = 0
        self.floor_db = None

        self.message_port_register_out(pmt.intern("edges"))

    def _pub_edges(self, f_lo, f_hi, thr):
        msg = pmt.make_dict()
        msg = pmt.dict_add(msg, pmt.intern("f_lo_hz"), pmt.from_double(float(f_lo)))
        msg = pmt.dict_add(msg, pmt.intern("f_hi_hz"), pmt.from_double(float(f_hi)))
        msg = pmt.dict_add(msg, pmt.intern("thr_db"), pmt.from_double(float(thr)))
        self.message_port_pub(pmt.intern("edges"), msg)

    def work(self, input_items, output_items):
        specs = input_items[0]  # (nvecs, nfft)
        bin_hz = self.samp_rate / self.nfft

        for v in specs:
            self._count += 1
            if self.publish_every > 1 and (self._count % self.publish_every) != 0:
                continue

            try:
                p_db = 10.0*np.log10(np.maximum(v, 1e-20))

                floor_now = np.median(p_db)
                self.floor_db = floor_now if self.floor_db is None else 0.9*self.floor_db + 0.1*floor_now
                thr = self.floor_db + self.thresh_db

                mask = p_db > thr
                idx = np.where(mask)[0]

                # NEW: if no jammer detected, publish zeros
                if idx.size == 0:
                    self._pub_edges(0.0, 0.0, thr)
                    continue

                splits = np.where(np.diff(idx) > 1)[0] + 1
                groups = np.split(idx, splits)
                best = max(groups, key=lambda g: g.size)

                k_lo, k_hi = int(best[0]), int(best[-1])

                # FFT-shifted mapping (-Fs/2..Fs/2) IF your FFT is shift=True.
                f_lo = (k_lo - self.nfft/2) * bin_hz
                f_hi = (k_hi - self.nfft/2) * bin_hz

                self._pub_edges(f_lo, f_hi, thr)

            except Exception:
                # If something weird happens, publish zeros rather than crashing
                try:
                    thr_fallback = float(self.floor_db) if self.floor_db is not None else -200.0
                    self._pub_edges(0.0, 0.0, thr_fallback)
                except Exception:
                    pass

        return len(specs)
