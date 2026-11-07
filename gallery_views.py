"""Galería privada con vista previa y copias de efectos elegidos en pantalla."""
import time
from gallery_pixels import preview_passes
from photo_library import FILTERS


class GalleryViews:
    def photo_dialog(self, action, item=None):
        self._photo_action=(action,item)
        self.artwork.clear(); self.art_key=None; self.cache.clear()
        self.dirty=True

    def draw_photo_dialog(self):
        action,item=self._photo_action; c=self.theme
        if action=='trash_list':
            entries=self.photos.trash_items(unlocked=self.unlocked)
            index=max(0,min(getattr(self,'_trash_index',0),len(entries)-1))
            self._trash_index=index; item=entries[index] if entries else None
            self._trash_item=item
            title='Papelera / '+str(index+1)+' de '+str(len(entries)) if entries else 'Papelera vacía'
            message='Puedes restaurar la foto o eliminarla definitivamente.' if entries else 'Las fotos eliminadas del álbum aparecerán aquí.'
        elif action=='error':
            title='No se pudo completar'
            message='La foto se conserva. Espera a que termine la cámara y vuelve a intentarlo.'
        else:
            title='¿Eliminar esta foto?' if action=='trash' else '¿Eliminar definitivamente?'
            message='Se moverá a la papelera. Podrás recuperarla.' if action=='trash' else 'Esta acción no se puede deshacer.'
        self.text('photodialogtitle',48,90,704,48,0,title,c['ink'],c['bg'],1)
        name=(item or {}).get('name','')
        self.text('photodialogname',48,166,704,30,2,self.fit(name,704),c['muted'],c['bg'],1)
        self.paragraph('photodialogmessage',80,218,640,message,2,0)
        self.soft_button('photocancel',48,400,200,52,'Volver' if action=='trash_list' else 'Cancelar')
        if action=='trash_list':
            if item:
                self.soft_button('trashprev',48,312,152,48,'Anterior')
                self.soft_button('trashnext',600,312,152,48,'Siguiente')
                self.soft_button('trashrestore',268,400,220,52,'Restaurar',True)
                self.soft_button('trashpurge',508,400,244,52,'Borrar para siempre')
        elif action!='error': self.soft_button('photoconfirm',508,400,244,52,'Eliminar',True)

    def touch_photo_dialog(self,x,y):
        if not self.unlocked: return False
        action,item=self._photo_action
        if 12<=y<52 and 632<=x<768 or 400<=y<452 and 48<=x<248:
            self.navigate(self.screen); return True
        if action=='trash_list':
            if 312<=y<360 and (48<=x<200 or 600<=x<752):
                self._trash_index=max(0,getattr(self,'_trash_index',0)+(-1 if x<200 else 1))
                self.photo_dialog('trash_list'); return True
            item=getattr(self,'_trash_item',None)
            if not item: return True
            if 400<=y<452 and 268<=x<488:
                if self.photos.manage_photo('restore',item['token'],item['signature'],unlocked=True):
                    self.navigate('gallery_grid')
                else: self.photo_dialog('error')
            elif 400<=y<452 and 508<=x<752: self.photo_dialog('purge',item)
        elif action in ('trash','purge') and 400<=y<452 and 508<=x<752:
            name=item['name'] if action=='trash' else item['token']
            success=self.photos.manage_photo(action,name,item['signature'],unlocked=True)
            self.navigate('gallery_grid')
            if success: self.photo_dialog('trash_list')
            else: self.photo_dialog('error')
        return True

    def gallery_clear_preview(self):
        self.artwork.clear(); self.art_key=None
        self.fill(32,100,528,297,self.theme['card'])
        for key in ('galleryempty0','galleryempty1','galleryempty2','galleryloading'):
            self.cache.pop(key,None)

    def draw_gallery(self):
        if getattr(self,'_photo_action',None): self.draw_photo_dialog(); return
        c=self.theme; library=getattr(self,'photos',None)
        state=library.snapshot(unlocked=self.unlocked) if library else None
        count=state['count'] if state else 0
        index=state['index'] if count else -1
        title='Galería / '+str(index+1)+' de '+str(count) if count else 'Galería'
        self.text('gallerytitle',32,64,348,28,2,title,c['ink'],c['bg'])
        if count: self.soft_button('gallerydelete',400,58,160,38,'Eliminar',False,2)
        self.text('galleryeffects',584,64,184,28,2,'EFECTOS',c['muted'],c['bg'],1)
        selected=state['filter'] if state else 'Original'
        for i,label in enumerate(FILTERS):
            self.soft_button('galleryfilter'+str(i),584,100+i*42,184,36,label,label==selected,2)
        self.soft_button('galleryprev',32,410,104,50,'Anterior',False,2)
        self.soft_button('gallerynext',456,410,104,50,'Siguiente',False,2)
        self.soft_button('gallerysave',584,410,184,50,'Guardando...' if state and state['saving'] else 'Guardar copia',selected!='Original' and bool(count),2)
        filename=state['filename'] if state else ''
        message=state['status'] if state else 'Cámara no disponible'
        captured=getattr(self,'_capture_notice',None)
        if captured and captured[0]==filename and time.monotonic()<captured[1]: message='Foto guardada'
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
        if getattr(self,'_photo_action',None): return self.touch_photo_dialog(x,y)
        if 400<=x<560 and 58<=y<96:
            item=library.selected_revision(unlocked=True)
            if item: self.photo_dialog('trash',item)
            return True
        if 632<=x<768 and 12<=y<52:
            self.navigate('gallery_grid'); return True
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
