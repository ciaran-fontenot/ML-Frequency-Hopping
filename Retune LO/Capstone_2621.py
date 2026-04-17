#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Frequency Hopping Spread Spectrum
# GNU Radio version: 3.10.9.2

from PyQt5 import Qt
from gnuradio import qtgui
from PyQt5 import QtCore
from gnuradio import analog
from gnuradio import audio
from gnuradio import blocks
import pmt
from gnuradio import blocks, gr
from gnuradio import fft
from gnuradio.fft import window
from gnuradio import filter
from gnuradio.filter import firdes
from gnuradio import gr
import sys
import signal
from PyQt5 import Qt
from argparse import ArgumentParser
from gnuradio.eng_arg import eng_float, intx
from gnuradio import eng_notation
import Capstone_2621_epy_block_0 as epy_block_0  # embedded python block
import Capstone_2621_epy_block_1_0 as epy_block_1_0  # embedded python block
import limesdr
import math
import sip


def snipfcn_snippet_0(self):
    print("[TOP] snippet running")

    def retune_tx(f):
            print(f"[TOP] retuning TX to {f/1e6:.3f} MHz")
            self.limesdr_sink_0.set_center_freq(f, 0)

    def retune_rx(f):
            print(f"[TOP] retuning RX to {f/1e6:.3f} MHz")
            self.limesdr_source_0.set_center_freq(f, 0)

    self.epy_block_1_0.set_tx_retune_fn(retune_tx)
    self.epy_block_1_0.set_rx_retune_fn(retune_rx)


def snippets_main_after_init(tb):
    snipfcn_snippet_0(tb)

class Capstone_2621(gr.top_block, Qt.QWidget):

    def __init__(self):
        gr.top_block.__init__(self, "Frequency Hopping Spread Spectrum", catch_exceptions=True)
        Qt.QWidget.__init__(self)
        self.setWindowTitle("Frequency Hopping Spread Spectrum")
        qtgui.util.check_set_qss()
        try:
            self.setWindowIcon(Qt.QIcon.fromTheme('gnuradio-grc'))
        except BaseException as exc:
            print(f"Qt GUI: Could not set Icon: {str(exc)}", file=sys.stderr)
        self.top_scroll_layout = Qt.QVBoxLayout()
        self.setLayout(self.top_scroll_layout)
        self.top_scroll = Qt.QScrollArea()
        self.top_scroll.setFrameStyle(Qt.QFrame.NoFrame)
        self.top_scroll_layout.addWidget(self.top_scroll)
        self.top_scroll.setWidgetResizable(True)
        self.top_widget = Qt.QWidget()
        self.top_scroll.setWidget(self.top_widget)
        self.top_layout = Qt.QVBoxLayout(self.top_widget)
        self.top_grid_layout = Qt.QGridLayout()
        self.top_layout.addLayout(self.top_grid_layout)

        self.settings = Qt.QSettings("GNU Radio", "Capstone_2621")

        try:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        except BaseException as exc:
            print(f"Qt GUI: Could not restore geometry: {str(exc)}", file=sys.stderr)

        ##################################################
        # Variables
        ##################################################
        self.xlate_freq = xlate_freq = 0
        self.vol_lvl = vol_lvl = 0.001
        self.samp_rate = samp_rate = 4.8e6
        self.noise_lvl = noise_lvl = 0
        self.jamming_range = jamming_range = 500e3

        ##################################################
        # Blocks
        ##################################################

        self.tab = Qt.QTabWidget()
        self.tab_widget_0 = Qt.QWidget()
        self.tab_layout_0 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tab_widget_0)
        self.tab_grid_layout_0 = Qt.QGridLayout()
        self.tab_layout_0.addLayout(self.tab_grid_layout_0)
        self.tab.addTab(self.tab_widget_0, 'TX and Channel')
        self.tab_widget_1 = Qt.QWidget()
        self.tab_layout_1 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tab_widget_1)
        self.tab_grid_layout_1 = Qt.QGridLayout()
        self.tab_layout_1.addLayout(self.tab_grid_layout_1)
        self.tab.addTab(self.tab_widget_1, 'RX')
        self.tab_widget_2 = Qt.QWidget()
        self.tab_layout_2 = Qt.QBoxLayout(Qt.QBoxLayout.TopToBottom, self.tab_widget_2)
        self.tab_grid_layout_2 = Qt.QGridLayout()
        self.tab_layout_2.addLayout(self.tab_grid_layout_2)
        self.tab.addTab(self.tab_widget_2, 'Audio')
        self.top_layout.addWidget(self.tab)
        self._noise_lvl_range = qtgui.Range(0, 0.1, 0.01, 0, 200)
        self._noise_lvl_win = qtgui.RangeWidget(self._noise_lvl_range, self.set_noise_lvl, "Noise Lvl", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._noise_lvl_win)
        self._jamming_range_range = qtgui.Range(500, 100e4, 1, 500e3, 200)
        self._jamming_range_win = qtgui.RangeWidget(self._jamming_range_range, self.set_jamming_range, "Jamming Range", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._jamming_range_win)
        self._xlate_freq_range = qtgui.Range(-5e6, 5e6, 5e4, 0, 200)
        self._xlate_freq_win = qtgui.RangeWidget(self._xlate_freq_range, self.set_xlate_freq, "'xlate_freq'", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._xlate_freq_win)
        self._vol_lvl_range = qtgui.Range(0, 0.005, 0.0001, 0.001, 200)
        self._vol_lvl_win = qtgui.RangeWidget(self._vol_lvl_range, self.set_vol_lvl, "Volume Lvl", "counter_slider", float, QtCore.Qt.Horizontal)
        self.top_layout.addWidget(self._vol_lvl_win)
        self.rational_resampler_xxx_1 = filter.rational_resampler_fff(
                interpolation=100,
                decimation=1,
                taps=[],
                fractional_bw=0)
        self.qtgui_waterfall_sink_x_1_0 = qtgui.waterfall_sink_c(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "RX Signal before LPF", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_1_0.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_1_0.enable_grid(False)
        self.qtgui_waterfall_sink_x_1_0.enable_axis_labels(True)



        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_1_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_1_0.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_1_0.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_1_0.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_1_0.set_intensity_range(-60, -30)

        self._qtgui_waterfall_sink_x_1_0_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_1_0.qwidget(), Qt.QWidget)

        self.tab_layout_1.addWidget(self._qtgui_waterfall_sink_x_1_0_win)
        self.qtgui_waterfall_sink_x_1 = qtgui.waterfall_sink_c(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "RX Signal after LPF", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_1.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_1.enable_grid(False)
        self.qtgui_waterfall_sink_x_1.enable_axis_labels(True)



        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_1.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_1.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_1.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_1.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_1.set_intensity_range(-140, 10)

        self._qtgui_waterfall_sink_x_1_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_1.qwidget(), Qt.QWidget)

        self.tab_layout_1.addWidget(self._qtgui_waterfall_sink_x_1_win)
        self.qtgui_waterfall_sink_x_0_0_0 = qtgui.waterfall_sink_c(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "Jamming", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_0_0_0.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_0_0_0.enable_grid(False)
        self.qtgui_waterfall_sink_x_0_0_0.enable_axis_labels(True)



        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_0_0_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_0_0_0.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_0_0_0.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_0_0_0.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_0_0_0.set_intensity_range(-140, 10)

        self._qtgui_waterfall_sink_x_0_0_0_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_0_0_0.qwidget(), Qt.QWidget)

        self.tab_layout_0.addWidget(self._qtgui_waterfall_sink_x_0_0_0_win)
        self.qtgui_waterfall_sink_x_0_0 = qtgui.waterfall_sink_c(
            2048, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "Channel", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_0_0.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_0_0.enable_grid(False)
        self.qtgui_waterfall_sink_x_0_0.enable_axis_labels(True)



        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_0_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_0_0.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_0_0.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_0_0.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_0_0.set_intensity_range(-140, 10)

        self._qtgui_waterfall_sink_x_0_0_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_0_0.qwidget(), Qt.QWidget)

        self.tab_layout_0.addWidget(self._qtgui_waterfall_sink_x_0_0_win)
        self.qtgui_waterfall_sink_x_0 = qtgui.waterfall_sink_c(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "TX Signal", #name
            1, #number of inputs
            None # parent
        )
        self.qtgui_waterfall_sink_x_0.set_update_time(0.10)
        self.qtgui_waterfall_sink_x_0.enable_grid(False)
        self.qtgui_waterfall_sink_x_0.enable_axis_labels(True)



        labels = ['', '', '', '', '',
                  '', '', '', '', '']
        colors = [0, 0, 0, 0, 0,
                  0, 0, 0, 0, 0]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
                  1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_waterfall_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_waterfall_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_waterfall_sink_x_0.set_color_map(i, colors[i])
            self.qtgui_waterfall_sink_x_0.set_line_alpha(i, alphas[i])

        self.qtgui_waterfall_sink_x_0.set_intensity_range(-140, 10)

        self._qtgui_waterfall_sink_x_0_win = sip.wrapinstance(self.qtgui_waterfall_sink_x_0.qwidget(), Qt.QWidget)

        self.tab_layout_0.addWidget(self._qtgui_waterfall_sink_x_0_win)
        self.qtgui_freq_sink_x_0 = qtgui.freq_sink_f(
            1024, #size
            window.WIN_BLACKMAN_hARRIS, #wintype
            0, #fc
            samp_rate, #bw
            "", #name
            1,
            None # parent
        )
        self.qtgui_freq_sink_x_0.set_update_time(0.01)
        self.qtgui_freq_sink_x_0.set_y_axis((-140), 10)
        self.qtgui_freq_sink_x_0.set_y_label('Relative Gain', 'dB')
        self.qtgui_freq_sink_x_0.set_trigger_mode(qtgui.TRIG_MODE_FREE, 0.0, 0, "")
        self.qtgui_freq_sink_x_0.enable_autoscale(False)
        self.qtgui_freq_sink_x_0.enable_grid(False)
        self.qtgui_freq_sink_x_0.set_fft_average(1.0)
        self.qtgui_freq_sink_x_0.enable_axis_labels(True)
        self.qtgui_freq_sink_x_0.enable_control_panel(False)
        self.qtgui_freq_sink_x_0.set_fft_window_normalized(False)


        self.qtgui_freq_sink_x_0.set_plot_pos_half(not True)

        labels = ['', '', '', '', '',
            '', '', '', '', '']
        widths = [1, 1, 1, 1, 1,
            1, 1, 1, 1, 1]
        colors = ["blue", "red", "green", "black", "cyan",
            "magenta", "yellow", "dark red", "dark green", "dark blue"]
        alphas = [1.0, 1.0, 1.0, 1.0, 1.0,
            1.0, 1.0, 1.0, 1.0, 1.0]

        for i in range(1):
            if len(labels[i]) == 0:
                self.qtgui_freq_sink_x_0.set_line_label(i, "Data {0}".format(i))
            else:
                self.qtgui_freq_sink_x_0.set_line_label(i, labels[i])
            self.qtgui_freq_sink_x_0.set_line_width(i, widths[i])
            self.qtgui_freq_sink_x_0.set_line_color(i, colors[i])
            self.qtgui_freq_sink_x_0.set_line_alpha(i, alphas[i])

        self._qtgui_freq_sink_x_0_win = sip.wrapinstance(self.qtgui_freq_sink_x_0.qwidget(), Qt.QWidget)
        self.tab_layout_2.addWidget(self._qtgui_freq_sink_x_0_win)
        self.limesdr_source_0 = limesdr.source('', 0, '', False)


        self.limesdr_source_0.set_sample_rate(samp_rate)


        self.limesdr_source_0.set_center_freq(914e6, 0)

        self.limesdr_source_0.set_bandwidth(samp_rate, 0)


        self.limesdr_source_0.set_digital_filter(2.5e6, 0)


        self.limesdr_source_0.set_gain(30, 0)


        self.limesdr_source_0.set_antenna(2, 0)


        self.limesdr_source_0.calibrate(2.5e6, 0)
        self.limesdr_sink_0 = limesdr.sink('', 0, '', '')


        self.limesdr_sink_0.set_sample_rate(samp_rate)


        self.limesdr_sink_0.set_center_freq(914e6, 0)

        self.limesdr_sink_0.set_bandwidth(5e6, 0)


        self.limesdr_sink_0.set_digital_filter(samp_rate, 0)


        self.limesdr_sink_0.set_gain(20, 0)


        self.limesdr_sink_0.set_antenna(255, 0)


        self.limesdr_sink_0.calibrate(2.5e6, 0)
        self.freq_xlating_fir_filter_xxx_2 = filter.freq_xlating_fir_filter_ccc(1, [1], 0, samp_rate)
        self.filter_fft_low_pass_filter_4 = filter.fft_filter_fff(1, firdes.low_pass(1, samp_rate, 200e3, 2e3, window.WIN_HAMMING, 6.76), 1)
        self.filter_fft_low_pass_filter_3 = filter.fft_filter_ccc(1, firdes.low_pass(1, samp_rate, 8e3, 1e3, window.WIN_HAMMING, 6.76), 1)
        self.filter_fft_low_pass_filter_2 = filter.fft_filter_ccc(1, firdes.low_pass(1, samp_rate, 8e3, 1e3, window.WIN_HAMMING, 6.76), 1)
        self.filter_fft_low_pass_filter_1 = filter.fft_filter_ccc(1, firdes.low_pass(1, samp_rate, 10e3, 2e3, window.WIN_HAMMING, 6.76), 1)
        self.filter_fft_low_pass_filter_0 = filter.fft_filter_ccc(1, firdes.low_pass(1, samp_rate, jamming_range, 100, window.WIN_HAMMING, 6.76), 1)
        self.fft_vxx_0 = fft.fft_vcc(1024, True, window.blackmanharris(1024), True, 1)
        self.epy_block_1_0 = epy_block_1_0.blk(seed=1, center_freq_hz=914e6, chan_spacing=100e3, chan_bw_hz=60e3, mute_time_s=1e-2, guard_hz=1000, num_chans=25, tx_chan=0, follow_rx=False, active=True)
        self.epy_block_0 = epy_block_0.blk(samp_rate=4.8e6, nfft=1024, thresh_db=40, publish_every=10000)
        self.blocks_wavfile_source_0 = blocks.wavfile_source('/home/ciaran/Downloads/1-04. Welcome To The World of Pokemon! ~ Route 123.mp3', True)
        self.blocks_var_to_msg_0 = blocks.var_to_msg_pair('freq')
        self.blocks_throttle2_0_0_0 = blocks.throttle( gr.sizeof_gr_complex*1024, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_throttle2_0_0 = blocks.throttle( gr.sizeof_gr_complex*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_throttle2_0 = blocks.throttle( gr.sizeof_gr_complex*1, samp_rate, True, 0 if "auto" == "auto" else max( int(float(0.1) * samp_rate) if "auto" == "time" else int(0.1), 1) )
        self.blocks_stream_to_vector_0 = blocks.stream_to_vector(gr.sizeof_gr_complex*1, 1024)
        self.blocks_multiply_const_vxx_1 = blocks.multiply_const_cc(1)
        self.blocks_message_strobe_0 = blocks.message_strobe(pmt.intern("TEST"), 100)
        self.blocks_message_debug_0 = blocks.message_debug(True, gr.log_levels.info)
        self.blocks_complex_to_mag_squared_0 = blocks.complex_to_mag_squared(1024)
        self.audio_sink_0 = audio.sink(48000, '', True)
        self.analog_simple_squelch_cc_0 = analog.simple_squelch_cc((-50), 1)
        self.analog_noise_source_x_0 = analog.noise_source_c(analog.GR_GAUSSIAN, noise_lvl, 0)
        self.analog_nbfm_rx_0 = analog.nbfm_rx(
        	audio_rate=48000,
        	quad_rate=4800000,
        	tau=(75e-6),
        	max_dev=5e3,
          )
        self.analog_frequency_modulator_fc_0 = analog.frequency_modulator_fc((2*math.pi*(5e3)/samp_rate))


        ##################################################
        # Connections
        ##################################################
        self.msg_connect((self.blocks_message_strobe_0, 'strobe'), (self.epy_block_1_0, 'tick'))
        self.msg_connect((self.blocks_var_to_msg_0, 'msgout'), (self.freq_xlating_fir_filter_xxx_2, 'freq'))
        self.msg_connect((self.epy_block_0, 'edges'), (self.blocks_message_debug_0, 'print'))
        self.msg_connect((self.epy_block_0, 'edges'), (self.epy_block_1_0, 'edges'))
        self.connect((self.analog_frequency_modulator_fc_0, 0), (self.filter_fft_low_pass_filter_3, 0))
        self.connect((self.analog_nbfm_rx_0, 0), (self.filter_fft_low_pass_filter_4, 0))
        self.connect((self.analog_nbfm_rx_0, 0), (self.qtgui_freq_sink_x_0, 0))
        self.connect((self.analog_noise_source_x_0, 0), (self.filter_fft_low_pass_filter_0, 0))
        self.connect((self.analog_simple_squelch_cc_0, 0), (self.analog_nbfm_rx_0, 0))
        self.connect((self.blocks_complex_to_mag_squared_0, 0), (self.epy_block_0, 0))
        self.connect((self.blocks_multiply_const_vxx_1, 0), (self.blocks_throttle2_0, 0))
        self.connect((self.blocks_multiply_const_vxx_1, 0), (self.limesdr_sink_0, 0))
        self.connect((self.blocks_multiply_const_vxx_1, 0), (self.qtgui_waterfall_sink_x_0, 0))
        self.connect((self.blocks_multiply_const_vxx_1, 0), (self.qtgui_waterfall_sink_x_0_0, 0))
        self.connect((self.blocks_stream_to_vector_0, 0), (self.fft_vxx_0, 0))
        self.connect((self.blocks_throttle2_0_0, 0), (self.blocks_stream_to_vector_0, 0))
        self.connect((self.blocks_throttle2_0_0, 0), (self.qtgui_waterfall_sink_x_0_0_0, 0))
        self.connect((self.blocks_throttle2_0_0_0, 0), (self.blocks_complex_to_mag_squared_0, 0))
        self.connect((self.blocks_wavfile_source_0, 0), (self.rational_resampler_xxx_1, 0))
        self.connect((self.fft_vxx_0, 0), (self.blocks_throttle2_0_0_0, 0))
        self.connect((self.filter_fft_low_pass_filter_0, 0), (self.freq_xlating_fir_filter_xxx_2, 0))
        self.connect((self.filter_fft_low_pass_filter_1, 0), (self.analog_simple_squelch_cc_0, 0))
        self.connect((self.filter_fft_low_pass_filter_1, 0), (self.qtgui_waterfall_sink_x_1, 0))
        self.connect((self.filter_fft_low_pass_filter_2, 0), (self.blocks_multiply_const_vxx_1, 0))
        self.connect((self.filter_fft_low_pass_filter_3, 0), (self.filter_fft_low_pass_filter_2, 0))
        self.connect((self.filter_fft_low_pass_filter_4, 0), (self.audio_sink_0, 0))
        self.connect((self.freq_xlating_fir_filter_xxx_2, 0), (self.blocks_throttle2_0_0, 0))
        self.connect((self.limesdr_source_0, 0), (self.filter_fft_low_pass_filter_1, 0))
        self.connect((self.limesdr_source_0, 0), (self.qtgui_waterfall_sink_x_1_0, 0))
        self.connect((self.rational_resampler_xxx_1, 0), (self.analog_frequency_modulator_fc_0, 0))


    def closeEvent(self, event):
        self.settings = Qt.QSettings("GNU Radio", "Capstone_2621")
        self.settings.setValue("geometry", self.saveGeometry())
        self.stop()
        self.wait()

        event.accept()

    def get_xlate_freq(self):
        return self.xlate_freq

    def set_xlate_freq(self, xlate_freq):
        self.xlate_freq = xlate_freq
        self.blocks_var_to_msg_0.variable_changed(self.xlate_freq)

    def get_vol_lvl(self):
        return self.vol_lvl

    def set_vol_lvl(self, vol_lvl):
        self.vol_lvl = vol_lvl

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.analog_frequency_modulator_fc_0.set_sensitivity((2*math.pi*(5e3)/self.samp_rate))
        self.blocks_throttle2_0.set_sample_rate(self.samp_rate)
        self.blocks_throttle2_0_0.set_sample_rate(self.samp_rate)
        self.blocks_throttle2_0_0_0.set_sample_rate(self.samp_rate)
        self.filter_fft_low_pass_filter_0.set_taps(firdes.low_pass(1, self.samp_rate, self.jamming_range, 100, window.WIN_HAMMING, 6.76))
        self.filter_fft_low_pass_filter_1.set_taps(firdes.low_pass(1, self.samp_rate, 10e3, 2e3, window.WIN_HAMMING, 6.76))
        self.filter_fft_low_pass_filter_2.set_taps(firdes.low_pass(1, self.samp_rate, 8e3, 1e3, window.WIN_HAMMING, 6.76))
        self.filter_fft_low_pass_filter_3.set_taps(firdes.low_pass(1, self.samp_rate, 8e3, 1e3, window.WIN_HAMMING, 6.76))
        self.filter_fft_low_pass_filter_4.set_taps(firdes.low_pass(1, self.samp_rate, 200e3, 2e3, window.WIN_HAMMING, 6.76))
        self.limesdr_sink_0.set_digital_filter(self.samp_rate, 0)
        self.limesdr_sink_0.set_digital_filter(self.samp_rate, 1)
        self.limesdr_source_0.set_bandwidth(self.samp_rate, 0)
        self.limesdr_source_0.set_digital_filter(self.samp_rate, 1)
        self.qtgui_freq_sink_x_0.set_frequency_range(0, self.samp_rate)
        self.qtgui_waterfall_sink_x_0.set_frequency_range(0, self.samp_rate)
        self.qtgui_waterfall_sink_x_0_0.set_frequency_range(0, self.samp_rate)
        self.qtgui_waterfall_sink_x_0_0_0.set_frequency_range(0, self.samp_rate)
        self.qtgui_waterfall_sink_x_1.set_frequency_range(0, self.samp_rate)
        self.qtgui_waterfall_sink_x_1_0.set_frequency_range(0, self.samp_rate)

    def get_noise_lvl(self):
        return self.noise_lvl

    def set_noise_lvl(self, noise_lvl):
        self.noise_lvl = noise_lvl
        self.analog_noise_source_x_0.set_amplitude(self.noise_lvl)

    def get_jamming_range(self):
        return self.jamming_range

    def set_jamming_range(self, jamming_range):
        self.jamming_range = jamming_range
        self.filter_fft_low_pass_filter_0.set_taps(firdes.low_pass(1, self.samp_rate, self.jamming_range, 100, window.WIN_HAMMING, 6.76))




def main(top_block_cls=Capstone_2621, options=None):

    qapp = Qt.QApplication(sys.argv)

    tb = top_block_cls()
    snippets_main_after_init(tb)
    tb.start()

    tb.show()

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        Qt.QApplication.quit()

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    timer = Qt.QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    qapp.exec_()

if __name__ == '__main__':
    main()
