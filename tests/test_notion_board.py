import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from notion_board import NotionBoard,normalize,query_tasks,write_private
from test_dashboard import hub


class NotionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)

    def test_normalization_sort_closed_removal_and_length_bounds(self):
        rows=normalize([{'Tarea':'\x00Sin fecha','Estado':'Pendiente'},
                        {'Tarea':'Fecha','date:Fecha límite:start':'2026-11-10','Estado':'En curso'},
                        {'Tarea':'Terminada','Estado':'Terminada'},
                        {'title':'a'*1000,'next':'b'*1500,'state':'Cancelada'}])
        self.assertEqual([r['title'] for r in rows],['Fecha','Sin fecha'])
        self.assertEqual(len(normalize([{'title':'x'*999}])[0]['title']),400)

    def test_authenticated_paginated_read_only_query_and_mapping(self):
        calls=[]
        def opener(request,timeout):
            calls.append(request)
            self.assertEqual(request.method,'POST')
            self.assertTrue(request.full_url.endswith('/query'))
            self.assertEqual(request.get_header('Notion-version'),'2026-03-11')
            self.assertEqual(timeout,10)
            first=len(calls)==1
            page={'properties':{'Tarea':{'title':[{'plain_text':'Medir motor'}]},'Estado':{'select':{'name':'Pendiente'}},'Fecha límite':{'date':{'start':'2026-11-10'}},'Siguiente paso':{'rich_text':[{'plain_text':'Preparar banco'}]}}}
            return io.BytesIO(json.dumps({'results':[page] if first else [],'has_more':first,'next_cursor':'cursor2' if first else None}).encode())
        rows=query_tasks({'data_source':'a'*32,'token':'test-only'},opener)
        self.assertEqual(rows[0]['title'],'Medir motor');self.assertEqual(rows[0]['next'],'Preparar banco')
        self.assertEqual(json.loads(calls[1].data)['start_cursor'],'cursor2')
        self.assertEqual(len(json.loads(calls[0].data)['filter']['and']),2)

    def test_failure_keeps_last_success_and_lock_does_not_show_data(self):
        config=self.root/'config.json';write_private(config,{'token':'test-only'})
        board=NotionBoard(self.root,threading.Event(),config=config,fetcher=lambda _:normalize([{'title':'Privada'}]),start=False)
        board.update(); first=board.snapshot(True)
        self.assertEqual(first['status'],'Sincronizado'); self.assertEqual(len(first['tasks']),1)
        self.assertEqual(board.snapshot(False)['tasks'],[])
        if os.name!='nt':self.assertEqual(board.path.stat().st_mode&0o777,0o600)
        def fail(_):raise OSError('private values must not be logged')
        board.fetcher=fail;board.update()
        self.assertEqual(board.snapshot(True)['updated'],first['updated'])
        restored=NotionBoard(self.root,threading.Event(),start=False)
        self.assertEqual(restored.snapshot(True)['tasks'],first['tasks'])
        h=hub();h.notion=board;h.screen='notion';h._notion_selected=first['tasks'][0]
        h.unlocked=False;commands=[];h.send=commands.append;h.draw_notion()
        self.assertFalse(any('Privada' in c for c in commands))

    def test_ui_list_detail_back_and_lock_gate(self):
        board=NotionBoard(self.root,threading.Event(),start=False)
        board.rows=normalize([{'title':'Revisar montaje','next':'Comprobar holguras'}])
        h=hub();h.notion=board;h.screen='status';h.touch(650,90)
        self.assertEqual(h.screen,'notion')
        h.last_touch=0;h.touch(120,180)
        self.assertEqual(h._notion_selected['title'],'Revisar montaje')
        commands=[];h.send=commands.append;h.render()
        self.assertTrue(any('Comprobar holguras' in c for c in commands))
        h.last_touch=0;h.touch(100,450);self.assertIsNone(h._notion_selected)
        h.unlocked=False;h.navigate('notion');self.assertEqual(h.screen,'lock')


if __name__=='__main__':unittest.main()
