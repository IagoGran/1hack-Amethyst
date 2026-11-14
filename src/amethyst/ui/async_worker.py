"""Async loop ownership and cleanup for the persistent desktop worker."""

import asyncio

from PySide6.QtCore import QThread


class AsyncThread(QThread):
    """Own and clean up an asyncio loop on the worker thread."""

    loop: asyncio.AbstractEventLoop | None = None

    def _open_loop(self) -> asyncio.AbstractEventLoop:
        """Create the asyncio loop on the thread that will execute its work.

        Parameters
        ----------
        None

        Returns
        -------
        asyncio.AbstractEventLoop
            Newly installed worker-local loop.
        """
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        return self.loop

    def _close_loop(self) -> None:
        """Cancel pending work and drain generators and executor before closing.

        Parameters
        ----------
        None

        Returns
        -------
        None
        """
        assert self.loop is not None
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.run_until_complete(self.loop.shutdown_asyncgens())
        self.loop.run_until_complete(self.loop.shutdown_default_executor())
        self.loop.close()
