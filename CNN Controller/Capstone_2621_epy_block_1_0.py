import pmt
import random
import threading
from gnuradio import gr


class blk(gr.basic_block):
    def __init__(
        self,
        seed=12345,
        chan_spacing=200e3,
        chan_bw_hz=60e3,
        mute_time_s=0.0,          # legacy hard-mute window if you still want it
        guard_hz=2e3,
        num_chans=25,
        max_attempts=128,
        follow_rx=True,
        active=True,

        # fade / hop timing
        fade_down_s=0.002,
        hop_settle_s=0.001,
        fade_up_s=0.002,

        # gain values used by callbacks
        tx_gain_on=1.0,
        tx_gain_off=0.0,
        rx_gain_on=1.0,
        rx_gain_off=0.0,
    ):
        gr.basic_block.__init__(
            self,
            name="FHSS fixed-center FIR controller with fade timing",
            in_sig=None,
            out_sig=None
        )

        # -----------------------------
        # Message ports
        # -----------------------------
        self.message_port_register_out(pmt.intern("tx_freq"))
        self.message_port_register_out(pmt.intern("rx_freq"))
        self.message_port_register_out(pmt.intern("set_mute"))
        self.message_port_register_out(pmt.intern("hop_info"))

        self.message_port_register_in(pmt.intern("tick"))
        self.set_msg_handler(pmt.intern("tick"), self._on_tick)

        self.message_port_register_in(pmt.intern("edges"))
        self.set_msg_handler(pmt.intern("edges"), self._on_edges)

        # -----------------------------
        # Parameters / state
        # -----------------------------
        self.rng = random.Random(int(seed))

        self.chan_spacing = float(chan_spacing)
        self.chan_bw_hz = float(chan_bw_hz)
        self.mute_time_s = float(mute_time_s)
        self.guard_hz = float(guard_hz)
        self.num_chans = int(num_chans)
        self.max_attempts = int(max_attempts)
        self.follow_rx = bool(follow_rx)
        self.active = bool(active)

        self.fade_down_s = float(fade_down_s)
        self.hop_settle_s = float(hop_settle_s)
        self.fade_up_s = float(fade_up_s)

        self.tx_gain_on = float(tx_gain_on)
        self.tx_gain_off = float(tx_gain_off)
        self.rx_gain_on = float(rx_gain_on)
        self.rx_gain_off = float(rx_gain_off)

        if self.num_chans <= 1:
            raise ValueError("num_chans must be >= 2")
        if self.num_chans % 2 == 0:
            raise ValueError("num_chans should be odd so one channel is exactly at offset 0 Hz")

        self.mid_chan = self.num_chans // 2
        self.chan = self.mid_chan

        self.jam_lo = None
        self.jam_hi = None

        self._hop_lock = threading.Lock()

        # Optional external callbacks
        self._tx_gain_fn = None
        self._rx_gain_fn = None

    # -----------------------------
    # External control
    # -----------------------------
    def set_follow_rx(self, follow_rx):
        self.follow_rx = bool(follow_rx)

    def set_active(self, active):
        self.active = bool(active)

    def set_tx_gain_fn(self, fn):
        """Example: lambda g: self.blocks_multiply_const_vxx_0.set_k(g)"""
        self._tx_gain_fn = fn

    def set_rx_gain_fn(self, fn):
        """Example: lambda g: self.rx_audio_gain_block.set_k(g)"""
        self._rx_gain_fn = fn

    # -----------------------------
    # Publishers
    # -----------------------------
    def _pub_mute(self, state):
        self.message_port_pub(pmt.intern("set_mute"), pmt.to_pmt(bool(state)))

    def _pub_tx_freq(self, offset_hz):
        msg = pmt.cons(pmt.intern("freq"), pmt.from_double(float(offset_hz)))
        self.message_port_pub(pmt.intern("tx_freq"), msg)

    def _pub_rx_freq(self, offset_hz):
        msg = pmt.cons(pmt.intern("freq"), pmt.from_double(float(offset_hz)))
        self.message_port_pub(pmt.intern("rx_freq"), msg)

    def _pub_hop_info(self, chan, offset_hz):
        d = pmt.make_dict()
        d = pmt.dict_add(d, pmt.intern("chan"), pmt.from_long(int(chan)))
        d = pmt.dict_add(d, pmt.intern("offset_hz"), pmt.from_double(float(offset_hz)))
        self.message_port_pub(pmt.intern("hop_info"), d)

    # -----------------------------
    # Gain helpers
    # -----------------------------
    def _set_tx_gain(self, g):
        if self._tx_gain_fn is not None:
            self._tx_gain_fn(float(g))

    def _set_rx_gain(self, g):
        if self._rx_gain_fn is not None:
            self._rx_gain_fn(float(g))

    def _ramp_gain(self, setter, g0, g1, duration_s, steps=8):
        """
        Simple timer-based linear ramp.
        """
        if setter is None or duration_s <= 0 or steps <= 1:
            if setter is not None:
                setter(float(g1))
            return

        dt = duration_s / steps
        for i in range(1, steps + 1):
            gi = g0 + (g1 - g0) * (i / steps)
            threading.Timer(dt * i, lambda val=gi: setter(float(val))).start()

    def _fade_down(self):
        if self._tx_gain_fn is not None:
            self._ramp_gain(self._set_tx_gain, self.tx_gain_on, self.tx_gain_off, self.fade_down_s)
        if self._rx_gain_fn is not None:
            self._ramp_gain(self._set_rx_gain, self.rx_gain_on, self.rx_gain_off, self.fade_down_s)

    def _fade_up(self):
        if self._tx_gain_fn is not None:
            self._ramp_gain(self._set_tx_gain, self.tx_gain_off, self.tx_gain_on, self.fade_up_s)
        if self._rx_gain_fn is not None:
            self._ramp_gain(self._set_rx_gain, self.rx_gain_off, self.rx_gain_on, self.fade_up_s)

    # -----------------------------
    # Apply hop sequence
    # -----------------------------
    def _apply_hop(self, offset_hz):
        self._pub_tx_freq(offset_hz)
        if self.follow_rx:
            self._pub_rx_freq(offset_hz)
        self._pub_hop_info(self.chan, offset_hz)

    def _apply_hop_with_fade(self, offset_hz):
        with self._hop_lock:
            # legacy hard mute signal if you're still wiring it somewhere
            self._pub_mute(True)

            # 1) fade down
            self._fade_down()

            # 2) schedule actual hop after fade-down
            hop_delay = max(0.0, self.fade_down_s)

            def do_hop():
                self._apply_hop(offset_hz)

            threading.Timer(hop_delay, do_hop).start()

            # 3) fade back up after hop settle
            up_delay = hop_delay + max(0.0, self.hop_settle_s)

            def do_fade_up():
                self._fade_up()
                # optional hard unmute release after fade-up begins
                release_delay = max(self.fade_up_s, self.mute_time_s)
                threading.Timer(release_delay, lambda: self._pub_mute(False)).start()

            threading.Timer(up_delay, do_fade_up).start()

    # -----------------------------
    # Jammer helpers
    # Jammer edges are baseband offsets from fixed center
    # -----------------------------
    def _is_no_jammer(self):
        return (
            self.jam_lo is None or self.jam_hi is None or
            (self.jam_lo == 0.0 and self.jam_hi == 0.0)
        )

    @staticmethod
    def _overlap(a_lo, a_hi, b_lo, b_hi):
        return (a_lo <= b_hi) and (b_lo <= a_hi)

    def _hop_band(self, offset_hz):
        half = 0.5 * self.chan_bw_hz
        return (
            offset_hz - half - self.guard_hz,
            offset_hz + half + self.guard_hz
        )

    def _hop_overlaps_jam(self, offset_hz):
        if self._is_no_jammer():
            return False
        c_lo, c_hi = self._hop_band(offset_hz)
        return self._overlap(c_lo, c_hi, self.jam_lo, self.jam_hi)

    # -----------------------------
    # Channel grid
    # -----------------------------
    def _grid_offset(self, chan):
        offset_index = int(chan) - self.mid_chan
        return offset_index * self.chan_spacing

    def _pick_next_chan(self):
        step = self.rng.randint(1, self.num_chans - 1)
        return (self.chan + step) % self.num_chans

    def _nearest_valid_chan_for_offset(self, offset_hz):
        idx = round(offset_hz / self.chan_spacing) + self.mid_chan
        idx = max(0, min(self.num_chans - 1, idx))
        return idx

    def _move_offset_to_clear_jam(self, offset_hz):
        if not self._hop_overlaps_jam(offset_hz):
            return offset_hz

        half = 0.5 * self.chan_bw_hz
        need_below = self.jam_lo - self.guard_hz - half
        need_above = self.jam_hi + self.guard_hz + half

        if abs(offset_hz - need_below) <= abs(need_above - offset_hz):
            chan = self._nearest_valid_chan_for_offset(need_below)
        else:
            chan = self._nearest_valid_chan_for_offset(need_above)

        return self._grid_offset(chan)

    def _fallback_safe_offset(self):
        for c in range(self.num_chans):
            off = self._grid_offset(c)
            if not self._hop_overlaps_jam(off):
                return off
        return self._grid_offset(self.mid_chan)

    # -----------------------------
    # Message handlers
    # -----------------------------
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
            return

        chosen = None
        attempts = 0

        while attempts < self.max_attempts:
            next_chan = self._pick_next_chan()
            off = self._grid_offset(next_chan)

            off2 = self._move_offset_to_clear_jam(off)

            if not self._hop_overlaps_jam(off2):
                chosen = off2
                self.chan = self._nearest_valid_chan_for_offset(off2)
                break

            attempts += 1

        if chosen is None:
            chosen = self._fallback_safe_offset()
            self.chan = self._nearest_valid_chan_for_offset(chosen)

        self._apply_hop_with_fade(chosen)