import pmt
import random
import threading
from gnuradio import gr

class blk(gr.basic_block):
    """
    FHSS TX controller with jammer-avoidance.

    Inputs (message ports):
      - "tick": trigger a hop
      - "edges": PMT dict with keys "f_lo_hz" and "f_hi_hz" (baseband jammer edges)

    Outputs (message ports):
      - "freq":  PMT pair ("freq", <double Hz>) to a Freq Xlating FIR 'freq' port
      - "set_mute": PMT bool to a Mute block 'set_mute' port
    """
    def __init__(self, seed=12345, chan_spacing=200e3, mute_time_s=0.02, guard_hz=5e3):
        gr.basic_block.__init__(self, name='FHSS TX controller', in_sig=None, out_sig=None)

        # OUT ports
        self.message_port_register_out(pmt.intern("freq"))       # to Freq Xlating FIR "freq"
        self.message_port_register_out(pmt.intern("set_mute"))   # to Mute block "set_mute"

        # IN ports
        self.message_port_register_in(pmt.intern("tick"))
        self.set_msg_handler(pmt.intern("tick"), self._on_tick)

        # NEW: jammer edges input
        self.message_port_register_in(pmt.intern("edges"))
        self.set_msg_handler(pmt.intern("edges"), self._on_edges)

        # state
        self.rng = random.Random(int(seed))
        self.chan = 0
        self.chan_spacing = float(chan_spacing)
        self.mute_time_s = float(mute_time_s)
        self.guard_hz = float(guard_hz)  # small margin outside jammer band

        self.active = True

        # jammer band (baseband Hz); None means "unknown / ignore"
        self.jam_lo = None
        self.jam_hi = None

    def set_active(self, active: bool):
        self.active = bool(active)

    def _pub_freq(self, freq_hz: float):
        msg = pmt.cons(pmt.intern("freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("freq"), msg)

    def _pub_mute(self, state: bool):
        self.message_port_pub(pmt.intern("set_mute"), pmt.to_pmt(bool(state)))

    # ---------- NEW: receive jammer edges ----------
    def _on_edges(self, msg):
        """
        Expect PMT dict:
          {"f_lo_hz": <double>, "f_hi_hz": <double>}
        """
        try:
            if not pmt.is_dict(msg):
                return

            lo_p = pmt.dict_ref(msg, pmt.intern("f_lo_hz"), pmt.PMT_NIL)
            hi_p = pmt.dict_ref(msg, pmt.intern("f_hi_hz"), pmt.PMT_NIL)
            if lo_p is pmt.PMT_NIL or hi_p is pmt.PMT_NIL:
                return

            lo = float(pmt.to_double(lo_p))
            hi = float(pmt.to_double(hi_p))

            # normalize ordering + sanity
            if hi < lo:
                lo, hi = hi, lo

            self.jam_lo = lo
            self.jam_hi = hi
        except Exception:
            # Never let bad messages crash the flowgraph
            return

    # ---------- jammer avoidance helpers ----------
    def _in_jam_band(self, f_hz: float) -> bool:
        if self.jam_lo is None or self.jam_hi is None:
            return False
        return (self.jam_lo <= f_hz <= self.jam_hi)

    def _move_outside_jam(self, f_hz: float) -> float:
        """
        If f_hz lands inside [jam_lo, jam_hi], move it to the nearest edge
        plus a guard band, then quantize to the nearest channel grid.
        """
        if not self._in_jam_band(f_hz):
            return f_hz

        # nearest side
        dist_lo = abs(f_hz - self.jam_lo)
        dist_hi = abs(self.jam_hi - f_hz)

        if dist_lo <= dist_hi:
            target = self.jam_lo - self.guard_hz
        else:
            target = self.jam_hi + self.guard_hz

        # quantize to channel grid (multiple of chan_spacing)
        # (rounding keeps you on your discrete hop frequencies)
        q = round(target / self.chan_spacing) * self.chan_spacing
        return float(q)

    def _pick_next_chan(self) -> int:
        return (self.chan + self.rng.randint(1, 7)) % 8

    def _on_tick(self, msg):
        if not self.active:
            self._pub_mute(True)
            self._pub_freq(0.0)
            return

        # try a few times to pick a channel not in jammer band
        # (handles the case where quantization still falls inside)
        attempts = 0
        max_attempts = 16

        while True:
            self.chan = self._pick_next_chan()
            freq = +self.chan * self.chan_spacing  # TX shifts UP (baseband)

            # If inside jammer band, move it outside
            freq2 = self._move_outside_jam(freq)

            # If after moving/quantizing it's still jammed, try another hop
            if not self._in_jam_band(freq2) or attempts >= max_attempts:
                freq = freq2
                break

            attempts += 1

        self._pub_mute(True)
        self._pub_freq(freq)
        threading.Timer(self.mute_time_s, lambda: self._pub_mute(False)).start()
