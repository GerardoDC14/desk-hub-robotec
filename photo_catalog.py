"""Metadatos privados del álbum; nunca modifica los JPEG originales."""
import copy
import json
from pathlib import Path
import re
import threading
import time
import uuid
from notion_board import read_private,write_private

NAME=re.compile(r'(?:foto|efecto)-[A-Za-z0-9][A-Za-z0-9_-]{0,95}\.jpg\Z')


class PhotoCatalog:
    def __init__(self,directory):
        self.path=Path(directory)/'photo-catalog.json';self.lock=threading.RLock()
        self.data={'photos':{},'sessions':[]};self.error=''
        try:
            data=read_private(self.path,512*1024)
            if not isinstance(data,dict):raise ValueError('Catálogo')
            for name,meta in data.get('photos',{}).items():
                if NAME.fullmatch(name) and isinstance(meta,dict):
                    self.data['photos'][name]=dict(favorite=meta.get('favorite') is True,rotation=meta.get('rotation',0) if type(meta.get('rotation',0)) is int and 0<=meta.get('rotation',0)<4 else 0)
            for session in data.get('sessions',[])[:100]:
                if not isinstance(session,dict) or not re.fullmatch('[a-f0-9]{32}',str(session.get('id',''))) or session.get('kind') not in ('timelapse','cabina'):continue
                names=session.get('names',[])
                if not isinstance(names,list):continue
                self.data['sessions'].append(dict(id=session['id'],kind=session['kind'],created=max(0,min(4102444800,float(session.get('created',0)))),interval=int(session.get('interval',0)),names=[n for n in names[:100] if isinstance(n,str) and NAME.fullmatch(n)],result=session.get('result','') if NAME.fullmatch(str(session.get('result',''))) else '',state='terminada' if session.get('state')=='terminada' else 'detenida'))
        except FileNotFoundError:pass
        except (OSError,ValueError,TypeError,AttributeError):self.error='No se pudo leer el catálogo privado.'

    def _commit(self,data):
        if self.error:raise ValueError(self.error)
        if len(data['photos'])>1000 or len(json.dumps(data))>512*1024:raise ValueError('Catálogo lleno')
        write_private(self.path,data);self.data=data

    def meta(self,name):
        with self.lock:return dict(self.data['photos'].get(name,dict(favorite=False,rotation=0)))

    def edit(self,name,*,favorite=None,rotation=None):
        if not isinstance(name,str) or not NAME.fullmatch(name):raise ValueError('Nombre')
        if favorite is not None and type(favorite) is not bool:raise ValueError('Favorito')
        if rotation is not None and (type(rotation) is not int or not 0<=rotation<4):raise ValueError('Giro')
        with self.lock:
            data=copy.deepcopy(self.data);meta=self.meta(name)
            if favorite is not None:meta['favorite']=favorite
            if rotation is not None:meta['rotation']=rotation
            data['photos'][name]=meta;self._commit(data)

    def sessions(self):
        with self.lock:return copy.deepcopy(self.data['sessions'])

    def begin(self,kind,interval=0):
        if kind not in ('timelapse','cabina') or type(interval) is not int or not 0<=interval<=3600:raise ValueError('Sesión')
        with self.lock:
            data=copy.deepcopy(self.data);ident=uuid.uuid4().hex
            data['sessions'].insert(0,dict(id=ident,kind=kind,created=time.time(),interval=interval,names=[],result='',state='en curso'))
            data['sessions']=data['sessions'][:100];self._commit(data);return ident

    def record(self,ident,name=None,*,result=None,state=None):
        if name is not None and not NAME.fullmatch(name):raise ValueError('Foto')
        if result is not None and not NAME.fullmatch(result):raise ValueError('Composición')
        if state is not None and state not in ('terminada','detenida'):raise ValueError('Estado')
        with self.lock:
            data=copy.deepcopy(self.data)
            session=next((s for s in data['sessions'] if s['id']==ident),None)
            if not session:raise ValueError('Sesión inexistente')
            if name and name not in session['names']:
                if len(session['names'])>=100:raise ValueError('Sesión llena')
                session['names'].append(name)
            if result is not None:session['result']=result
            if state is not None:session['state']=state
            self._commit(data)
