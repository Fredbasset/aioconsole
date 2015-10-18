"""Provide an asynchronous equivalent to the python console."""

import sys
import signal
import asyncio
from codeop import CommandCompiler
from code import InteractiveConsole

from . import input
from . import execute


class AsynchronousCompiler(CommandCompiler):

    def __init__(self):
        self.compiler = execute.compile_for_aexec


class AsynchronousConsole(InteractiveConsole):

    def __init__(self, locals=None, filename="<console>", *, loop=None):
        super().__init__(locals, filename)
        self.compile = AsynchronousCompiler()
        if loop is None:
            loop = asyncio.get_event_loop()
        self.loop = loop
        self.locals.setdefault('asyncio', asyncio)
        self.locals.setdefault('loop', self.loop)

    @asyncio.coroutine
    def runsource(self, source, filename="<ainput>", symbol="single"):
        try:
            code = self.compile(source, filename, symbol)
        except (OverflowError, SyntaxError, ValueError):
            self.showsyntaxerror(filename)
            return False

        if code is None:
            return True

        yield from self.runcode(code)
        return False

    @asyncio.coroutine
    def runcode(self, code):
        try:
            yield from execute.aexec(code, self.locals)
        except SystemExit:
            raise
        except:
            self.showtraceback()
        else:
            yield

    def resetbuffer(self):
        self.buffer = []

    @asyncio.coroutine
    def interact(self, banner=None, stop=True):
        task = asyncio.Task.current_task(loop=self.loop)

        def handle_keyboard_interrupt(signal, frame):
            self.loop.call_soon_threadsafe(task.cancel)
            if task._fut_waiter._loop is not self.loop:
                self.loop.call_soon_threadsafe(task._wakeup, task._fut_waiter)
        try:
            signal.signal(signal.SIGINT, handle_keyboard_interrupt)
            yield from self._interact(banner)
        finally:
            def callback(signal, frame):
                raise KeyboardInterrupt
            signal.signal(signal.SIGINT, callback)
            if stop:
                self.loop.stop()

    @asyncio.coroutine
    def _interact(self, banner=None):
        # Get ps1 and ps2
        try:
            sys.ps1
        except AttributeError:
            sys.ps1 = ">>> "
        try:
            sys.ps2
        except AttributeError:
            sys.ps2 = "... "
        # Print banner
        cprt = ('Type "help", "copyright", "credits" '
                'or "license" for more information.')
        if banner is None:
            msg = "Python %s on %s\n%s\n%s\n"
            extra = """\
---
This interpreter is running in an asyncio event loop.
It allows you to wait for coroutines using the 'yield from' syntax.
Try: yield from asyncio.sleep(1, result=3, loop=loop)
---"""
            self.write(msg % (sys.version, sys.platform, cprt, extra))
        elif banner:
            self.write("%s\n" % str(banner))
        # Run loop
        more = 0
        while 1:
            try:
                if more:
                    prompt = sys.ps2
                else:
                    prompt = sys.ps1
                try:
                    line = yield from self.raw_input(prompt)
                except EOFError:
                    self.write("\n")
                    break
                else:
                    more = yield from self.push(line)
            except asyncio.CancelledError:
                self.write("\nKeyboardInterrupt\n")
                self.resetbuffer()
                more = 0

    @asyncio.coroutine
    def push(self, line):
        self.buffer.append(line)
        source = "\n".join(self.buffer)
        more = yield from self.runsource(source, self.filename)
        if not more:
            self.resetbuffer()
        return more

    @asyncio.coroutine
    def raw_input(self, prompt=""):
        return (yield from input.ainput(prompt, loop=self.loop))


@asyncio.coroutine
def interact(banner=None, local=None, stop=True, *, loop=None):
    console = AsynchronousConsole(local, loop=loop)
    yield from console.interact(banner, stop)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(interact())