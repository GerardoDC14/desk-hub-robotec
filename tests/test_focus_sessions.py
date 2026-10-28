"""Sesiones independientes de enfoque: restauración y avance explícito."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from focus_sessions import FocusSession, FocusViews


class FocusSessionTests(unittest.TestCase):
    def setUp(self): self.now = [1_800_000_000.0]
    def session(self, data=None): return FocusSession(data,clock=lambda:self.now[0])
    def finish(self, value):
        self.now[0] = value.data['deadline']
        return value.poll()

    def test_round_trip_requires_acknowledgement_for_each_phase(self):
        value = self.session(); value.configure(focus_minutes=5,break_minutes=1,rounds=2)
        self.assertTrue(value.start())
        event = self.finish(value)
        self.assertEqual(event,dict(title='Enfoque terminado',kind='focus',missed=False))
        self.assertEqual(value.data['state'],'waiting'); self.assertEqual(value.data['completed_rounds'],1)
        self.now[0] += 3600; self.assertIsNone(value.poll()); self.assertIsNone(value.data['deadline'])
        self.assertFalse(value.start()); self.assertTrue(value.acknowledge())
        self.assertEqual(value.data['phase'],'break'); self.assertEqual(value.remaining(),60)
        self.assertEqual(self.finish(value)['title'],'Descanso terminado')
        value.acknowledge()
        self.assertEqual(value.data['phase'],'focus'); self.assertEqual(value.data['current_round'],2)
        self.assertEqual(value.remaining(),300)
        self.assertEqual(self.finish(value)['title'],'Sesión completada')
        value.acknowledge()
        self.assertEqual(value.data['state'],'done'); self.assertIsNone(value.data['deadline'])
        self.assertEqual(value.data['completed_rounds'],2)
        self.assertFalse(value.acknowledge()); self.assertTrue(value.start())
        self.assertEqual(value.data['current_round'],1); self.assertEqual(value.data['completed_rounds'],0)

    def test_pause_preserves_fractional_remaining_without_clock_drift(self):
        value = self.session(); value.start(); self.now[0] += 12.25
        self.assertTrue(value.pause()); self.assertEqual(value.data['remaining'],1487.75)
        self.now[0] += 90; self.assertEqual(value.remaining(),1488)
        self.assertTrue(value.start()); self.assertAlmostEqual(value.data['deadline'],self.now[0]+1487.75)
        self.assertFalse(value.start())

    def test_pause_at_expiry_does_not_hide_notification(self):
        value = self.session(); value.start(); self.now[0] = value.data['deadline']
        self.assertFalse(value.pause()); self.assertEqual(value.data['state'],'running')
        self.assertIsNotNone(value.poll()); self.assertIsNone(value.poll())

    def test_restore_running_session_keeps_absolute_deadline(self):
        value = self.session(); value.start(); stamp = value.data['deadline']
        encoded = json.dumps(value.data); self.now[0] += 180
        restored = self.session(json.loads(encoded))
        self.assertEqual(restored.data['deadline'],stamp); self.assertEqual(restored.remaining(),1320)
        self.now[0] = stamp; self.assertIsNotNone(restored.poll()); self.assertIsNone(restored.poll())

    def test_late_restore_never_runs_multiple_phases_automatically(self):
        value = self.session(); value.start(); encoded = json.dumps(value.data)
        self.now[0] += 86400; restored = self.session(json.loads(encoded))
        event = restored.poll(); self.assertTrue(event['missed'])
        self.assertEqual(restored.data['state'],'waiting'); self.assertEqual(restored.data['current_round'],1)
        self.assertEqual(restored.data['phase'],'focus'); self.assertEqual(restored.data['completed_rounds'],1)
        self.assertIsNone(restored.data['deadline']); self.assertIsNone(restored.poll())

    def test_single_round_has_no_trailing_break(self):
        value = self.session(); value.configure(rounds=1); value.start(); self.finish(value)
        self.assertTrue(value.acknowledge()); self.assertEqual(value.data['state'],'done')
        self.assertEqual(value.data['phase'],'focus')

    def test_waiting_and_paused_persist_without_running(self):
        value = self.session(); value.start(); self.now[0] += 5; value.pause()
        restored = self.session(json.loads(json.dumps(value.data)))
        self.now[0] += 1000; self.assertEqual(restored.remaining(),1495)
        restored.start(); self.finish(restored)
        waiting = self.session(json.loads(json.dumps(restored.data)))
        self.now[0] += 99999; self.assertIsNone(waiting.poll()); self.assertIsNone(waiting.data['deadline'])

    def test_config_limits_and_running_configuration_is_ignored(self):
        value = self.session(); value.configure(focus_minutes=-5,break_minutes=500,rounds=99)
        self.assertEqual((value.data['focus_minutes'],value.data['break_minutes'],value.data['rounds']),(5,30,8))
        value.start(); original=value.data.copy()
        self.assertFalse(value.configure(focus_minutes=90)); self.assertEqual(value.data,original)
        value.pause(); self.assertFalse(value.configure(rounds=1))
        value.reset(); self.assertTrue(value.configure(focus_minutes=100,break_minutes=0,rounds=0))
        self.assertEqual((value.data['focus_minutes'],value.data['break_minutes'],value.data['rounds']),(90,1,1))

    def test_reset_preserves_configuration_and_clears_progress(self):
        value = self.session(); value.configure(focus_minutes=45,break_minutes=8,rounds=3)
        value.start(); self.finish(value); value.acknowledge(); value.reset()
        self.assertEqual(value.data['state'],'idle'); self.assertEqual(value.remaining(),2700)
        self.assertEqual((value.data['focus_minutes'],value.data['break_minutes'],value.data['rounds']),(45,8,3))
        self.assertEqual(value.data['current_round'],1); self.assertEqual(value.data['completed_rounds'],0)
        self.assertIsNone(value.data['deadline'])

    def test_damaged_saved_state_cannot_create_unbounded_deadline_or_duration(self):
        value = self.session(dict(focus_minutes='bad',break_minutes=float('inf'),rounds=-1,
                                  current_round=500,state='running',phase='focus',deadline=float('nan'),remaining=-9))
        self.assertEqual(value.data['focus_minutes'],25); self.assertEqual(value.data['rounds'],1)
        self.assertEqual(value.data['state'],'paused'); self.assertIsNone(value.data['deadline'])
        self.assertEqual(value.remaining(),0)
        malformed = self.session(dict(rounds=2,current_round=2,phase='break',state='running',deadline=self.now[0]+99))
        self.assertEqual(malformed.data['state'],'waiting'); self.assertEqual(malformed.data['phase'],'focus')
        self.assertIsNone(malformed.data['deadline'])
        future=self.session(dict(state='running',deadline=1e200))
        self.assertEqual(future.data['state'],'paused'); self.assertIsNone(future.data['deadline'])


class FocusViewTests(unittest.TestCase):
    class View(FocusViews):
        def __init__(self):
            self.focus = FocusSession(); self.unlocked = True; self.saved=0; self.views=[]; self.commands=[]
            self.theme={key:i for i,key in enumerate(('bg','ink','mint','muted'))}
        def save(self): self.saved+=1
        def navigate(self,view): self.views.append(view)
        def text(self,*args): self.commands.append(('text',args))
        def digital(self,*args): self.commands.append(('digital',args))
        def soft_button(self,*args): self.commands.append(('button',args))
        def text_action(self,*args): self.commands.append(('action',args))
        def icon_button(self,*args): self.commands.append(('icon',args))
        def progress(self,*args): self.commands.append(('progress',args))

    def test_locked_touches_do_not_start_or_advance_session(self):
        value=self.View(); value.unlocked=False
        self.assertFalse(value.touch_focus(400,365)); self.assertEqual(value.focus.data['state'],'idle')
        self.assertEqual(value.saved,0); self.assertEqual(value.views,[])

    def test_setup_hit_areas_and_phase_controls_match_model(self):
        value=self.View(); self.assertFalse(value.touch_focus(600,120))
        self.assertTrue(value.touch_focus(686,158)); self.assertEqual(value.focus.data['focus_minutes'],26)
        self.assertTrue(value.touch_focus(400,365)); self.assertEqual(value.focus.data['state'],'running')
        self.assertTrue(value.touch_focus(250,365)); self.assertEqual(value.focus.data['state'],'paused')
        self.assertTrue(value.touch_focus(250,365)); self.assertEqual(value.focus.data['state'],'running')
        self.assertTrue(value.touch_focus(500,365)); self.assertEqual(value.focus.data['state'],'idle')
        self.assertEqual(value.views,['focus']*5)

    def test_all_model_states_render_within_content_bounds(self):
        value=self.View()
        for state in ('idle','running','paused','waiting','done'):
            value.focus.data['state']=state
            value.focus.data['deadline']=value.focus.clock()+60 if state=='running' else None
            value.commands=[]; value.draw_focus()
            self.assertTrue(value.commands,state)
            for kind,args in value.commands:
                if kind in ('text','digital','button','action'):
                    _,x,y,w,h,*rest=args
                    self.assertGreaterEqual(x,0); self.assertGreaterEqual(y,76)
                    self.assertLessEqual(x+w,800); self.assertLessEqual(y+h,424)


if __name__=='__main__': unittest.main()
