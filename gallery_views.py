"""Galería privada con vista previa y copias de efectos elegidos en pantalla."""
import time
from gallery_pixels import preview_passes
from photo_library import FILTERS


class GalleryViews:
    def gallery_clear_preview(self):
        self.artwork.clear(); self.art_key=None
        self.fill(32,100,528,297,self.theme['card'])
        for key in ('galleryempty0','galleryempty1','galleryempty2','galleryloading'):
            self.cache.pop(key,None)

    def draw_gallery(self):
        c=self.theme; library=getattr(self,'photos',None)
        state=library.snapshot(unlocked=self.unlocked) if library else None
        count=state['count'] if state else 0
        index=state['index'] if count else -1
        title='Galería / '+str(index+1)+' de '+str(count) if count else 'Galería'
        self.text('gallerytitle',32,64,528,28,2,title,c['ink'],c['bg'])
        self.text('galleryeffects',584,64,184,28,2,'EFECTOS',c['muted'],c['bg'],1)
        selected=state['filter'] if state else 'Original'
        for i,label in enumerate(FILTERS):
            self.soft_button('galleryfilter'+str(i),584,100+i*42,184,36,label,label==selected,2)
        self.soft_button('galleryprev',32,410,104,50,'Anterior',False,2)
        self.soft_button('gallerynext',456,410,104,50,'Siguiente',False,2)
        self.soft_button('gallerysave',584,410,184,50,'Guardando...' if state and state['saving'] else 'Guardar copia',selected!='Original' and bool(count),2)
        filename=state['filename'] if state else ''
        message=state['status'] if state else 'Cámara no disponible'
        self.text('galleryfilename',152,410,288,24,2,self.fit(filename,288),c['muted'],c['bg'],1)
        self.text('gallerystatus',152,438,288,24,2,self.fit(message,288),c['mint'],c['bg'],1)
        if not count:
            if self.art_key!=('gallery-empty',):
                self.gallery_clear_preview(); self.art_key=('gallery-empty',)
            self.paragraph('galleryempty',64,182,464,'Tus fotos aparecerán aquí. Vuelve a Cámara y pulsa Tomar foto.',3,0,bg=c['card'])
            return
        preview=state.get('preview'); key=state.get('preview_key')
        if not preview or not key or key[:2]!=(filename,selected):
            pending=('gallery-pending',filename,selected)
            if self.art_key!=pending:
                self.gallery_clear_preview(); self.art_key=pending
            label='No se pudo abrir la foto' if state.get('error') else 'Preparando foto...'
            self.text('galleryloading',64,216,464,48,0,label,c['muted'],c['card'],1)
            return
        ident=('gallery',key)
        if self.art_key!=ident:
            self.gallery_clear_preview(); self.art_key=ident
            cols,rows,pixels=preview
            coarse,detail=preview_passes(pixels,cols,rows,32,100,528,297)
            self.artwork.extend(coarse); self.artwork.extend(detail)
            self.art_started=time.monotonic(); self.art_total=len(self.artwork)

    def touch_gallery(self,x,y):
        library=getattr(self,'photos',None)
        if not self.unlocked or not library: return False
        if 632<=x<768 and 12<=y<52:
            self.navigate('camera'); return True
        state=library.snapshot(unlocked=True)
        before=(state['filename'],state['filter'],state.get('preview_key'))
        changed=False
        if 584<=x<768:
            if 100<=y<388:
                index=(y-100)//42
                if index<len(FILTERS) and (y-100)%42<36:
                    changed=library.set_filter(FILTERS[index],unlocked=True)
            elif 410<=y<460:
                library.save_copy(unlocked=True); return True
        elif 410<=y<460:
            if 32<=x<136: changed=library.move(-1,unlocked=True)
            elif 456<=x<560: changed=library.move(1,unlocked=True)
        if changed:
            state=library.snapshot(unlocked=True)
            after=(state['filename'],state['filter'],state.get('preview_key'))
            if after!=before: self.gallery_clear_preview()
        return bool(changed)
