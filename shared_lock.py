"""Reentrant thread + OS file lock, also used by clients sharing one data directory."""
import os
import threading
import time

class SharedLock:
    def __init__(self,path):
        self.path=path;self.thread_lock=threading.RLock();self.local=threading.local()
    def __enter__(self):
        self.thread_lock.acquire()
        if getattr(self.local,'depth',0): self.local.depth+=1;return self
        handle=None
        try:
            handle=open(self.path,'a+b')
            if os.fstat(handle.fileno()).st_size==0: handle.write(b'0');handle.flush()
            deadline=time.monotonic()+10
            while True:
                try:
                    handle.seek(0)
                    if os.name=='nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    else:
                        import fcntl
                        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic()>=deadline: raise OSError('Shared workspace is busy')
                    time.sleep(.05)
            self.local.handle=handle;self.local.depth=1;return self
        except BaseException:
            if handle: handle.close()
            self.thread_lock.release();raise
    def __exit__(self,*args):
        self.local.depth-=1
        if not self.local.depth:
            handle=self.local.handle
            try:
                handle.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(handle,fcntl.LOCK_UN)
            finally: handle.close();self.thread_lock.release()
        else: self.thread_lock.release()
