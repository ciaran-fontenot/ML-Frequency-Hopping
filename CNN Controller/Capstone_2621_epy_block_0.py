import numpy as np
import pmt
from gnuradio import gr

class blk(gr.sync_block):
    def __init__(self, samp_rate=1e6, nfft=1024, thresh_db=8.0, publish_every=10, chan_spacing=200e3, chan_bw_hz=60e3, num_chans=10):
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
        self.chan_spacing = float(chan_spacing)
        self.chan_bw_hz = float(chan_bw_hz)
        self.num_chans = int(num_chans)

        self.message_port_register_out(pmt.intern("edges"))
        self.message_port_register_out(pmt.intern("jam_channels"))

    def _pub_edges(self, f_lo, f_hi, thr):
        msg = pmt.make_dict()
        msg = pmt.dict_add(msg, pmt.intern("f_lo_hz"), pmt.from_double(float(f_lo)))
        msg = pmt.dict_add(msg, pmt.intern("f_hi_hz"), pmt.from_double(float(f_hi)))
        msg = pmt.dict_add(msg, pmt.intern("thr_db"), pmt.from_double(float(thr)))
        self.message_port_pub(pmt.intern("edges"), msg)


    def _pub_jam_channels(self, f_lo, f_hi):
        channels = []
        if not (f_lo == 0.0 and f_hi == 0.0):
            half = 0.5 * self.chan_bw_hz
            for c in range(self.num_chans):
                center = float(c) * self.chan_spacing
                c_lo = center - half
                c_hi = center + half
                if (c_lo <= f_hi) and (f_lo <= c_hi):
                    channels.append(int(c))

        vec = pmt.init_u32vector(len(channels), channels)
        self.message_port_pub(pmt.intern("jam_channels"), vec)

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
                    self._pub_jam_channels(0.0, 0.0)
                    continue

                splits = np.where(np.diff(idx) > 1)[0] + 1
                groups = np.split(idx, splits)
                best = max(groups, key=lambda g: g.size)

                k_lo, k_hi = int(best[0]), int(best[-1])

                # FFT-shifted mapping (-Fs/2..Fs/2) IF your FFT is shift=True.
                f_lo = (k_lo - self.nfft/2) * bin_hz
                f_hi = (k_hi - self.nfft/2) * bin_hz

                self._pub_edges(f_lo, f_hi, thr)
                self._pub_jam_channels(f_lo, f_hi)

            except Exception:
                # If something weird happens, publish zeros rather than crashing
                try:
                    thr_fallback = float(self.floor_db) if self.floor_db is not None else -200.0
                    self._pub_edges(0.0, 0.0, thr_fallback)
                    self._pub_jam_channels(0.0, 0.0)
                except Exception:
                    pass

        return len(specs)
