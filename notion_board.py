"""Consulta de tareas Notion: sólo lectura, caché privada y actualización acotada."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
import urllib.request
import uuid

MAX_BYTES=2*1024*1024


def text(value,limit=400):
    return ''.join(c for c in str(value or '') if c.isprintable())[:limit]


def normalize(rows):
    result=[]
    if not isinstance(rows,list):return result
    for row in rows[:500]:
        if not isinstance(row,dict):continue
        state=text(row.get('state',row.get('Estado')),40)
        if state in ('Terminada','Cancelada'): continue
        result.append(dict(title=text(row.get('title',row.get('Tarea'))),state=state or 'Por definir',
                           due=text(row.get('due',row.get('date:Fecha límite:start')),40),
                           next=text(row.get('next',row.get('Siguiente paso')),800),
                           priority=text(row.get('priority',row.get('Prioridad')),20)))
    return sorted(result,key=lambda r:(not bool(r['due']),r['due'],r['title']))


def read_private(path,limit=MAX_BYTES):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_size>limit:
        raise ValueError('Archivo privado no válido')
    if os.name!='nt' and info.st_mode&0o077: raise ValueError('Permisos privados requeridos')
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(descriptor,'r',encoding='utf8') as stream: return json.load(stream)


def write_private(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as stream:
            json.dump(data,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def query_tasks(config,opener=urllib.request.urlopen):
    source=config.get('data_source',''); token=config.get('token','')
    if not re.fullmatch(r'[a-fA-F0-9-]{32,36}',source) or not isinstance(token,str) or not token:
        raise ValueError('Configura la conexión de Notion')
    rows=[];cursor=None
    for _ in range(5):
        body=dict(page_size=100,filter={'and':[{'property':'Estado','select':{'does_not_equal':s}} for s in ('Terminada','Cancelada')]})
        if cursor:body['start_cursor']=cursor
        request=urllib.request.Request('https://api.notion.com/v1/data_sources/'+source+'/query',
            data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,
            'Notion-Version':'2026-03-11','Content-Type':'application/json'},method='POST')
        with opener(request,timeout=10) as response:
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError('Respuesta demasiado grande')
            data=json.loads(raw)
        for page in data['results']:
            props=page['properties']
            def rich(key,kind='rich_text'):
                return ''.join(v.get('plain_text',v.get('text',{}).get('content','')) for v in props.get(key,{}).get(kind,[]))
            def select(key):return (props.get(key,{}).get('select') or {}).get('name','')
            rows.append(dict(title=rich('Tarea','title'),state=select('Estado'),priority=select('Prioridad'),
                             due=(props.get('Fecha límite',{}).get('date') or {}).get('start',''),next=rich('Siguiente paso')))
        if not data.get('has_more'): return normalize(rows)
        next_cursor=data.get('next_cursor')
        if not next_cursor or next_cursor==cursor:raise ValueError('Paginación no válida')
        cursor=next_cursor
    raise ValueError('Hay más de 500 tareas; limita la base para este panel')


class NotionBoard:
    def __init__(self,directory,stop,config=None,fetcher=query_tasks,start=True):
        self.path=Path(directory)/'notion-tasks.json'
        self.config=Path(config) if config else Path.home()/'.config/desk-hub/notion.json'
        self.stop=stop;self.fetcher=fetcher;self.lock=threading.Lock();self.wake=threading.Event()
        self.rows=[];self.updated=0;self.status='Conexión pendiente';self.last_attempt=0
        try:
            data=read_private(self.path);updated=float(data['updated'])
            if not 0<updated<4102444800:raise ValueError('Fecha de consulta no válida')
            self.rows=normalize(data['tasks']);self.updated=updated
        except (OSError,ValueError,KeyError,TypeError):pass
        if start:threading.Thread(target=self.worker,daemon=True,name='desk-hub-notion').start()

    def snapshot(self,allowed=False):
        with self.lock:
            if not allowed:return dict(tasks=[],updated=0,status='Panel bloqueado')
            return dict(tasks=[dict(r) for r in self.rows],updated=self.updated,status=self.status)

    def refresh(self):self.wake.set()

    def update(self):
        try:
            config=read_private(self.config,16384)
            rows=self.fetcher(config);now=time.time()
            write_private(self.path,dict(tasks=rows,updated=now))
            with self.lock:self.rows=rows;self.updated=now;self.status='Sincronizado'
        except FileNotFoundError:
            with self.lock:self.status='Copia guardada / conexión pendiente' if self.updated else 'Configura Notion en la Pi'
        except Exception:
            with self.lock:self.status='Sin conexión / conserva la última consulta'

    def worker(self):
        while not self.stop.is_set():
            now=time.monotonic()
            if now-self.last_attempt>=300 or self.wake.is_set() and now-self.last_attempt>=30:
                self.last_attempt=now;self.wake.clear();self.update()
            self.stop.wait(1)


class NotionViews:
    def draw_notion(self):
        c=self.theme;board=getattr(self,'notion',None)
        allowed=self.unlocked and getattr(self,'role','owner')=='owner'
        state=board.snapshot(allowed) if board else dict(tasks=[],updated=0,status='No disponible')
        rows=state['tasks'];page=max(0,min(getattr(self,'_notion_page',0),max(0,(len(rows)-1)//3)))
        self._notion_page=page
        identity=(state['updated'],page,allowed,len(rows))
        if self.cache.get('notionrows')!=identity:
            self.fill(0,140,800,340,c['bg'])
            for key in list(self.cache):
                if key.startswith(('task','button:task','notionpage','button:notionprev','button:notionnext','notionempty')):self.cache.pop(key,None)
            self.cache['notionrows']=identity
        self.text('notiontitle',32,68,736,40,0,'Robotec / tareas abiertas',c['ink'],c['bg'])
        stamp=dt.datetime.fromtimestamp(state['updated']).strftime('%d/%m %H:%M') if state['updated'] else 'sin consulta'
        self.text('notionstamp',32,108,736,28,2,state['status']+' · '+stamp,c['muted'],c['bg'])
        selected=getattr(self,'_notion_selected',None) if allowed else None
        if selected is not None:
            self.paragraph('tasktitle',32,150,736,selected['title'],3,0)
            self.text('taskstate',32,276,736,30,2,selected['state']+' · '+(selected['due'][:10] or 'Sin fecha'),c['mint'],c['bg'])
            self.paragraph('tasknext',32,318,736,selected['next'] or 'Sin siguiente paso registrado.',4,2)
            self.soft_button('taskback',32,438,200,40,'Volver a tareas');return
        for i,row in enumerate(rows[page*3:page*3+3]):
            y=148+i*86
            self.soft_button('task'+str(i),32,y,736,76,'',False,2)
            self.text('tasklabel'+str(i),48,y+4,700,32,0,self.fit(row['title'],700,0),c['ink'],c['button'])
            self.text('taskmeta'+str(i),48,y+40,700,28,2,row['state']+' · '+(row['due'][:10] or 'Sin fecha'),c['mint'],c['button'])
        if not rows:self.paragraph('notionempty',48,180,704,'No hay tareas disponibles. La consulta es de sólo lectura.',3,0)
        self.soft_button('notionprev',32,432,180,44,'Anterior')
        self.text('notionpage',232,432,336,44,2,f'{page+1} / {max(1,(len(rows)+2)//3)} · {len(rows)} tareas',c['muted'],c['bg'],1)
        self.soft_button('notionnext',588,432,180,44,'Siguiente')

    def touch_notion(self,x,y):
        if not self.unlocked or getattr(self,'role','owner')!='owner':return
        if 632<=x<768 and 12<=y<52:self._notion_selected=None;self.navigate('home');return
        if 496<=x<616 and 12<=y<52:
            if self.notion:self.notion.refresh()
            return
        rows=self.notion.snapshot(True)['tasks'] if self.notion else []
        if getattr(self,'_notion_selected',None) is not None:
            if 32<=x<232 and 438<=y<478:self._notion_selected=None;self.navigate('notion')
            return
        if 432<=y<476:
            step=-1 if 32<=x<212 else 1 if 588<=x<768 else 0
            self._notion_page=max(0,min(getattr(self,'_notion_page',0)+step,max(0,(len(rows)-1)//3)))
            self.navigate('notion');return
        if 32<=x<768 and 148<=y<396 and (y-148)%86<76:
            index=getattr(self,'_notion_page',0)*3+(y-148)//86
            if index<len(rows):self._notion_selected=rows[index];self.navigate('notion')
