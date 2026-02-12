import pmt
import random
import threading
from gnuradio import gr

class blk(gr.basic_block):
    def __init__(self, seed=12345, chan_spacing=200e3, mute_time_s=0.02):
        gr.basic_block.__init__(self, name='FHSS RX controller', in_sig=None, out_sig=None)

        # OUT ports
        self.message_port_register_out(pmt.intern("freq"))       # to Freq Xlating FIR "freq"
        self.message_port_register_out(pmt.intern("set_mute"))   # to Mute block "set_mute"

        # IN port
        self.message_port_register_in(pmt.intern("tick"))
        self.set_msg_handler(pmt.intern("tick"), self._on_tick)

        self.rng = random.Random(int(seed))
        self.chan = 0
        self.chan_spacing = float(chan_spacing)
        self.mute_time_s = float(mute_time_s)

        self.active = True

    def set_active(self, active: bool):
        self.active = bool(active)

    def _pub_freq(self, freq_hz: float):
        msg = pmt.cons(pmt.intern("freq"), pmt.from_double(float(freq_hz)))
        self.message_port_pub(pmt.intern("freq"), msg)

    def _pub_mute(self, state: bool):
        # Mute expects raw PMT bool
        self.message_port_pub(pmt.intern("set_mute"), pmt.to_pmt(bool(state)))

    def _on_tick(self, msg):
        if not self.active:
            # optional: keep muted + zero shift when inactive
            self._pub_mute(True)
            self._pub_freq(0.0)
            return

        # Next hop (same sequence as TX because same seed + same rng usage)
        self.chan = (self.chan + self.rng.randint(1, 7)) % 8
        freq = -self.chan * self.chan_spacing  # RX shifts DOWN

        # Mute → retune → unmute
        self._pub_mute(True)
        self._pub_freq(freq)
        threading.Timer(self.mute_time_s, lambda: self._pub_mute(False)).start()
