"""Uso compartido: límites, ayuda pública, navegación y pronóstico."""
import datetime as dt
import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import Mock, patch
from test_dashboard import hub
from robotec import Robotec
from friendly_ui import GUIDE
from weather_data import next_hours


class FriendlyTests(unittest.TestCase):
    def test_public_guide_never_unlocks_or_resets_pin_cooldown(self):
        value=hub(); value.screen='lock'; value.unlocked=False; value.pin_wait=time.monotonic()+30
        value.pin_entry='12'; value.spotify_desired=False; deadline=value.pin_wait
        value.touch(690,32); self.assertEqual(value.screen,'help'); self.assertFalse(value.unlocked)
        self.assertEqual(value.pin_entry,''); self.assertEqual(value.pin_wait,deadline)
        for x in (50,210,360,520,700):
            value.last_touch=0; value.touch(x,145)
            self.assertEqual(value.screen,'help'); self.assertFalse(value.unlocked)
        value.last_touch=0; value.touch(650,440); self.assertEqual(value.screen,'help')
        value.last_touch=0; value.touch(120,440); self.assertEqual(value.screen,'lock')
        self.assertFalse(value.spotify_desired); self.assertEqual(value.pin_wait,deadline)
        self.assertTrue(all(len(body)<=160 for _,body in GUIDE))

    def test_running_timer_can_return_home_and_reopen_without_pause(self):
        value=hub(); value.timer.toggle(); deadline=value.timer.data['deadline']; value.navigate('time')
        self.assertTrue(value.compact); value.touch(100,32); self.assertEqual(value.screen,'home')
        self.assertEqual(value.timer.data['deadline'],deadline)
        value.last_touch=0; value.touch(300,400)
        self.assertEqual(value.screen,'time'); self.assertTrue(value.compact)
        self.assertEqual(value.timer.data['deadline'],deadline)

    def test_running_watch_can_return_home_and_reopen_without_pause(self):
        value=hub(); value.time_mode='watch'; value.watch['started']=time.time()-25; value.navigate('time')
        stamp=value.watch['started']; value.touch(100,32); self.assertEqual(value.screen,'home')
        value.last_touch=0; value.touch(300,400)
        self.assertEqual(value.time_mode,'watch'); self.assertTrue(value.compact); self.assertEqual(value.watch['started'],stamp)

    def test_reconnect_confirmation_only_interrupts_when_confirmed(self):
        value=hub(); value.screen='status'; value.music['status']='playing'; value.spotify_wake=threading.Event()
        value.touch(180,375); self.assertEqual(value.screen,'confirm_reconnect'); self.assertFalse(value.spotify_restart)
        value.last_touch=0; value.touch(180,360); self.assertEqual(value.screen,'status'); self.assertFalse(value.spotify_restart)
        value.last_touch=0; value.touch(180,375); value.last_touch=0; value.touch(550,360)
        self.assertEqual(value.screen,'status'); self.assertTrue(value.spotify_restart)
        self.assertFalse(value.music['is_active'])

    def test_silence_keeps_notice_and_countdown_without_unlocking(self):
        value=hub(); value.screen='lock'; value.unlocked=False; value.alert_sound=Mock()
        value.timer.toggle(); deadline=value.timer.data['deadline']; value.notify('Es la hora','alarm')
        value.touch(400,365)
        self.assertIsNotNone(value.notice); self.assertTrue(value.notice['muted']); self.assertFalse(value.unlocked)
        self.assertEqual(value.timer.data['deadline'],deadline); value.alert_sound.silence.assert_called_once()
        value.last_touch=0; value.touch(200,290); self.assertIsNone(value.notice); self.assertFalse(value.unlocked)

    def test_inactive_music_offers_help_without_claiming_playback(self):
        value=hub(); value.screen='music'; value.music.update(is_active=False,_ready=False,logged_in=False)
        commands=[]; value.send=commands.append; value.render()
        self.assertTrue(any('¿Cómo conectar?' in c for c in commands))
        value.touch(160,395); self.assertEqual(value.screen,'help'); self.assertTrue(value.music_commands.empty())


class ForecastTests(unittest.TestCase):
    def test_hours_cross_midnight_and_preserve_units(self):
        start=dt.datetime(2026,10,28,4,0,tzinfo=dt.timezone.utc).timestamp()
        stamps=[start+i*3600 for i in range(5)]
        rows=next_hours(dict(time=stamps,temperature_2m=[20,19,18,17,16],precipitation_probability=[0,20,50,None,80]),start)
        self.assertEqual([r['label'] for r in rows],['23:00','00:00','01:00'])
        self.assertEqual(rows[0]['value'],'19° · 20%'); self.assertEqual(rows[2]['value'],'17° · --%')

    def test_expired_or_missing_forecast_does_not_replace_current_conditions(self):
        value=hub(); value.screen='home'; value.forecast_visible=True
        value.network.update(feels='25 °C',humidity='41 %',wind='2 km/h',forecast=[dict(at=time.time()-60,label='00:00',value='10° · 10%')])
        rows,forecast=value.home_weather_rows(value.network)
        self.assertFalse(forecast); self.assertEqual(rows[0],('Sensación','25 °C'))
        value.network['forecast'][0]['at']=time.time()+3600; value.network['weather_stale']=True
        self.assertFalse(value.home_weather_rows(value.network)[1])
        self.assertEqual(next_hours({},time.time()),[])

    def test_home_toggles_forecast_in_place_and_keeps_current_temperature(self):
        value=hub(); value.screen='home'
        value.network.update(forecast=[dict(at=time.time()+3600,label='20:00',value='22° · 50%')],weather_stale=False)
        value.touch(650,220); self.assertEqual(value.screen,'home'); self.assertTrue(value.forecast_visible)
        commands=[]; value.send=commands.append; value.render()
        self.assertTrue(any('22° · 50%' in c for c in commands)); self.assertTrue(any('28°' in c for c in commands))
        value.last_touch=0; value.touch(650,220); self.assertFalse(value.forecast_visible)


if __name__=='__main__': unittest.main()
