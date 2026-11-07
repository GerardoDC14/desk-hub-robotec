import json
import sqlite3
import threading
import time
import unittest
from unittest.mock import Mock,patch
from timer_bank import TimerBank,NAMES
from robotec import Robotec
from test_dashboard import hub


class TimerBankTests(unittest.TestCase):
    def test_legacy_away_and_timer_migrate_without_losing_deadline(self):
        old=dict(mode='away',duration=1800,remaining=1800,deadline=2000)
        bank=TimerBank(legacy=old,clock=lambda:1000)
        self.assertEqual(bank.away.remaining(),1000)
        self.assertIsNone(bank.timers[0].data['deadline'])
        old['mode']='focus'; bank=TimerBank(legacy=old,clock=lambda:1000)
        self.assertEqual(bank.timers[0].remaining(),1000)
        self.assertIsNone(bank.away.data['deadline'])

    def test_simultaneous_accounts_remain_independent_and_fire_once(self):
        now=[1000]; bank=TimerBank(clock=lambda:now[0])
        for timer in bank.timers: timer.toggle()
        bank.away.toggle(); bank.timers[1].toggle(); bank.selected=2
        stored=json.loads(json.dumps(bank.export()))
        restored=TimerBank(stored,clock=lambda:now[0])
        self.assertEqual(restored.selected,2)
        self.assertIsNone(restored.timers[1].data['deadline'])
        now[0]+=3601
        self.assertEqual(restored.due(),['Experimento','Impresión'])
        self.assertEqual(restored.due(),[])
        self.assertEqual(restored.timers[1].remaining(),300)
        self.assertIsNotNone(restored.away.data['deadline'])

    def test_away_unlock_keeps_regular_timers_and_pending_alerts(self):
        h=hub(); h.marker=Mock(); h.spotify_wake=threading.Event()
        h.pin_record={'configured':True};h.pin_entry='test';h.pin_failures=0
        h.timers.timers[0].toggle(); h.timers.timers[2].toggle()
        deadlines=[t.data['deadline'] for t in h.timers.timers]
        h.navigate('away');h.last_touch=0;h.touch(400,370)
        self.assertFalse(h.unlocked); self.assertIsNotNone(h.away_timer.data['deadline'])
        with patch('robotec.verify_pin',return_value=True):h.unlock_hub()
        self.assertIsNone(h.away_timer.data['deadline'])
        self.assertEqual([t.data['deadline'] for t in h.timers.timers],deadlines)

    def test_all_expired_timers_are_announced_without_overwriting_alarm(self):
        h=hub();h.notify('Alarma principal','alarm')
        for timer in h.timers.timers:timer.data['deadline']=time.time()-1
        h.poll_tools()
        self.assertEqual(h.notice['title'],'Alarma principal')
        for name in NAMES:
            h.touch_notice(200,290);h.poll_tools()
            self.assertEqual(h.notice['title'],name+' / listo')
        h.touch_notice(200,290);h.poll_tools();self.assertIsNone(h.notice)

    def test_picker_navigation_and_running_accounts_survive_sqlite_restore(self):
        h=hub();h.db=sqlite3.connect(':memory:'); self.addCleanup(h.db.close)
        h.db.execute('CREATE TABLE state (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
        h.save=lambda:Robotec.save(h)
        h.timer.toggle();first=h.timer.data['deadline']
        h.navigate('time');h.last_touch=0;h.touch(550,30)
        self.assertEqual(h.screen,'timers')
        h.last_touch=0;h.touch(650,342)
        self.assertEqual(h.timers.selected,2);self.assertEqual(h.screen,'time')
        h.timer.toggle();h.save()
        data=json.loads(h.db.execute("SELECT value FROM state WHERE key='timers'").fetchone()[0])
        bank=TimerBank(data)
        self.assertEqual(bank.timers[0].data['deadline'],first)
        self.assertIsNotNone(bank.timers[2].data['deadline'])
        h.navigate('timers');h.last_touch=0;h.touch(100,460)
        self.assertEqual(h.screen,'home')


if __name__=='__main__':unittest.main()
