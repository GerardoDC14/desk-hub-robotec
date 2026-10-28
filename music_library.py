"""Canciones y episodios guardados explícitamente en el Hub, sin historial automático."""
import re
from nextion_link import safe_text


class MusicLibrary:
    MAX_ITEMS=24
    URI=re.compile(r'spotify:(?:track|episode):[A-Za-z0-9]{1,64}\Z')

    def __init__(self,data=None):
        self.data=[]
        self.status=''
        self.removed=None
        if isinstance(data,list):
            for item in data[:self.MAX_ITEMS*4]:
                self.add(item)
        self.status=''

    @classmethod
    def clean(cls,item):
        if not isinstance(item,dict): return None
        uri=item.get('uri')
        if not isinstance(uri,str) or not cls.URI.fullmatch(uri): return None
        title=safe_text(item.get('title') if isinstance(item.get('title'),str) else 'Sin título',120)
        artist=safe_text(item.get('artist') if isinstance(item.get('artist'),str) else 'Spotify',100)
        return dict(uri=uri,title=title or 'Sin título',artist=artist or 'Spotify')

    def add(self,item):
        entry=self.clean(item)
        if entry is None:
            self.status='invalid'; return False
        for index,saved in enumerate(self.data):
            if saved['uri']==entry['uri']:
                if self.removed is not None and self.removed[1]['uri']==entry['uri']:
                    self.removed=None
                self.data[index]=entry; self.status='updated'; return True
        if len(self.data)>=self.MAX_ITEMS:
            self.status='full'; return False
        self.data.append(entry)
        if self.removed is not None and self.removed[1]['uri']==entry['uri']:
            self.removed=None
        self.status='saved'; return True

    @property
    def can_undo(self):
        return (self.removed is not None and len(self.data)<self.MAX_ITEMS
                and all(item['uri']!=self.removed[1]['uri'] for item in self.data))

    def remove(self,uri):
        for index,saved in enumerate(self.data):
            if saved['uri']==uri:
                self.removed=(index,self.data.pop(index)); return True
        return False

    def undo_remove(self):
        if self.removed is None or len(self.data)>=self.MAX_ITEMS: return False
        index,entry=self.removed
        if any(item['uri']==entry['uri'] for item in self.data):
            self.removed=None; return False
        self.data.insert(min(index,len(self.data)),entry)
        self.removed=None
        return True


class LibraryViews:
    def draw_library(self):
        c=self.theme
        editing=getattr(self,'library_editing',False)
        self.soft_button('libraryedit',496,12,120,40,'Listo' if editing else 'Editar',editing,2)
        page=max(0,min(getattr(self,'library_page',0),max(0,(len(self.library.data)-1)//4)))
        self.library_page=page
        entries=self.library.data[page*4:page*4+4]
        self.text('librarytitle',32,78,420,44,0,'Quitar guardadas' if editing else 'Música guardada',c['ink'],c['bg'])
        self.soft_button('librarysave',480,78,288,44,'Guardar actual',False,0)
        style=(page,editing,tuple((e['uri'],e['title'],e['artist']) for e in entries))
        if self.cache.get('libraryrows')!=style:
            self.fill(48,136,704,250,c['bg'])
            for key in list(self.cache):
                if key.startswith(('panel:libraryrow','libraryrow','libraryempty','icon:libraryplay','icon:libraryremove')):
                    self.cache.pop(key,None)
            self.cache['libraryrows']=style
        if not entries:
            self.text('libraryempty1',64,176,672,48,0,'Tu selección empieza aquí.',c['ink'],c['bg'])
            self.paragraph('libraryempty2',64,238,672,'Reproduce una canción o episodio y pulsa Guardar actual. Después podrás escucharlo desde esta pantalla.',3,0)
        for i,item in enumerate(entries):
            y=136+i*64
            self.panel('libraryrow'+str(i),48,y,704,58,c['card'],8)
            self.text('libraryrowtitle'+str(i),64,y+2,598,34,0,self.fit(item['title'],598,0),c['ink'],c['card'])
            self.text('libraryrowartist'+str(i),64,y+36,598,20,2,self.fit(item['artist'],598),c['muted'],c['card'])
            if editing:
                key='icon:libraryremove'+str(i)
                style=(718,y+29,c['coral'],c['bg'])
                if self.cache.get(key)!=style:
                    self.send(f"cirs 718,{y+29},20,{c['coral']}")
                    for offset in (-1,0,1):
                        self.send(f"line {710+offset},{y+21},{726+offset},{y+37},{c['bg']}")
                        self.send(f"line {710+offset},{y+37},{726+offset},{y+21},{c['bg']}")
                    self.cache[key]=style
            else:
                self.icon_button('libraryplay'+str(i),718,y+29,20,'play',True)
        pages=max(1,(len(self.library.data)+3)//4)
        for key,x,title,enabled in [('libraryprev',48,'Anterior',page>0),('librarynext',592,'Siguiente',page+1<pages)]:
            if enabled:
                self.cache.pop(key+'blank',None)
                self.soft_button(key,x,390,160,32,title,False,2)
            else:
                self.text(key+'blank',x,390,160,32,2,'',c['muted'],c['bg'])
                self.cache.pop('button:'+key,None); self.cache.pop(key,None)
        can_undo=self.library.can_undo
        if self.cache.get('libraryundostyle')!=can_undo:
            self.fill(216,390,368,32,c['bg'])
            for key in ('librarymessage','libraryundo','button:libraryundo'):
                self.cache.pop(key,None)
            self.cache['libraryundostyle']=can_undo
        if can_undo:
            self.soft_button('libraryundo',216,390,368,32,'Deshacer eliminación',False,2)
        else:
            message=getattr(self,'library_message','') or ('Toca una tarjeta para quitarla' if editing else f'{len(self.library.data)} guardadas / {page+1} de {pages}')
            self.text('librarymessage',216,390,368,32,2,self.fit(message,368),c['mint'],c['bg'],1)

    def touch_library(self,x,y):
        if not self.unlocked: return True
        if 496<=x<616 and 12<=y<52:
            self.library_editing=not getattr(self,'library_editing',False)
            self.library_message=''
            return True
        if 480<=x<768 and 78<=y<122:
            with self.lock: music=self.music.copy()
            saved=self.library.add(music)
            self.library_message={'saved':'Guardada en el Hub','updated':'Ya estaba guardada','full':'Límite: 24 canciones o episodios','invalid':'Elige una canción en Spotify'}[self.library.status]
            if saved:
                self.library_page=next(i//4 for i,item in enumerate(self.library.data) if item['uri']==music['uri'])
                self.save()
            return True
        if 48<=x<752 and 136<=y<386:
            row=(y-136)//64
            if (y-136)%64>=58: return True
            index=max(0,getattr(self,'library_page',0))*4+row
            if 0<=index<len(self.library.data):
                if getattr(self,'library_editing',False):
                    self.library.remove(self.library.data[index]['uri'])
                    self.library_page=min(getattr(self,'library_page',0),max(0,(len(self.library.data)-1)//4))
                    self.library_message='Quitada de las guardadas'
                    self.save()
                else:
                    result=self.request_selected_music(self.library.data[index]['uri'])
                    if result is False: self.library_message='Conecta Spotify para escuchar'
                    else: self.navigate('music')
            return True
        if 390<=y<422:
            if 216<=x<584 and self.library.can_undo:
                index=self.library.removed[0]
                if self.library.undo_remove():
                    self.library_page=index//4
                    self.library_message='Canción o episodio restaurado'
                    self.save()
                return True
            pages=max(1,(len(self.library.data)+3)//4)
            if 48<=x<208: self.library_page=max(0,getattr(self,'library_page',0)-1)
            elif 592<=x<752: self.library_page=min(pages-1,getattr(self,'library_page',0)+1)
            else: return False
            self.library_message=''; return True
        return False
