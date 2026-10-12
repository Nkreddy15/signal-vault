"""One bounded asynchronous native-feed check; never edits the execution ledger."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from .binance_public import BinancePublic


class VenueProbe:
    def __init__(self,check=None,clock=time.time):
        self.check=check or BinancePublic().preflight;self.clock=clock;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='native-feed-probe');self.lock=threading.Lock();self.future=None;self.result=None;self.checked=0
    def state(self):
        with self.lock:
            if self.future is not None and self.future.done():
                try:self.result=dict(state='READY',**self.future.result())
                except Exception as e:self.result=dict(state='UNAVAILABLE',venue='Binance.US',mode='READ_ONLY_PUBLIC_PREFLIGHT',reason=str(e) if isinstance(e,RuntimeError) else type(e).__name__,orders_submitted=0)
                self.checked=self.clock();self.future=None
            if self.future is None and (self.result is None or self.clock()-self.checked>=300):self.future=self.pool.submit(self.check)
            return dict(self.result or {},state='CHECKING' if self.future is not None else self.result['state'],checked_at=self.checked or None,orders_submitted=0)
    def close(self):self.pool.shutdown(wait=False,cancel_futures=True)
