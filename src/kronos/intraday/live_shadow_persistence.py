"""WO-06H atomic append-only research namespace; no production current pointers."""
import os
import json
from pathlib import Path
from threading import RLock
from uuid import uuid4
from kronos.intraday.live_shadow import Artifact, ShadowError, KINDS, KEY


class ShadowStore:
    def __init__(self, root:Path):
        if type(root) is not type(Path()) or not root.is_absolute() or root==Path('/'):
            raise ShadowError('SHADOW_ROOT_INVALID')
        self.root=root/'live-shadow-v1';self.lock=RLock()

    def _directory(self,kind,create=False):
        if kind not in KINDS:raise ShadowError('SHADOW_KIND_INVALID')
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        try:
            for part in (*self.root.parts[1:],kind):
                if part in {'.','..',''}:raise ShadowError('SHADOW_PATH_INVALID')
                try:new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                except FileNotFoundError:
                    if not create:os.close(fd);return None
                    try:os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError:pass
                    new=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=new
            return fd
        except Exception:
            os.close(fd);raise ShadowError('SHADOW_PATH_UNSAFE_OR_UNAVAILABLE') from None

    def _read(self,fd,kind,identifier):
        if not KEY.fullmatch(identifier) or not identifier.startswith('WO06H-'+kind.upper()+'-'):
            raise ShadowError('SHADOW_KEY_INVALID')
        try:f=os.open(identifier+'.json',os.O_RDONLY|os.O_NOFOLLOW,dir_fd=fd)
        except FileNotFoundError:return None
        try:
            with os.fdopen(f,'rb') as stream:data=stream.read(8_000_001)
            if len(data)>8_000_000:raise ShadowError('SHADOW_RECORD_TOO_LARGE')
            return Artifact(kind,identifier,data)
        except Exception:raise ShadowError('SHADOW_RECORD_INVALID') from None

    def load(self,kind,identifier):
        if not KEY.fullmatch(identifier):raise ShadowError('SHADOW_KEY_INVALID')
        fd=self._directory(kind)
        if fd is None:return None
        try:return self._read(fd,kind,identifier)
        finally:os.close(fd)

    def all(self,kind):
        fd=self._directory(kind)
        if fd is None:return ()
        try:
            names=sorted(os.listdir(fd));result=[]
            for name in names:
                if name.startswith('.') and name.endswith('.tmp'):continue
                if not name.endswith('.json'):raise ShadowError('SHADOW_UNEXPECTED_FILE')
                result.append(self._read(fd,kind,name[:-5]))
            if any(x is None for x in result):raise ShadowError('SHADOW_READ_RACE')
            return tuple(result)
        finally:os.close(fd)

    def retain(self,value:Artifact,*,claim=False):
        Artifact(value.kind,value.key,value.payload)
        with self.lock:
            fd=self._directory(value.kind,True);temporary='.'+uuid4().hex+'.tmp'
            try:
                old=self._read(fd,value.kind,value.key)
                if old is not None:
                    if claim and value.kind=='intent':
                        stable=('window','run','result','cohort','observation')
                        if any(old.body[k]!=value.body[k] for k in stable):raise ShadowError('SHADOW_IMMUTABLE_CONFLICT')
                        return False
                    if old.payload!=value.payload:raise ShadowError('SHADOW_IMMUTABLE_CONFLICT')
                    return False
                f=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
                with os.fdopen(f,'wb') as stream:stream.write(value.payload);stream.flush();os.fsync(stream.fileno())
                try:os.link(temporary,value.key+'.json',src_dir_fd=fd,dst_dir_fd=fd,follow_symlinks=False)
                except FileExistsError:
                    old=self._read(fd,value.kind,value.key)
                    if claim and value.kind=='intent' and all(old.body[k]==value.body[k] for k in ('window','run','result','cohort','observation')):return False
                    if old.payload!=value.payload:raise ShadowError('SHADOW_IMMUTABLE_CONFLICT')
                    return False
                os.fsync(fd);return True
            finally:
                try:os.unlink(temporary,dir_fd=fd)
                except FileNotFoundError:pass
                os.close(fd)
