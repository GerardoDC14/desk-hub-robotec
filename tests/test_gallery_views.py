"""Regresiones de galería: privacidad, toques y transporte visual de Nextion."""
from collections import deque
from pathlib import Path
import re
import sys
import threading
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from font_metrics import text_width
from photo_library import FILTERS, PREVIEW_SIZE
from test_dashboard import hub


class FakePhotos:
    """Contrato público del backend sin archivos, cámara ni trabajadores."""
    def __init__(self,count=2,ready=True):
        self.calls=[]; self.lock_calls=0; self.generation=1
        self.state=dict(count=count,index=0,filename='foto-a.jpg' if count else '',
                        filter='Original',status='Fotos privadas en la Raspberry' if count else 'No hay fotos guardadas',
                        preview=None,preview_key=None,ready=False,busy=False,saving=False,
                        error='',last_saved='',filters=FILTERS,original_size=(1280,720))
        if count and ready: self.ready()

    def ready(self,color=None):
        color=100+self.generation if color is None else color
        cols,rows=PREVIEW_SIZE
        self.state.update(preview=(cols,rows,tuple([color]*(cols*rows))),
                          preview_key=(self.state['filename'],self.state['filter'],self.generation),
                          ready=True,busy=False,error='',status='Fotos privadas en la Raspberry')

    def snapshot(self,unlocked=False):
        if not unlocked:
            self.lock()
            return dict(self.state,count=0,index=0,filename='',preview=None,preview_key=None,ready=False,status='Galería bloqueada')
        return dict(self.state)

    def _changed(self):
        self.generation+=1
        self.state.update(preview=None,preview_key=None,ready=False,busy=True,error='',status='Preparando vista…')

    def set_filter(self,name,unlocked=False):
        self.calls.append(('filter',name,unlocked))
        if not unlocked or name not in FILTERS: return False
        if name!=self.state['filter']:
            self.state['filter']=name; self._changed()
        return True

    def move(self,step,unlocked=False):
        self.calls.append(('move',step,unlocked))
        if not unlocked or not self.state['count']: return False
        index=max(0,min(self.state['count']-1,self.state['index']+step))
        if index!=self.state['index']:
            self.state.update(index=index,filename='foto-'+('a' if index==0 else 'b')+'.jpg')
            self._changed()
        return True

    def save_copy(self,unlocked=False):
        self.calls.append(('save',unlocked))
        return unlocked and bool(self.state['count']) and self.state['filter']!='Original'

    def lock(self):
        self.lock_calls+=1
        self.state.update(preview=None,preview_key=None,ready=False,busy=False)


def value_with_photos(photos=None):
    value=hub(); value.screen='gallery'
    value.photos=photos if photos is not None else FakePhotos()
    value.commands=[]; value.send=value.commands.append
    return value


def image_geometry(command):
    match=re.fullmatch(r'fill (\d+),(\d+),(\d+),(\d+),(\d+)',command)
    if not match: raise AssertionError('Instrucción de foto no válida: '+command)
    return tuple(map(int,match.groups()))


class GalleryRenderTests(unittest.TestCase):
    def test_missing_backend_and_empty_library_show_actionable_empty_state(self):
        for photos in (None,FakePhotos(count=0)):
            with self.subTest(photos=photos):
                value=value_with_photos(); value.photos=photos
                value.draw_gallery()
                self.assertEqual(value.art_key,('gallery-empty',))
                self.assertEqual(list(value.artwork),[])
                self.assertTrue(any('Tus fotos aparecerán aquí.' in command for command in value.commands))
                self.assertTrue(any('Tomar foto.' in command for command in value.commands))
                if photos is None:
                    self.assertTrue(any('Cámara no disponible' in command for command in value.commands))

    def test_ready_preview_queues_native_image_inside_dedicated_rectangle(self):
        value=value_with_photos(); value.draw_gallery()
        self.assertEqual(value.art_key,('gallery',value.photos.state['preview_key']))
        self.assertTrue(value.artwork)
        self.assertEqual(value.art_total,len(value.artwork))
        for command in value.artwork:
            x,y,w,h,color=image_geometry(command)
            self.assertGreaterEqual(x,32); self.assertGreaterEqual(y,100)
            self.assertLessEqual(x+w,560); self.assertLessEqual(y+h,397)
            self.assertTrue(w>0 and h>0 and 0<=color<=65535)
        self.assertEqual(list(value.artwork),['fill 32,100,528,297,101'])

    def test_detailed_preview_uses_only_native_fills_inside_its_image_bounds(self):
        value=value_with_photos(); cols,rows=PREVIEW_SIZE
        value.photos.state['preview']=(cols,rows,tuple(range(cols*rows)))
        value.draw_gallery()
        self.assertGreater(len(value.artwork),16*9)
        for command in value.artwork:
            x,y,w,h,color=image_geometry(command)
            self.assertGreaterEqual(x,32); self.assertGreaterEqual(y,100)
            self.assertLessEqual(x+w,560); self.assertLessEqual(y+h,397)
            self.assertTrue(w>0 and h>0 and 0<=color<=65535)

    def test_all_seven_filter_buttons_fit_font_and_header_uses_camera_return(self):
        value=value_with_photos(); buttons=[]
        original=value.soft_button
        def button(*args,**kwargs):
            buttons.append((args,kwargs)); return original(*args,**kwargs)
        value.soft_button=button
        value.base(); value.draw_gallery()
        filters=[args for args,kwargs in buttons if args[0].startswith('galleryfilter')]
        self.assertEqual(len(filters),7)
        self.assertEqual([args[5] for args in filters],list(FILTERS))
        for args in filters:
            _,x,y,w,h,label,selected,font=args
            inset=min(14,max(3,h//4))
            self.assertLessEqual(text_width(label,font),w-2*inset,label)
            self.assertGreaterEqual(x,584); self.assertLessEqual(x+w,768)
            self.assertGreaterEqual(y,100); self.assertLessEqual(y+h,397)
        camera=[args for args,kwargs in buttons if args[0]=='galleryback']
        self.assertEqual(len(camera),1); self.assertEqual(camera[0][5],'Cámara')
        self.assertFalse(any(key.startswith('nav') for key in value.cache))

    def test_stable_preview_does_not_requeue_or_redraw_its_base(self):
        value=value_with_photos(); value.draw_gallery()
        original=list(value.artwork); key=value.art_key
        value.artwork.popleft(); remaining=list(value.artwork)
        value.commands.clear(); value.draw_gallery()
        self.assertEqual(value.art_key,key)
        self.assertEqual(list(value.artwork),remaining)
        self.assertEqual(value.commands,[])
        self.assertTrue(original)

    def test_filter_change_clears_old_queue_and_waits_for_matching_preview(self):
        value=value_with_photos(); value.draw_gallery()
        stale='fill 32,100,528,297,65535'; value.artwork.append(stale)
        self.assertTrue(value.touch_gallery(650,202)) # Sepia
        self.assertEqual(value.photos.calls[-1],('filter','Sepia',True))
        self.assertEqual(list(value.artwork),[]); self.assertIsNone(value.art_key)
        value.draw_gallery()
        self.assertEqual(value.art_key,('gallery-pending','foto-a.jpg','Sepia'))
        self.assertEqual(list(value.artwork),[])
        # Un resultado tardío de Original no debe aparecer como si fuera Sepia.
        value.photos.state.update(preview=(16,9,tuple([4]*144)),preview_key=('foto-a.jpg','Original',1))
        value.draw_gallery(); self.assertEqual(list(value.artwork),[])
        value.photos.ready(color=202); value.draw_gallery()
        self.assertEqual(value.art_key,('gallery',('foto-a.jpg','Sepia',2)))
        self.assertEqual(list(value.artwork),['fill 32,100,528,297,202'])
        self.assertNotIn(stale,value.artwork)

    def test_new_photo_generation_replaces_pending_artwork(self):
        value=value_with_photos(); value.draw_gallery()
        self.assertTrue(value.touch_gallery(510,438))
        self.assertEqual(list(value.artwork),[])
        value.photos.ready(color=303); value.draw_gallery()
        self.assertEqual(value.art_key,('gallery',('foto-b.jpg','Original',2)))
        self.assertEqual(list(value.artwork),['fill 32,100,528,297,303'])

    def test_failed_photo_displays_error_instead_of_endless_loading(self):
        photos=FakePhotos(ready=False)
        photos.state.update(error='No se pudo abrir esta foto',status='No se pudo abrir esta foto',busy=False)
        value=value_with_photos(photos)
        value.draw_gallery()
        self.assertTrue(any('No se pudo abrir la foto' in command for command in value.commands))
        self.assertFalse(any('Preparando foto' in command for command in value.commands))
        self.assertEqual(list(value.artwork),[])
        value.commands.clear(); value.draw_gallery()
        self.assertEqual(value.commands,[])
        self.assertEqual(value.art_key,('gallery-pending','foto-a.jpg','Original'))


class GalleryIntegrationTests(unittest.TestCase):
    def touch(self,value,x,y):
        value.last_touch=0; value.touch(x,y)

    def test_header_camera_action_uses_camera_route(self):
        value=value_with_photos(); value.draw_gallery()
        self.touch(value,700,30)
        self.assertEqual(value.screen,'camera')
        self.assertEqual(list(value.artwork),[]); self.assertIsNone(value.art_key)

    def test_bottom_gallery_controls_are_not_intercepted_by_navigation(self):
        value=value_with_photos(); value.photos.state['filter']='Sepia'; value.photos.ready()
        self.touch(value,80,438)
        self.assertEqual(value.photos.calls[-1],('move',-1,True)); self.assertEqual(value.screen,'gallery')
        self.touch(value,510,438)
        self.assertEqual(value.photos.calls[-1],('move',1,True)); self.assertEqual(value.screen,'gallery')
        self.touch(value,675,438)
        self.assertEqual(value.photos.calls[-1],('save',True)); self.assertEqual(value.screen,'gallery')

    def test_pressing_selected_filter_preserves_inflight_image_without_sending_draw_commands(self):
        value=value_with_photos(); cols,rows=PREVIEW_SIZE
        value.photos.state['preview']=(cols,rows,tuple(range(cols*rows)))
        value.draw_gallery()
        for _ in range(5): value.artwork.popleft()
        key=value.art_key; queued=list(value.artwork)
        queued_bytes=b''.join(command.encode('latin-1')+b'\xff\xff\xff' for command in queued)
        value.commands.clear()
        self.touch(value,675,118) # Original ya está seleccionado.
        value.draw_gallery()
        self.assertEqual(value.photos.calls[-1],('filter','Original',True))
        self.assertEqual(value.art_key,key); self.assertEqual(list(value.artwork),queued)
        self.assertEqual(b''.join(command.encode('latin-1')+b'\xff\xff\xff' for command in value.artwork),queued_bytes)
        self.assertEqual(len(value.commands),0)

    def test_previous_at_first_photo_preserves_inflight_image_without_sending_draw_commands(self):
        value=value_with_photos(); cols,rows=PREVIEW_SIZE
        value.photos.state['preview']=(cols,rows,tuple(range(cols*rows)))
        value.draw_gallery()
        for _ in range(5): value.artwork.popleft()
        key=value.art_key; queued=list(value.artwork)
        queued_bytes=b''.join(command.encode('latin-1')+b'\xff\xff\xff' for command in queued)
        value.commands.clear()
        self.touch(value,80,438)
        value.draw_gallery()
        self.assertEqual(value.photos.calls[-1],('move',-1,True))
        self.assertEqual(value.photos.state['index'],0); self.assertEqual(value.screen,'gallery')
        self.assertEqual(value.art_key,key); self.assertEqual(list(value.artwork),queued)
        self.assertEqual(b''.join(command.encode('latin-1')+b'\xff\xff\xff' for command in value.artwork),queued_bytes)
        self.assertEqual(len(value.commands),0)

    def test_filter_hit_gaps_and_preview_taps_do_not_change_selection(self):
        value=value_with_photos()
        for x,y in ((650,138),(650,139),(575,110),(770,110),(250,230),(500,400),(700,400)):
            self.assertFalse(value.touch_gallery(x,y),(x,y))
        self.assertEqual(value.photos.calls,[])
        for index,label in enumerate(FILTERS):
            self.assertTrue(value.touch_gallery(675,118+42*index))
            self.assertEqual(value.photos.calls[-1],('filter',label,True))

    def test_navigation_away_discards_partially_sent_image_queue(self):
        value=value_with_photos(); value.draw_gallery()
        value.artwork.extend(['fill 33,100,1,1,500','fill 34,100,1,1,501'])
        value.navigate('home')
        self.assertEqual(value.screen,'home'); self.assertTrue(value.dirty)
        self.assertEqual(list(value.artwork),[]); self.assertIsNone(value.art_key)

    def test_pin_lock_calls_backend_lock_and_blocks_all_photo_actions(self):
        value=value_with_photos(); value.draw_gallery()
        value.camera=Mock(); value.marker=Mock(); value.spotify_wake=threading.Event()
        value.reset_music_session=Mock()
        value.music_commands.put(['play'])
        value.lock_hub()
        self.assertFalse(value.unlocked); self.assertEqual(value.screen,'lock')
        self.assertEqual(value.photos.lock_calls,1); value.camera.lock.assert_called_once_with()
        self.assertEqual(list(value.artwork),[]); self.assertIsNone(value.art_key)
        value.photos.calls.clear()
        for x,y in ((675,118),(675,202),(80,438),(510,438),(675,438),(700,30)):
            self.assertFalse(value.touch_gallery(x,y))
        self.assertEqual(value.photos.calls,[])
        value.navigate('gallery'); self.assertEqual(value.screen,'lock')

    def test_locked_gallery_render_never_queues_private_preview(self):
        value=value_with_photos(); value.unlocked=False
        value.artwork=deque(['fill 32,100,528,297,123'])
        value.draw_gallery()
        self.assertEqual(value.photos.lock_calls,1)
        self.assertEqual(list(value.artwork),[])
        self.assertFalse(any(command.endswith(',101') for command in value.commands))


if __name__=='__main__': unittest.main()
