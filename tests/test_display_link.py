"""Regresiones de texto, límites UART y navegación del aviso público."""
import time
import unittest
from collections import deque
from test_dashboard import hub
from desk_hub import Frames
from nextion_link import NextionLink, safe_text, END


class LinkTests(unittest.TestCase):
    def link(self,replies):
        self.packets=[]; self.replies=deque(replies); self.clock=0
        def receive(timeout):
            self.clock+=timeout
            return self.replies.popleft() if self.replies else b''
        return NextionLink(self.packets.append,receive,Frames(),lambda:self.clock)

    def test_text_cannot_insert_quotes_controls_or_frame_terminator(self):
        text=safe_text('Repo"\r\n\\\x00\xff\xff\xff\u202e get sys0 “otro”\tfinal')
        self.assertNotIn('"',text); self.assertNotIn('\\',text)
        self.assertFalse(any(ord(c)<32 or ord(c)==255 for c in text))
        self.assertLessEqual(len(safe_text('a'*1000)),160)
        self.assertNotIn(END,text.encode('latin-1'))

    def test_fence_and_touch_in_same_read_preserve_all_touches(self):
        touch=bytes.fromhex('670100010000')
        fence=bytes.fromhex('7100000000')
        raw=touch+END+fence+END+touch+END
        link=self.link([raw[:7],raw[7:]])
        link.send(['fill 0,0,1,1,0'])
        self.assertEqual(list(link.pending),[touch,touch])
        self.assertTrue(self.packets[0].endswith(b'get sys0'+END))

    def test_batch_is_bounded_and_each_batch_waits_for_fence(self):
        fence=bytes.fromhex('7100000000')+END
        link=self.link([fence]*20)
        commands=['fill 0,0,10,10,65535']*50
        link.send(commands)
        self.assertGreater(len(self.packets),1)
        self.assertTrue(all(len(p)<=256 for p in self.packets))
        self.assertEqual(sum(p.count(b'fill ') for p in self.packets),50)

    def test_error_is_not_silently_cached_as_success(self):
        link=self.link([b'\x24'+END+bytes.fromhex('7100000000')+END])
        with self.assertRaisesRegex(OSError,'24'): link.send(['fill 0,0,1,1,0'])

    def test_unconfirmed_lot_times_out(self):
        link=self.link([])
        with self.assertRaises(TimeoutError): link.send(['fill 0,0,1,1,0'])

    def test_oversized_and_embedded_commands_are_rejected(self):
        link=self.link([])
        for command in ['a'*240,'cls 0\xff\xff\xffget sys0']:
            with self.assertRaises(ValueError): link.send([command])
        self.assertFalse(self.packets)


class PublicDisplayTests(unittest.TestCase):
    def away(self):
        value=hub(); value.screen='away'; value.compact=True; value.unlocked=False
        value.timer.mode('away'); value.repo_index=0; value.carousel_started=time.monotonic()
        value.repos=[dict(name='Proyecto '+str(i),language='Python',description='Descripcion',stargazers_count=0) for i in range(3)]
        value.images['profileqr']=[65535]*37**2
        return value

    def test_public_project_navigation_does_not_unlock(self):
        value=self.away(); value.touch(710,357)
        self.assertEqual(value.repo_index,1); self.assertFalse(value.unlocked)
        value.last_touch=0; value.touch(710,435)
        self.assertEqual(value.screen,'lock'); self.assertIsNotNone(value.timer.data['deadline'])
        value.last_touch=0; value.touch(200,416)
        self.assertEqual(value.screen,'away'); self.assertFalse(value.unlocked)

    def test_unlock_area_does_not_include_count_or_project(self):
        value=self.away()
        for x,y in [(100,350),(550,300),(400,435)]:
            value.last_touch=0; value.touch(x,y)
            self.assertEqual(value.screen,'away')

    def test_pin_key_gaps_do_not_add_digits(self):
        value=hub(); value.screen='lock'; value.unlocked=False
        value.touch(430,140); self.assertEqual(value.pin_entry,'1')
        value.last_touch=0; value.touch(522,140); self.assertEqual(value.pin_entry,'1')

    def test_unlocked_visitor_can_return_home(self):
        value=self.away(); value.unlocked=True; value.touch(130,435)
        self.assertEqual(value.screen,'home'); self.assertTrue(value.unlocked)

    def test_text_style_changes_redraw_even_if_value_is_unchanged(self):
        value=hub(); commands=[]; value.send=commands.append
        value.text('label',0,0,100,30,2,'Texto',1,0)
        value.text('label',0,0,100,30,2,'Texto',2,0)
        self.assertEqual(len(commands),2)

    def test_unlock_text_and_picture_have_disjoint_bounds(self):
        value=self.away(); commands=[]; value.send=commands.append
        value.render()
        unlock=next(c for c in commands if c.startswith('xstr') and '"Desbloquear"' in c)
        self.assertEqual(unlock.count('"'),2)
        self.assertGreaterEqual(int(unlock.split(',')[1]),416)
        for command in value.artwork:
            x,y,w,h,_=map(int,command.partition(' ')[2].split(','))
            self.assertLess(y+h,400)

    def test_temperature_width_change_repaints_icon_at_its_new_position(self):
        value=hub(); value.screen='home'; commands=[]; value.send=commands.append
        value.network['weather']='-- °C'; value.render()
        commands.clear(); value.network['weather']='8 °C'; value.render()
        self.assertTrue(any(c.startswith('cirs ') for c in commands))
        self.assertTrue(any('"8°"' in c for c in commands))

    def test_long_away_duration_fits_remaining_time(self):
        value=self.away(); value.timer.data.update(duration=7200,remaining=7200,deadline=None)
        value.timer.toggle(); commands=[]; value.send=commands.append; value.render()
        count=next(c for c in commands if c.startswith('xstr') and 'Faltan' in c)
        fields=count.partition(' ')[2].split(',',10)
        self.assertLessEqual(value.text_width(fields[10].strip('"'),int(fields[4])),int(fields[2]))


if __name__=='__main__': unittest.main()
