"""Navegación directa y controles del reproductor en su composición actual."""
import unittest
from unittest.mock import Mock
from test_dashboard import hub
from music_state import apply_event

class PlayerLayoutTests(unittest.TestCase):
    def tap(self,h,x,y):h.last_touch=0;h.touch(x,y)

    def test_album_is_track_parent_not_playlist_and_clears_on_next_track(self):
        state={}
        apply_event(state,dict(type='track_changed',item=dict(uri='a',decorations=dict(
            parent=dict(entity=dict(entity_type='album',decorations=dict(identity=dict(name='Álbum real')))))),
            context=dict(decorations=dict(identity=dict(name='Mi playlist')))))
        self.assertEqual(state['album'],'Álbum real')
        apply_event(state,dict(type='track_changed',item=dict(uri='b',decorations={})))
        self.assertEqual(state['album'],'')

    def test_listen_here_transfers_without_clearing_art_or_metadata(self):
        h=hub();h.screen='music';h.music.update(is_active=False,_ready=False,status='playing',album='Mi álbum')
        h.images['music']=('cover',[1]*256);h.art_key=('music','cover')
        commands=[];h.send=commands.append;h.render()
        self.assertTrue(any('"Escuchar aquí"' in c for c in commands))
        self.assertTrue(any('"Mi álbum"' in c for c in commands))
        self.tap(h,592,280)
        self.assertEqual(h.music_commands.get_nowait()['command'],['activate'])
        self.assertEqual(h.music['album'],'Mi álbum');self.assertIn('music',h.images)
        self.assertIsNotNone(h.music_pending)

    def test_listen_here_resumes_paused_local_track_without_seeking(self):
        h=hub();h.screen='music';h.music['status']='paused'
        self.tap(h,592,280)
        self.assertEqual(h.music_commands.get_nowait()['command'],['play'])

    def test_six_destinations_available_from_main_screens(self):
        for source in ('home','music','time','away','status'):
            for x,target in ((65,'home'),(200,'music'),(333,'time'),(466,'away'),(600,'notion'),(733,'viewfinder')):
                h=hub();h.navigate(source);h.camera=Mock();h._notion_selected={'title':'Anterior'}
                self.tap(h,x,450);self.assertEqual(h.screen,target,(source,target))
                h.camera.start_preview.assert_not_called();h.camera.capture.assert_not_called()
                if target=='notion':self.assertIsNone(h._notion_selected)

    def test_locked_navigation_cannot_open_tasks_or_camera(self):
        for x in (600,733):
            h=hub();h.unlocked=False;h.navigate('lock');self.tap(h,x,450)
            self.assertEqual(h.screen,'lock');self.assertFalse(h.unlocked)

    def test_footer_labels_fit_actual_firmware_font(self):
        h=hub();h.screen='home';commands=[];h.send=commands.append;h.render()
        labels=[]
        for cmd in commands:
            if not cmd.startswith('xstr '):continue
            p=cmd[5:].split(',',10);x,y,w,height,font=map(int,p[:5]);label=p[10].strip('"')
            if y==433:
                labels.append(label);self.assertLessEqual(h.text_width(label,font),w,label)
                self.assertLessEqual(x+w,800);self.assertLessEqual(y+height,480)
        self.assertEqual(labels,['Inicio','Spotify','Tiempo','Fuera','Tareas','Cámara'])

    def test_transport_and_full_volume_range(self):
        h=hub();h.screen='music'
        for x,y,expected in ((472,342,['prev']),(592,342,['play']),(712,342,['next']),
                             (456,396,['volume','0']),(687,396,['volume','100'])):
            self.tap(h,x,y);self.assertEqual(h.music_commands.get_nowait()['command'],expected)

    def test_help_area_becomes_seek_only_after_local_playback_ready(self):
        h=hub();h.screen='music';h.music.update(is_active=False,_ready=False,logged_in=False)
        self.tap(h,592,280);self.assertEqual(h.screen,'help');self.assertTrue(h.music_commands.empty())
        h.navigate('music');h.music.update(is_active=True,_ready=True,logged_in=True,status="playing")
        self.tap(h,592,280);self.assertEqual(h.music_commands.get_nowait()['command'],['seek','100000'])

    def test_short_title_clears_both_old_title_lines(self):
        h=hub();h.screen='music';h.music['title']='Una canción con un título suficientemente largo para ocupar dos líneas'
        h.render();commands=[];h.send=commands.append;h.music['title']='Luz';h.render()
        self.assertTrue(any(c.startswith('fill 416,96,352,80,') for c in commands))
        self.assertTrue(any('"Luz"' in c and ',1,' in c for c in commands))
        self.assertFalse(any(c.startswith('cls ') for c in commands))

    def test_tasks_return_directly_home(self):
        h=hub();h.navigate('notion');h.notion=None;self.tap(h,690,32)
        self.assertEqual(h.screen,'home')
