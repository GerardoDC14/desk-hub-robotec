"""Papelera: revisión confirmada, conservación, privacidad y controles."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from photo_library import PhotoLibrary
from camera_tools import CameraController
from test_photo_library import FakeCamera
from test_gallery_views import value_with_photos


class TrashTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.camera=FakeCamera(tmp.name)
        self.path=self.camera.directory/'foto-prueba.jpg'
        Image.new('RGB',(80,40),'teal').save(self.path)
        self.original=self.path.read_bytes()
        self.photos=PhotoLibrary(self.camera); self.addCleanup(self.photos.close)
        self.item=self.photos.selected_revision(unlocked=True)

    def move(self):
        return self.photos.manage_photo('trash',**self.item,unlocked=True)

    def test_move_restart_restore_preserves_original_and_storage(self):
        self.assertTrue(self.move()); self.assertFalse(self.path.exists())
        self.assertEqual(self.photos.snapshot(unlocked=True)['count'],0)
        self.assertEqual(CameraController._usage(self.camera),(0,len(self.original)))
        self.photos.close(); self.photos=PhotoLibrary(self.camera); self.addCleanup(self.photos.close)
        item=self.photos.trash_items(unlocked=True)[0]
        self.assertTrue(self.photos.manage_photo('restore',item['token'],item['signature'],unlocked=True))
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertEqual(self.photos.snapshot(unlocked=True)['count'],1)
        self.assertEqual(self.photos.trash_items(unlocked=True),[])

    def test_purge_removes_only_confirmed_item(self):
        self.move(); item=self.photos.trash_items(unlocked=True)[0]
        other=self.camera.directory/'foto-otra.jpg'; other.write_bytes(self.original)
        self.assertFalse(self.photos.manage_photo('purge','../foto-otra.jpg',item['signature'],unlocked=True))
        self.assertTrue(self.photos.manage_photo('purge',item['token'],item['signature'],unlocked=True))
        self.assertEqual(other.read_bytes(),self.original)
        self.assertEqual(self.photos.trash_items(unlocked=True),[])

    def test_lock_stale_revision_busy_and_restore_collision_preserve_files(self):
        self.assertFalse(self.photos.manage_photo('trash',**self.item,unlocked=False))
        self.assertEqual(self.photos.trash_items(unlocked=False),[])
        self.camera._sequence={'running':True}; self.assertFalse(self.move()); self.camera._sequence=None
        self.path.write_bytes(self.original+b'x'); self.assertFalse(self.move())
        self.item=self.photos.selected_revision(unlocked=True); self.assertTrue(self.move())
        item=self.photos.trash_items(unlocked=True)[0]
        self.path.write_bytes(b'otra foto')
        self.assertFalse(self.photos.manage_photo('restore',item['token'],item['signature'],unlocked=True))
        self.assertEqual(self.path.read_bytes(),b'otra foto')
        self.assertTrue((self.camera.directory/item['token']).exists())

    def test_cancel_then_confirm_and_restore_through_ui(self):
        ui=value_with_photos(self.photos)
        ui.draw_gallery(); ui.touch_gallery(470,75)
        self.assertEqual(ui._photo_action[0],'trash'); self.assertTrue(self.path.exists())
        self.assertFalse(ui.artwork)
        ui.draw_gallery(); ui.touch_gallery(140,425)
        self.assertTrue(self.path.exists()); self.assertIsNone(ui._photo_action)
        ui.touch_gallery(470,75); ui.touch_gallery(620,425)
        self.assertFalse(self.path.exists()); self.assertEqual(ui._photo_action[0],'trash_list')
        ui.draw_gallery_grid(); ui.touch_media(360,425)
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertIsNone(ui._photo_action)

    def test_lock_discards_confirmation_and_cannot_delete(self):
        ui=value_with_photos(self.photos); ui.touch_gallery(470,75)
        ui.unlocked=False; ui.navigate('lock')
        self.assertIsNone(ui._photo_action)
        self.assertFalse(ui.touch_gallery(620,425)); self.assertTrue(self.path.exists())


if __name__=='__main__': unittest.main()
