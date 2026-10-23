import datetime as dt
import math
from pathlib import Path
import queue
import random
import sys
import threading
import unittest
from collections import deque, OrderedDict
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw
from dashboard_state import Alarm
from music_state import apply_event, position_ms
from robotec import Robotec, Timer, image_commands, BG, CARD
from soft_ui import SoftUI


class Sound:
    def play(self): pass
    def silence(self): pass


def hub():
    value=Robotec.__new__(Robotec)
    value.cache={}; value.artwork=deque(); value.art_key=None; value.images={}
    value.lock=threading.Lock(); value.screen='time'; value.compact=False; value.dirty=True
    value.unlocked=True; value.notice=None; value.pin_entry=''; value.pin_wait=0; value.pin_message='PIN'
    value.time_mode='timer'; value.watch={'elapsed':0,'started':None}; value.timer=Timer()
    value.alarm=Alarm(); value.alert_sound=Sound(); value.repos=[]
    value.network={'weather':'28 °C','condition':'Zapopan','weather_code':0}
    value.music={'title':'Titulo','artist':'Artista','status':'paused','volume':30,'duration':200000}
    value.last_touch=0; value.music_commands=queue.Queue(); value.save=lambda:None
    value.cover_cache=OrderedDict(); value.cover_requested=None; value.image_jobs=queue.Queue()
    value.send=lambda command:None
    return value


class Raster(SoftUI):
    def __init__(self):
        self.im=Image.new('RGB',(220,50),'#112233')
        self.draw=ImageDraw.Draw(self.im); self.cache={}; self.commands=[]

    def fill(self,x,y,w,h,color): self.send(f'fill {x},{y},{w},{h},{color}')

    def send(self,command):
        self.commands.append(command)
        op,data=command.split(' ',1)
        if op=='fill':
            x,y,w,h,c=map(int,data.split(','))
            self.draw.rectangle((x,y,x+w-1,y+h-1),fill=c)
        elif op=='cirs':
            x,y,r,c=map(int,data.split(',')); self.draw.ellipse((x-r,y-r,x+r,y+r),fill=c)


class AlarmTests(unittest.TestCase):
    def setUp(self): self.now=[dt.datetime(2026,10,23,23,59,20).timestamp()]
    def alarm(self): return Alarm(clock=lambda:self.now[0])

    def test_next_day_and_single_fire(self):
        alarm=self.alarm(); alarm.data.update(hour=0,minute=1); alarm.arm()
        self.assertEqual(dt.datetime.fromtimestamp(alarm.data['deadline']).day,24)
        self.now[0]=alarm.data['deadline']; self.assertEqual(alarm.poll(),'ring')
        self.assertIsNone(alarm.poll()); self.assertFalse(alarm.data['enabled'])

    def test_persistence_snooze_and_missed(self):
        alarm=self.alarm(); alarm.snooze(); restored=Alarm(alarm.data.copy(),clock=lambda:self.now[0])
        self.now[0]+=299; self.assertIsNone(restored.poll())
        self.now[0]+=2; self.assertEqual(restored.poll(),'ring')
        restored.snooze(); self.now[0]+=601; self.assertEqual(restored.poll(),'missed')

    def test_adjust_wrap_and_cancel(self):
        alarm=self.alarm(); alarm.data.update(hour=0,minute=0); alarm.adjust(minutes=-1)
        self.assertEqual((alarm.data['hour'],alarm.data['minute']),(23,59))
        alarm.arm(); alarm.cancel(); self.now[0]+=90000; self.assertIsNone(alarm.poll())


class PaintTests(unittest.TestCase):
    def test_progress_updates_match_clean_render_without_wiping_bar(self):
        raster=Raster(); raster.delta_progress('p',10,10,180,0,0xAABBCC,0x112233)
        random.seed(7)
        for value in [1,2,3,4,8,50,179,180,90,0]+[random.randrange(181) for _ in range(30)]:
            raster.commands=[]
            raster.delta_progress('p',10,10,180,value/180,0xAABBCC,0x112233)
            expected=Raster(); expected.delta_progress('p',10,10,180,value/180,0xAABBCC,0x112233)
            self.assertEqual(raster.im.tobytes(),expected.im.tobytes())
            self.assertFalse(any(c.startswith('fill 10,10,180,8,') for c in raster.commands))

    def test_image_rectangles_preserve_pixels_and_coarse_refinement(self):
        random.seed(2); pixels=[random.choice([1,2,3,4]) for _ in range(48*48)]
        coarse=[pixels[(r*4+2)*48+c*4+2] for r in range(12) for c in range(12)]
        underlay=[coarse[r//4*12+c//4] for r in range(48) for c in range(48)]
        raster=Raster()
        for cmd in image_commands(coarse,0,0,48)+image_commands(pixels,0,0,48,underlay):raster.send(cmd)
        self.assertEqual(raster.im.crop((0,0,48,48)).tobytes(),bytes(channel for p in pixels for channel in (p,0,0)))
        self.assertEqual(len(image_commands([5]*2304,0,0,192)),1)

    def test_pause_and_play_keep_font(self):
        value=hub(); value.screen='music'; commands=[]; value.send=commands.append
        value.render(); paused=next(c for c in commands if c.startswith('xstr') and 'Reproducir' in c)
        commands.clear(); value.music['status']='playing'; value.render()
        playing=next(c for c in commands if c.startswith('xstr') and 'Pausar' in c)
        self.assertEqual(paused.split(',')[4],playing.split(',')[4])


class ToolsTests(unittest.TestCase):
    def test_alarm_tab_not_replaced_by_running_timer(self):
        value=hub(); value.timer.toggle(); value.touch(650,100)
        self.assertEqual(value.time_mode,'alarm'); self.assertFalse(value.compact)
        value.last_touch=0; value.touch(100,340)
        self.assertTrue(value.alarm.data['enabled'])

    def test_notice_does_not_unlock(self):
        value=hub(); value.unlocked=False; value.screen='lock'
        value.notify('Alarma','alarm'); value.touch(250,290)
        self.assertFalse(value.unlocked); self.assertIsNone(value.notice); self.assertEqual(value.screen,'lock')

    def test_seek_and_shuffle_are_queued(self):
        value=hub(); value.screen='music'; value.touch(528,260)
        self.assertEqual(value.music_commands.get_nowait(),['seek','100000'])
        value.last_touch=0; value.touch(350,410)
        self.assertEqual(value.music_commands.get_nowait(),['shuffle','on'])

    def test_stopwatch_lap_preserves_running_state(self):
        value=hub(); value.time_mode='watch'; value.watch.update(started=10)
        with patch('time.time',return_value=23): value.lap()
        self.assertEqual(value.watch['laps'],[13]); self.assertEqual(value.watch['started'],10)


class MusicTests(unittest.TestCase):
    def test_pause_freezes_monotonic_position(self):
        clock=[10.0]; state={}
        event={'status':'playing','item':{'decorations':{'playback':{'duration_ms':30000}}},'position':{'position_ms':1000,'timestamp_ms':100000,'speed':1}}
        apply_event(state,event,lambda:clock[0],lambda:100)
        clock[0]=12; self.assertEqual(position_ms(state,lambda:clock[0]),3000)
        apply_event(state,{'type':'playback_changed','status':'paused'},lambda:clock[0],lambda:100)
        clock[0]=30; self.assertEqual(position_ms(state,lambda:clock[0]),3000)

    def test_events_queue_cover_without_stale_jobs(self):
        value=hub()
        for cover in ['a','b','c']:
            value.accept_music({'type':'track_changed','item':{'decorations':{'visual_identity':{'cover':[{'url':cover}]}}}})
        self.assertEqual(value.image_jobs.qsize(),1); self.assertEqual(value.image_jobs.get(),'c')
        value.cover_cache['cached']=[1]*2304
        value.accept_music({'type':'track_changed','item':{'decorations':{'visual_identity':{'cover':[{'url':'cached'}]}}}})
        self.assertEqual(value.images['music'][0],'cached'); self.assertTrue(value.image_jobs.empty())

    def test_cancelled_cover_can_be_requested_again(self):
        value=hub()
        def track(url):
            return {'type':'track_changed','item':{'decorations':{'visual_identity':{'cover':[{'url':url}]}}}}
        value.accept_music(track('pending'))
        value.image_jobs.get_nowait()
        value.cover_cache['cached']=[1]*2304
        value.accept_music(track('cached'))
        value.accept_music(track('pending'))
        self.assertEqual(value.image_jobs.get_nowait(),'pending')


if __name__=='__main__': unittest.main()
