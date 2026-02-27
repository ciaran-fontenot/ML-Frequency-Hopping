import pmt
import random
import threading
import math
from gnuradio import gr

class blk(gr.basic_block):
    def __init__(
        self,
        seed=12345,
        chan_spacing=200e3,
        chan_bw_hz=60e3,
        mute_time_s=0.02,
        guard_hz=2e3,
        num_chans=8,
        max_attempts=64
    ):
        gr.basic_block.__init__(self, name='FHSS TX controller (jammer-aware overlap)', in_sig=None, out_sig=None)

        # OUT ports
        self.message_port_register_out(pmt.intern("freq"))
        self.message_port_register_out(pmt.intern("set_mute"))

        # IN ports
        self.message_port_register_in(pmt.intern("tick"))
        self.set_msg_handler(pmt.intern("tick"), self._on_tick)

        self.message_port_register_in(pmt.intern("edges"))
        self.set_msg_handler(pmt.intern("edges"), self._on_edges)

        # state
        self.rng = random.Random(int(seed))
        self.chan = 0
        self.chan_spacing = float(chan_spacing)
        self.chan_bw_hz = float(chan_bw_hz)
        self.mute_time_s = float(mute_time_s)
        self.guard_hz = float(guard_hz)
        self.num_chans = int(num_chans)
        self.max_attempts = int(max_attempts)

        self.jam_lo = None
        self.jam_hi = None
        self.active = True

    # -------- publishing helpers --------
    def set_active(self, active):
        self.active = bool(active)

    def _pub_freq(self, freq_hz):
        msg = pmt.cons(pmt.intern("freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("freq"), msg)

    def _pub_mute(self, state):
        self.message_port_pub(pmt.intern("set_mute"), pmt.to_pmt(bool(state)))

    def _retune_with_mute(self, freq_hz):
        self._pub_mute(True)
        self._pub_freq(freq_hz)
        threading.Timer(self.mute_time_s, lambda: self._pub_mute(False)).start()

    # -------- jammer logic (overlap-based) --------
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

    # -------- hop grid --------
    def _grid_freq(self, chan):
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

    # -------- message handlers --------
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

            self.jam_lo = lo
            self.jam_hi = hi
        except Exception:
            return

    def _on_tick(self, msg):
        if not self.active:
            self._pub_mute(True)
            self._pub_freq(0.0)
            return

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

        self._retune_with_mute(chosen)
