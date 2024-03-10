import asyncio
from .mixins import _LoopBoundMixin


class Queue(asyncio.Queue, _LoopBoundMixin):
    def _get_item(self, item):
        self._queue.remove(item)
        return item

    def _has_same_item(self, item):
        return item in list(self._queue)

    async def put_item(self, item):
        """
        Put an item into the queue.
        Put an item into the queue. If the queue is full, wait until a free
        slot is available before adding item.
        """
        while self.full() or self._has_same_item(item):
            putter = self._get_loop().create_future()
            self._putters.append(putter)
            try:
                await putter
            except:
                putter.cancel()  # Just in case putter is not done yet.
                try:
                    # Clean self._putters from canceled putters.
                    self._putters.remove(putter)
                except ValueError:
                    # The putter could be removed from self._putters by a
                    # previous get_nowait call.
                    pass
                if not self.full() and not putter.cancelled():
                    # We were woken up by get_nowait(), but can't take
                    # the call.  Wake up the next in line.
                    self._wakeup_next(self._putters)
                raise
        return self.put_nowait(item)

    async def get_item(self, item):
        """
        Remove and return an item from the queue.

        If queue is empty, wait until an item is available.
        """
        while self.empty():
            getter = self._get_loop().create_future()
            self._getters.append(getter)
            try:
                await getter
            except:
                getter.cancel()  # Just in case getter is not done yet.
                try:
                    # Clean self._getters from canceled getters.
                    self._getters.remove(getter)
                except ValueError:
                    # The getter could be removed from self._getters by a
                    # previous put_nowait call.
                    pass
                if not self.empty() and not getter.cancelled():
                    # We were woken up by put_nowait(), but can't take
                    # the call.  Wake up the next in line.
                    self._wakeup_next(self._getters)
                raise
        return self.get_item_nowait(item)

    def get_item_nowait(self, item):
        """
        Remove and return an item from the queue.

        Return an item if one is immediately available, else raise QueueEmpty.
        """
        if self.empty():
            raise QueueEmpty
        item = self._get_item(item)
        self._wakeup_next(self._putters)
        return item
