import pmt
import random
import threading
from gnuradio import gr


class blk(gr.basic_block):
    def __init__(
        self,
        seed=12345,
        center_freq_hz=915e6,
        chan_spacing=200e3,
        chan_bw_hz=60e3,
        mute_time_s=0.02,
        guard_hz=2e3,
        num_chans=25,
        tx_chan=0,
        follow_rx=False,
        active=True,
    ):
        gr.basic_block.__init__(
            self,
            name='FHSS hopper (simple jam-aware channel mask)',
            in_sig=None,
            out_sig=None
        )

        # OUT ports
        self.message_port_register_out(pmt.intern("set_mute"))
        self.message_port_register_out(pmt.intern("rf_freq"))
        self.message_port_register_out(pmt.intern("tx_freq"))
        self.message_port_register_out(pmt.intern("rx_freq"))

        # IN ports
        self.message_port_register_in(pmt.intern("tick"))
        self.set_msg_handler(pmt.intern("tick"), self._on_tick)

        self.message_port_register_in(pmt.intern("edges"))
        self.set_msg_handler(pmt.intern("edges"), self._on_edges)

        # State
        self.rng = random.Random(int(seed))

        self.center_freq_hz = float(center_freq_hz)
        self.chan_spacing = float(chan_spacing)
        self.chan_bw_hz = float(chan_bw_hz)
        self.mute_time_s = float(mute_time_s)
        self.guard_hz = float(guard_hz)
        self.num_chans = int(num_chans)
        self.tx_chan = int(tx_chan)

        if self.num_chans % 2 == 0:
            raise ValueError("num_chans should be odd if you want one channel exactly centered at center_freq_hz")

        self.mid_chan = self.num_chans // 2
        self.chan = self.mid_chan

        # Track the RX center used to interpret relative jammer edges
        self.current_rx_freq_hz = self.center_freq_hz

        self.jam_lo = None
        self.jam_hi = None
        self.active = bool(active)
        self.follow_rx = bool(follow_rx)

        self._retune_lock = threading.Lock()
        self._tx_retune_fn = None
        self._rx_retune_fn = None

    # ---------- external hooks ----------
    def set_tx_retune_fn(self, fn):
        self._tx_retune_fn = fn

    def set_rx_retune_fn(self, fn):
        self._rx_retune_fn = fn

    def set_follow_rx(self, follow_rx):
        self.follow_rx = bool(follow_rx)

    def set_active(self, active):
        self.active = bool(active)

    # ---------- publishing helpers ----------
    def _pub_mute(self, state):
        self.message_port_pub(pmt.intern("set_mute"), pmt.to_pmt(bool(state)))

    def _pub_rf_freq(self, freq_hz):
        msg = pmt.cons(pmt.intern("rf_freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("rf_freq"), msg)

    def _pub_tx_freq(self, freq_hz):
        msg = pmt.cons(pmt.intern("tx_freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("tx_freq"), msg)

    def _pub_rx_freq(self, freq_hz):
        msg = pmt.cons(pmt.intern("rx_freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("rx_freq"), msg)

    # ---------- retune helpers ----------
    def _retune_tx_hw(self, freq_hz):
        if self._tx_retune_fn is None:
            raise RuntimeError("No LimeSDR TX retune callback installed.")
        self._tx_retune_fn(float(freq_hz))

    def _retune_rx_hw(self, freq_hz):
        if self._rx_retune_fn is None:
            raise RuntimeError("No LimeSDR RX retune callback installed.")
        self._rx_retune_fn(float(freq_hz))

    def _retune_with_mute(self, freq_hz):
        with self._retune_lock:
            self._pub_mute(True)

            # Always retune TX
            self._retune_tx_hw(freq_hz)
            self._pub_tx_freq(freq_hz)

            # Optionally retune RX too
            if self.follow_rx:
                self._retune_rx_hw(freq_hz)
                self.current_rx_freq_hz = float(freq_hz)
                self._pub_rx_freq(freq_hz)

            self._pub_rf_freq(freq_hz)
            threading.Timer(self.mute_time_s, lambda: self._pub_mute(False)).start()

    # ---------- jammer/channel logic ----------
    def _is_no_jammer(self):
        return (
            self.jam_lo is None or self.jam_hi is None or
            (self.jam_lo == 0.0 and self.jam_hi == 0.0)
        )

    @staticmethod
    def _overlap(a_lo, a_hi, b_lo, b_hi):
        return (a_lo <= b_hi) and (b_lo <= a_hi)

    def _grid_freq(self, chan):
        offset_index = int(chan) - self.mid_chan
        return self.center_freq_hz + offset_index * self.chan_spacing

    def _chan_band(self, chan):
        f = self._grid_freq(chan)
        half = 0.5 * self.chan_bw_hz
        return (f - half - self.guard_hz, f + half + self.guard_hz)

    def _chan_is_blocked(self, chan):
        if self._is_no_jammer():
            return False

        c_lo, c_hi = self._chan_band(chan)
        return self._overlap(c_lo, c_hi, self.jam_lo, self.jam_hi)

    def _available_chans(self):
        return [c for c in range(self.num_chans) if not self._chan_is_blocked(c)]

    # ---------- message handlers ----------
    def _on_edges(self, msg):
        """
        Expects PMT dict with jammer edges RELATIVE to the current RX center:
            {"f_lo_hz": -1.0e6, "f_hi_hz": +1.0e6}
        Converts them to absolute RF Hz.
        """
        try:
            if not pmt.is_dict(msg):
                return

            lo_p = pmt.dict_ref(msg, pmt.intern("f_lo_hz"), pmt.PMT_NIL)
            hi_p = pmt.dict_ref(msg, pmt.intern("f_hi_hz"), pmt.PMT_NIL)
            if lo_p is pmt.PMT_NIL or hi_p is pmt.PMT_NIL:
                return

            lo_rel = float(pmt.to_double(lo_p))
            hi_rel = float(pmt.to_double(hi_p))
            if hi_rel < lo_rel:
                lo_rel, hi_rel = hi_rel, lo_rel

            # Convert relative/baseband jammer edges to absolute RF jammer edges
            self.jam_lo = self.current_rx_freq_hz + lo_rel
            self.jam_hi = self.current_rx_freq_hz + hi_rel

        except Exception:
            return

    def _on_tick(self, msg):
        if not self.active:
            self._pub_mute(True)
            return

        available = self._available_chans()

        # If everything is blocked, stay where you are
        if not available:
            chosen_chan = self.chan
        else:
            # Prefer not to stay on the same channel if alternatives exist
            choices = [c for c in available if c != self.chan]
            if choices:
                chosen_chan = self.rng.choice(choices)
            else:
                chosen_chan = available[0]

        self.chan = chosen_chan
        chosen_freq = self._grid_freq(self.chan)
        self._retune_with_mute(chosen_freq)