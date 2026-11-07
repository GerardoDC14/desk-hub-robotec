"""Nivel real, privacidad, caducidad y coste de dibujo del indicador musical."""
import math
import struct
import threading
import unittest
from unittest.mock import Mock, patch
from test_dashboard import hub
from audio_meter import COMMAND, OutputMeter, pcm_level
from visual_assets import player_symbol


class OutputMeterTests(unittest.TestCase):
    def test_pcm_silence_and_amplitude(self):
        self.assertEqual(pcm_level(b'\0'*2000),0)
        self.assertEqual(pcm_level(b''),0)
        def signal(amplitude):
            return struct.pack('<1000h',*(round(amplitude*math.sin(i*.2)) for i in range(1000)))
        self.assertLess(pcm_level(signal(200)),pcm_level(signal(12000)))
        self.assertLessEqual(pcm_level(signal(32767)),1)

    def test_monitor_is_output_only_and_does_not_write_files(self):
        self.assertIn('--device=@DEFAULT_MONITOR@',COMMAND)
        self.assertNotIn('--file-format',COMMAND)
        self.assertNotIn('--device=@DEFAULT_SOURCE@',COMMAND)

    def meter(self):
        with patch('audio_meter.threading.Thread'): return OutputMeter(threading.Event())

    def test_bounded_history_and_old_generation_rejected(self):
        meter=self.meter();meter.set_enabled(True);generation=meter.generation
        for _ in range(40):meter._publish(generation,struct.pack('<1000h',*([10000]*1000)))
        self.assertEqual(len(meter.snapshot()),16);self.assertGreater(min(meter.snapshot()),0)
        meter.set_enabled(False);meter.set_enabled(True)
        meter._publish(generation,struct.pack('<1000h',*([30000]*1000)))
        self.assertEqual(meter.snapshot(),(0.0,)*16)

    def test_only_local_playing_music_enables_meter(self):
        h=hub();h.output_meter=Mock()
        for screen,unlocked,status,active,expected in (
            ('music',True,'playing',True,True),('music',True,'paused',True,False),
            ('music',True,'playing',False,False),('home',True,'playing',True,False),
            ('music',False,'playing',True,False)):
            h.screen=screen;h.unlocked=unlocked;h.music.update(status=status,is_active=active,_ready=active)
            h.prepare_experience();h.output_meter.set_enabled.assert_called_with(expected)
        h.unlocked=True;h.navigate('home');h.output_meter.set_enabled.assert_called_with(False)

    def test_bars_use_small_deltas_without_touching_cover_or_text(self):
        h=hub();h.output_meter=Mock();h.output_meter.snapshot.return_value=(.2,)*16
        commands=[];h.send=commands.append;h.draw_output_meter(True);commands.clear()
        h.draw_output_meter(True);self.assertEqual(commands,[])
        h.output_meter.snapshot.return_value=(.7,)*16;h.draw_output_meter(True)
        self.assertEqual(len(commands),16)
        for command in commands:
            self.assertTrue(command.startswith('fill '))
            x,y,w,height,color=map(int,command[5:].split(','))
            self.assertTrue(416<=x<x+w<=768 and 218<=y<y+height<=246)
        commands.clear();h.draw_output_meter(False)
        self.assertLessEqual(len(commands),32)

    def test_skip_symbols_are_centered_inside_both_circles(self):
        for radius in (24,26,30):
            for icon in ('prev','next'):
                side,pixels=player_symbol(radius,icon,65535,0,0)
                points=[(i%side,i//side) for i,p in enumerate(pixels) if p==65535]
                self.assertTrue(points)
                for axis in (0,1):
                    bounds=[p[axis] for p in points]
                    self.assertLessEqual(abs((min(bounds)+max(bounds))/2-(radius+1)),1,(radius,icon,axis))
