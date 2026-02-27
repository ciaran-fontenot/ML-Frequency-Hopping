import pmt
import random
import threading
from gnuradio import gr

class blk(gr.basic_block):
    """
    FHSS RX controller that follows the transmitter's hopping decisions.

    Inputs (message ports):
      - "tick":     fallback hop trigger (optional; can be disconnected)
      - "tx_freq":  PMT pair ("freq", <double Hz>) from the TX controller

    Outputs (message ports):
      - "freq":      PMT pair ("freq", <double Hz>) to RX Freq Xlating FIR "freq"
      - "set_mute":  PMT bool to Mute block "set_mute"

    Behavior:
      - When a tx_freq arrives, RX mutes, tunes to the *negative* of TX shift,
        then unmutes after mute_time_s.
      - If no tx_freq has been seen yet, it can optionally hop using the RNG
        on ticks (set follow_only=True to disable fallback).
    """
    def __init__(self, seed=12345, chan_spacing=200e3, mute_time_s=0.02, follow_only=True, num_chans=8):
        gr.basic_block.__init__(self, name='FHSS RX controller (follows TX)', in_sig=None, out_sig=None)

        # OUT ports
        self.message_port_register_out(pmt.intern("freq"))       # to RX Freq Xlating FIR "freq"
        self.message_port_register_out(pmt.intern("set_mute"))   # to Mute block "set_mute"

        # IN ports
        self.message_port_register_in(pmt.intern("tick"))
        self.set_msg_handler(pmt.intern("tick"), self._on_tick)

        # NEW: follow TX
        self.message_port_register_in(pmt.intern("tx_freq"))
        self.set_msg_handler(pmt.intern("tx_freq"), self._on_tx_freq)

        # Optional jammer channel hints from spectrum classifier/data capture path
        self.message_port_register_in(pmt.intern("jam_channels"))
        self.set_msg_handler(pmt.intern("jam_channels"), self._on_jam_channels)

        self.rng = random.Random(int(seed))
        self.chan = 0
        self.chan_spacing = float(chan_spacing)
        self.mute_time_s = float(mute_time_s)
        self.follow_only = bool(follow_only)
        self.num_chans = max(2, int(num_chans))

        self.active = True
        self._have_tx = False
        self._jam_channels = set()

    def set_active(self, active: bool):
        self.active = bool(active)

    def _pub_freq(self, freq_hz: float):
        msg = pmt.cons(pmt.intern("freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("freq"), msg)

    def _pub_mute(self, state: bool):
        self.message_port_pub(pmt.intern("set_mute"), pmt.to_pmt(bool(state)))

    def _retune_with_mute(self, freq_hz: float):
        # Mute → retune → unmute
        self._pub_mute(True)
        self._pub_freq(freq_hz)
        threading.Timer(self.mute_time_s, lambda: self._pub_mute(False)).start()

    def _on_tx_freq(self, msg):
        """
        Expect a PMT pair like: ( "freq" . <double> )
        from the TX controller. RX uses the opposite sign.
        """
        if not self.active:
            self._pub_mute(True)
            self._pub_freq(0.0)
            return

        try:
            # Accept either a pair ("freq" . value) or a dict {"freq": value}
            tx_f = None

            if pmt.is_pair(msg):
                key = pmt.car(msg)
                val = pmt.cdr(msg)
                if pmt.is_symbol(key) and pmt.symbol_to_string(key) == "freq":
                    tx_f = float(pmt.to_double(val))

            elif pmt.is_dict(msg):
                v = pmt.dict_ref(msg, pmt.intern("freq"), pmt.PMT_NIL)
                if v is not pmt.PMT_NIL:
                    tx_f = float(pmt.to_double(v))

            if tx_f is None:
                return

            self._have_tx = True

            # TX shifts UP (+). RX must shift DOWN (-TX) to follow.
            rx_f = -tx_f
            self._retune_with_mute(rx_f)

        except Exception:
            # Don't crash the flowgraph on bad messages
            return


    def _on_jam_channels(self, msg):
        try:
            chs = set()
            if pmt.is_u32vector(msg):
                vals = pmt.u32vector_elements(msg)
                chs = {int(v) for v in vals}
            elif pmt.is_pair(msg):
                # graceful fallback if sent as ("channels" . u32vector)
                msg = pmt.cdr(msg)
                if pmt.is_u32vector(msg):
                    chs = {int(v) for v in pmt.u32vector_elements(msg)}
            self._jam_channels = chs
        except Exception:
            return

    def _on_tick(self, msg):
        """
        Optional fallback: if you aren't wired to TX messages, or you want RX
        to free-run until it hears TX, it can hop using the same RNG.
        """
        if not self.active:
            self._pub_mute(True)
            self._pub_freq(0.0)
            return

        if self.follow_only and self._have_tx:
            # Once we're following TX, ignore ticks.
            return

        # Fallback hop with jammer-aware channel skip if hints exist.
        tries = 0
        while tries < 16:
            self.chan = (self.chan + self.rng.randint(1, self.num_chans - 1)) % self.num_chans
            if self._jam_channels and self.chan in self._jam_channels:
                tries += 1
                continue
            break

        freq = -self.chan * self.chan_spacing  # RX shifts DOWN
        self._retune_with_mute(freq)
