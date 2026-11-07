"""Regresiones de navegación, pintura y retirada de servicios opcionales."""
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from test_dashboard import hub

class EssentialTests(unittest.TestCase):
    def test_unchanged_player_does_not_redraw_decorative_animation(self):
        h=hub();h.screen='music';h.music.update(status='playing',position={'position_ms':1000,'speed':0})
        commands=[];h.send=commands.append;h.render()
        start=time.monotonic()
        for step in range(8):
            commands.clear()
            with patch('time.monotonic',return_value=start+step*.25):h.render()
            self.assertEqual(commands,[])

    def test_new_cover_does_not_invalidate_player_controls(self):
        h=hub();h.screen='music';h.render();theme=dict(h.theme)
        h.images['music']=('new-cover',[65535]*256)
        commands=[];h.send=commands.append;h.render()
        self.assertEqual(h.theme,theme)
        self.assertFalse(any(c.startswith('cls ') for c in commands))
        self.assertFalse(any('Volumen' in c for c in commands))

    def test_retired_routes_fall_back_without_bypassing_lock(self):
        h=hub()
        for unlocked,target in ((True,'home'),(False,'lock')):
            h.unlocked=unlocked
            for route in ('phone','sharing','booth','activity'):
                h.navigate(route);self.assertEqual(h.screen,target)

    def test_retired_modules_not_shipped(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('phone_server','phone_html','phone_views','guest_access','photobooth'):
            self.assertFalse((root/(name+'.py')).exists())

    def test_entire_display_settings_button_is_tappable(self):
        h=hub();h.screen='status';h.open_display=Mock()
        for point in ((35,292),(760,330),(400,312)):
            h.touch_experience(*point)
        self.assertEqual(h.open_display.call_count,3)

    def test_icon_cache_tracks_palette_changes(self):
        h=hub();commands=[];h.send=commands.append
        h.icon_button('sample',40,40,20,'plus');commands.clear()
        h.icon_button('sample',40,40,20,'plus');self.assertEqual(commands,[])
        h.theme=dict(h.theme,ink=65535);h.icon_button('sample',40,40,20,'plus')
        self.assertTrue(commands)
