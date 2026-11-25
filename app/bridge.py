import asyncio
from concurrent.futures import Future

from config import BOT_TIMEOUT


class LoopBridge:
    """Lets the Flask threads run code on the Discord client's event loop."""

    def __init__(self, client):
        self._client = client

    def run_async(self, coro, timeout=BOT_TIMEOUT):
        future = asyncio.run_coroutine_threadsafe(coro, self._client.loop)
        return future.result(timeout=timeout)

    def call(self, func, *args):
        """Runs a synchronous function on the bot's event loop thread."""
        future = Future()

        def runner():
            try:
                future.set_result(func(*args))
            except Exception as e:
                future.set_exception(e)

        self._client.loop.call_soon_threadsafe(runner)
        return future.result(timeout=BOT_TIMEOUT)
