import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from photo_catalog import PhotoCatalog
from photo_library import PhotoLibrary
from test_photo_library import FakeCamera
from test_dashboard import hub


class CatalogTests(unittest.TestCase):
    def library(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        c=FakeCamera(temp.name);p=PhotoLibrary(c);self.addCleanup(p.close)
        for i in range(3):
            path=c.directory/f'foto-prueba-{i}.jpg';Image.new('RGB',(80,40),(i*60,80,120)).save(path)
            os.utime(path,(1700000000+i*86400,1700000000+i*86400))
        return p,c

    def test_favorite_rotation_restart_and_original_bytes(self):
        p,c=self.library();p.select('foto-prueba-1.jpg',unlocked=True);path=c.directory/'foto-prueba-1.jpg';raw=path.read_bytes()
        self.assertTrue(p.edit_selected('favorite',unlocked=True));self.assertTrue(p.edit_selected('rotate',unlocked=True))
        self.assertEqual(p.catalog.meta(path.name),dict(favorite=True,rotation=1))
        deadline=time.monotonic()+2
        while not p.snapshot(unlocked=True)['ready'] and time.monotonic()<deadline:time.sleep(.01)
        self.assertEqual(p.snapshot(unlocked=True)['original_size'],(40,80));self.assertEqual(path.read_bytes(),raw)
        restored=PhotoCatalog(c.directory.parent);self.assertEqual(restored.meta(path.name),dict(favorite=True,rotation=1))
        self.assertFalse(p.edit_selected('rotate',unlocked=False));self.assertEqual(restored.meta(path.name)['rotation'],1)

    def test_collections_date_session_and_favorite_navigation(self):
        p,c=self.library();p.select('foto-prueba-0.jpg',unlocked=True);p.edit_selected('favorite',unlocked=True)
        p.select('foto-prueba-2.jpg',unlocked=True);p.edit_selected('favorite',unlocked=True)
        ident=p.catalog.begin('cabina',3);p.catalog.record(ident,'foto-prueba-0.jpg');p.catalog.record(ident,'foto-prueba-1.jpg',state='terminada')
        groups=p.collections(True);self.assertEqual(len([g for g in groups if g['id'].startswith('date:')]),3)
        self.assertTrue(p.set_collection('favorites',True));self.assertEqual(p.grid(unlocked=True)['count'],2)
        self.assertEqual(p.snapshot(unlocked=True)['filename'],'foto-prueba-2.jpg');p.move(1,unlocked=True)
        self.assertEqual(p.snapshot(unlocked=True)['filename'],'foto-prueba-0.jpg')
        p.set_collection('session:'+ident,True);self.assertEqual(p.grid(unlocked=True)['count'],2)
        self.assertEqual(p.collections(False),[])

    def test_metadata_write_failure_keeps_previous_state(self):
        p,c=self.library();name='foto-prueba-0.jpg';p.catalog.edit(name,favorite=True)
        original=p.catalog.path.read_bytes()
        with patch('photo_catalog.write_private',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):p.catalog.edit(name,favorite=False)
        self.assertTrue(p.catalog.meta(name)['favorite']);self.assertEqual(p.catalog.path.read_bytes(),original)
        with self.assertRaises(ValueError):p.catalog.edit('../secret',favorite=True)
        with self.assertRaises(ValueError):p.catalog.edit(name,rotation=5)

    def test_sessions_are_persistent_bounded_and_not_resumed(self):
        p,c=self.library();ident=p.catalog.begin('timelapse',10);p.catalog.record(ident,'foto-prueba-0.jpg')
        restored=PhotoCatalog(c.directory.parent);s=restored.sessions()[0]
        self.assertEqual(s['names'],['foto-prueba-0.jpg']);self.assertEqual(s['state'],'detenida')
        p.catalog.record(ident,'foto-prueba-1.jpg',state='terminada')
        self.assertEqual(PhotoCatalog(c.directory.parent).sessions()[0]['state'],'terminada')
        if os.name!='nt':self.assertEqual(p.catalog.path.stat().st_mode&0o777,0o600)

    def test_native_album_options_and_rotated_copy(self):
        p,c=self.library();h=hub();h.photos=p;h.camera=c;h.role='owner'
        p.select('foto-prueba-0.jpg',unlocked=True);h.navigate('gallery');h.last_touch=0;h.touch(540,30);h.render()
        self.assertEqual(h._photo_action[0],'edit');h.last_touch=0;h.touch(350,290)
        self.assertEqual(h.screen,'gallery');self.assertEqual(p.snapshot(unlocked=True)['rotation'],1)
        raw=(c.directory/'foto-prueba-0.jpg').read_bytes();self.assertTrue(p.save_copy(unlocked=True))
        deadline=time.monotonic()+2
        while p.snapshot(unlocked=True)['saving'] and time.monotonic()<deadline:time.sleep(.01)
        name=p.snapshot(unlocked=True)['last_saved'];self.assertTrue(name)
        with Image.open(c.directory/name) as image:self.assertEqual(image.size,(40,80))
        self.assertEqual((c.directory/'foto-prueba-0.jpg').read_bytes(),raw)
        h.navigate('gallery_grid');h.last_touch=0;h.touch(450,70);h.render()
        self.assertEqual(h._photo_action[0],'collections');self.assertTrue(h._group_items)


if __name__=='__main__':unittest.main()
