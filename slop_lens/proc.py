"""Child processes (Node probes) that are safe to start from a long-running MCP stdio server.

- stdin is never inherited: the server's stdin is the JSON-RPC stream.
- a cancelled or timed-out call takes its whole process tree (Node + browser) with it.
"""
import os
import signal
import subprocess
import threading
import time

_local = threading.local()


class Cancelled(BaseException):
    """The client cancelled the request. BaseException, so the 'one failure must not break the scan' handlers let it through."""


def set_cancel_event(event):
    """Bind a threading.Event to the work of the current thread; None unbinds."""
    _local.event = event


def check_cancelled():
    ev = getattr(_local, "event", None)
    if ev is not None and ev.is_set():
        raise Cancelled()


def kill_tree(p):
    if p.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=15)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    if p.poll() is None:
        p.kill()


def run(cmd, timeout, cwd=None):
    """subprocess.run(capture_output=True) with the guarantees above. Raises TimeoutExpired or Cancelled."""
    check_cancelled()
    p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         start_new_session=os.name != "nt")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                out, err = p.communicate(timeout=0.5)
                return subprocess.CompletedProcess(cmd, p.returncode, out, err)
            except subprocess.TimeoutExpired:
                check_cancelled()
                if time.monotonic() > deadline:
                    raise subprocess.TimeoutExpired(cmd, timeout)
    except BaseException:
        kill_tree(p)
        try:
            p.communicate(timeout=5)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        raise
