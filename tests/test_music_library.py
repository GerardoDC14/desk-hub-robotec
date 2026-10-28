"""Persistencia de una selección explícita y zonas táctiles de la biblioteca."""
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from music_library import MusicLibrary,LibraryViews


def track(number=0,**extra):
    return dict(uri='spotify:track:'+str(number),title='Canción '+str(number),artist='Artista',**extra)


class LibraryTests(unittest.TestCase):
    def test_only_explicit_track_or_episode_uris_are_saved(self):
        library=MusicLibrary()
        for uri in ['',None,'track-a','https://open.spotify.com/track/abc','spotify:playlist:abc',
                    'spotify:track:','spotify:track:abc\n','spotify:track:a/b','spotify:track:a"',
                    'spotify:episode:'+'a'*65]:
            self.assertFalse(library.add(dict(uri=uri,title='No guardar')),uri)
        self.assertTrue(library.add(track()))
        self.assertTrue(library.add(dict(uri='spotify:episode:abc',title='Episodio')))
        self.assertEqual(len(library.data),2)

    def test_no_secrets_sessions_or_cover_urls_are_retained(self):
        music=track(1,cover='private-cover',token='secret',position={'position_ms':1000},logged_in=True)
        library=MusicLibrary(); library.add(music)
        self.assertEqual(set(library.data[0]),{'uri','title','artist'})
        self.assertNotIn('secret',json.dumps(library.data))
        malformed=track(2); malformed.update(title={'token':'secret'},artist=['session-secret'])
        library.add(malformed)
        self.assertNotIn('secret',json.dumps(library.data))

    def test_dedup_updates_metadata_without_reordering_and_restores_from_json(self):
        library=MusicLibrary([track(1),track(2)])
        changed=track(1); changed['title']='Título corregido'
        self.assertTrue(library.add(changed)); self.assertEqual(library.status,'updated')
        self.assertEqual([item['uri'] for item in library.data],['spotify:track:1','spotify:track:2'])
        restored=MusicLibrary(json.loads(json.dumps(library.data)))
        self.assertEqual(restored.data,library.data); self.assertEqual(restored.data[0]['title'],'Título corregido')

    def test_caps_avoid_unbounded_state_and_existing_items_still_update(self):
        library=MusicLibrary([track(i) for i in range(40)])
        self.assertEqual(len(library.data),24)
        self.assertFalse(library.add(track(90))); self.assertEqual(library.status,'full')
        update=track(2); update['title']='Actualizada'
        self.assertTrue(library.add(update)); self.assertEqual(library.data[2]['title'],'Actualizada')

    def test_metadata_is_bounded_and_cannot_inject_display_commands(self):
        item=track(1); item.update(title='"\\\xff\x00\n'+'a'*300,artist='b'*300)
        library=MusicLibrary([item]); saved=library.data[0]
        self.assertLessEqual(len(saved['title']),120); self.assertLessEqual(len(saved['artist']),100)
        self.assertFalse(any(c in saved['title'] for c in ('"','\\','\xff','\x00','\n')))
        self.assertEqual(MusicLibrary([None,4,{}]).data,[])
        self.assertEqual(MusicLibrary({'token':'secret'}).data,[])

    def test_removal_can_be_undone_and_never_duplicates_a_resaved_item(self):
        library=MusicLibrary([track(1),track(2),track(3)])
        self.assertFalse(library.remove('spotify:track:unknown'))
        self.assertTrue(library.remove('spotify:track:2')); self.assertTrue(library.undo_remove())
        self.assertEqual([item['uri'] for item in library.data],['spotify:track:1','spotify:track:2','spotify:track:3'])
        self.assertFalse(library.undo_remove())
        library.remove('spotify:track:2'); self.assertTrue(library.can_undo)
        library.add(track(2)); self.assertFalse(library.can_undo); self.assertFalse(library.undo_remove())
        self.assertEqual(len(library.data),3)

    def test_undo_is_unavailable_if_new_saved_song_fills_capacity(self):
        library=MusicLibrary([track(i) for i in range(24)])
        library.remove('spotify:track:2'); self.assertTrue(library.can_undo)
        library.add(track(99)); self.assertFalse(library.can_undo)
        self.assertFalse(library.undo_remove()); self.assertEqual(len(library.data),24)


class TouchTests(unittest.TestCase):
    def value(self):
        value=LibraryViews()
        value.library=MusicLibrary([track(i) for i in range(6)])
        value.library_page=0; value.library_message=''; value.unlocked=True
        value.lock=threading.Lock(); value.music=track(9)
        value.save=Mock(); value.navigate=Mock(); value.request_selected_music=Mock(return_value=True)
        return value

    def test_saving_current_song_changes_to_its_page_and_persists(self):
        value=self.value(); value.touch_library(600,100)
        self.assertEqual(value.library_page,1); value.save.assert_called_once()
        self.assertEqual(value.library.data[-1]['uri'],'spotify:track:9')
        value.navigate.assert_not_called()

    def test_card_play_gaps_and_paging_match_layout(self):
        value=self.value()
        value.touch_library(100,195); value.request_selected_music.assert_not_called()
        value.touch_library(650,405); self.assertEqual(value.library_page,1)
        value.touch_library(100,150)
        value.request_selected_music.assert_called_once_with('spotify:track:4')
        value.navigate.assert_called_once_with('music')
        value.touch_library(650,405); self.assertEqual(value.library_page,1)

    def test_failed_play_or_locked_touch_cannot_start_playback(self):
        value=self.value(); value.request_selected_music.return_value=False
        value.touch_library(100,150); value.navigate.assert_not_called()
        self.assertIn('Conecta Spotify',value.library_message)
        value.unlocked=False; value.request_selected_music.reset_mock()
        value.touch_library(100,150); value.touch_library(600,100)
        value.request_selected_music.assert_not_called(); value.save.assert_not_called()

    def test_edit_mode_removes_instead_of_playing_and_undo_restores_position(self):
        value=self.value()
        value.touch_library(550,30); self.assertTrue(value.library_editing)
        value.touch_library(100,215)
        self.assertNotIn('spotify:track:1',[item['uri'] for item in value.library.data])
        self.assertTrue(value.library.can_undo); value.save.assert_called_once()
        value.request_selected_music.assert_not_called(); value.navigate.assert_not_called()
        value.touch_library(400,405)
        self.assertFalse(value.library.can_undo); self.assertEqual(value.save.call_count,2)
        self.assertEqual([item['uri'] for item in value.library.data],['spotify:track:'+str(i) for i in range(6)])
        value.touch_library(550,30); self.assertFalse(value.library_editing)
        value.touch_library(100,215)
        value.request_selected_music.assert_called_once_with('spotify:track:1')

    def test_removing_last_card_on_final_page_clamps_page_and_undo_returns_there(self):
        value=self.value(); value.library=MusicLibrary([track(i) for i in range(5)])
        value.library_page=1; value.library_editing=True
        value.touch_library(100,150)
        self.assertEqual(value.library_page,0); self.assertEqual(len(value.library.data),4)
        value.touch_library(400,405)
        self.assertEqual(value.library_page,1); self.assertEqual(value.library.data[4]['uri'],'spotify:track:4')

    def test_locked_edit_remove_and_undo_do_not_modify_saved_music(self):
        value=self.value(); value.library_editing=True
        value.library.remove('spotify:track:1'); before=list(value.library.data)
        value.unlocked=False
        for point in ((550,30),(100,150),(400,405)):
            value.touch_library(*point)
        self.assertEqual(value.library.data,before); self.assertTrue(value.library.can_undo)
        self.assertTrue(value.library_editing); value.save.assert_not_called()
        value.request_selected_music.assert_not_called()

    def test_empty_state_reappears_after_last_item_is_removed(self):
        from test_dashboard import hub
        value=hub(); value.library=MusicLibrary(); value.library_page=0; value.library_message=''
        commands=[]; value.send=commands.append
        LibraryViews.draw_library(value)
        value.library.add(track(1)); LibraryViews.draw_library(value)
        value.library.remove('spotify:track:1'); commands.clear(); LibraryViews.draw_library(value)
        self.assertTrue(any('Tu selección empieza aquí.' in command for command in commands))

    def test_edit_mode_redraws_delete_icons_and_undo_returns_to_plain_footer(self):
        from test_dashboard import hub
        value=hub(); value.library=MusicLibrary([track(1)]); commands=[]; value.send=commands.append
        LibraryViews.draw_library(value)
        self.assertIn('icon:libraryplay0',value.cache)
        value.library_editing=True; commands.clear(); LibraryViews.draw_library(value)
        self.assertNotIn('icon:libraryplay0',value.cache)
        self.assertIn('icon:libraryremove0',value.cache)
        self.assertTrue(any(command.startswith('line 710,157,726,173,') for command in commands))
        commands.clear(); LibraryViews.draw_library(value)
        self.assertEqual(commands,[],'A stable library must not keep redrawing its cards')
        value.library.remove('spotify:track:1'); LibraryViews.draw_library(value)
        self.assertIn('button:libraryundo',value.cache)
        value.library.undo_remove(); commands.clear(); LibraryViews.draw_library(value)
        self.assertNotIn('button:libraryundo',value.cache)
        self.assertTrue(any(command.startswith('fill 216,390,368,32,') for command in commands))
        value.library_editing=False; LibraryViews.draw_library(value)
        self.assertNotIn('icon:libraryremove0',value.cache); self.assertIn('icon:libraryplay0',value.cache)

    def test_library_content_leaves_bottom_navigation_clear(self):
        from test_dashboard import hub
        value=hub(); value.library=MusicLibrary([track(i) for i in range(6)])
        value.library_editing=True; commands=[]; value.send=commands.append
        LibraryViews.draw_library(value)
        for command in commands:
            op,_,raw=command.partition(' ')
            if op in ('fill','xstr'):
                _,y,_,height=map(int,raw.split(',')[:4])
                self.assertLessEqual(y+height,426,command)
            elif op=='cirs':
                _,y,radius=map(int,raw.split(',')[:3])
                self.assertLess(y+radius,426,command)


if __name__=='__main__': unittest.main()
