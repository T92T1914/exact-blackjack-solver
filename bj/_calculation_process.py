"""Own one fixed calculation worker and its bounded transport.

Windows contains the worker in a kill-on-close Job before sending its input.
Linux owns one direct worker in a fresh session. That fixed worker does not
create descendants. Linux memory is explicitly uncapped in this interface.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time

MAX_STREAM_BYTES = 65536
CLEANUP_SECONDS = 5.0


class _WindowsJob:
    def __init__(self, memory_bytes):
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('minimum_ws', ctypes.c_size_t),
                        ('maximum_ws', ctypes.c_size_t), ('active_limit', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                        ('scheduling', wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ('read_ops', 'write_ops', 'other_ops', 'read_bytes',
                         'write_bytes', 'other_bytes')]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [('basic', BasicLimits), ('io', IoCounters),
                        ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                        ('peak_process_memory', ctypes.c_size_t),
                        ('peak_job_memory', ctypes.c_size_t)]

        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in
                        ('user_time', 'kernel_time', 'period_user', 'period_kernel')]
            _fields_ += [(name, wintypes.DWORD) for name in
                         ('page_faults', 'total_processes', 'active_processes', 'terminated')]

        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                        ctypes.c_void_p, wintypes.DWORD]
        self.kernel.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                          ctypes.c_void_p, wintypes.DWORD,
                                                          ctypes.c_void_p]
        self.kernel.QueryInformationJobObject.restype = wintypes.BOOL
        self.kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.TerminateJobObject.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.accounting = Accounting
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = ExtendedLimits()
            # KILL_ON_JOB_CLOSE | JOB_MEMORY | DIE_ON_UNHANDLED_EXCEPTION.
            # Suppress fault dialogs only for associated owned processes.
            limits.basic.flags = 0x2000 | 0x200 | 0x400
            limits.job_memory = memory_bytes
            if not self.kernel.SetInformationJobObject(
                    self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            observed = ExtendedLimits()
            if not self.kernel.QueryInformationJobObject(
                    self.handle, 9, ctypes.byref(observed), ctypes.sizeof(observed), None):
                raise ctypes.WinError(ctypes.get_last_error())
            if (observed.job_memory != memory_bytes
                    or observed.basic.flags & 0x2600 != 0x2600):
                raise OSError('Windows Job did not retain the requested memory/ownership limits')
        except BaseException:
            self.close()
            raise

    def assign(self, process):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def empty(self):
        counters = self.accounting()
        if not self.kernel.QueryInformationJobObject(
                self.handle, 1, ctypes.byref(counters), ctypes.sizeof(counters), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.active_processes == 0

    def terminate(self):
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())


def execute(payload, policy, directory, cancellation):
    """Return captured bytes and retirement observations, never a decision claim."""
    process = job = None
    job_assigned = False
    threads = []
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}
    transport_errors = []
    overflow = threading.Event()
    status, error = 'worker_failed', None
    started = time.monotonic()
    deadline = started + policy['wall_seconds']
    cleanup_errors = []

    def problem(exc):
        return f'{type(exc).__name__}: {str(exc)[:512]}'

    def read(stream, name):
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                room = MAX_STREAM_BYTES - len(buffers[name])
                buffers[name].extend(chunk[:room])
                if len(chunk) > room:
                    overflow.set()
                    return
        except (OSError, ValueError) as exc:
            transport_errors.append(problem(exc))

    def send(stream):
        try:
            view = memoryview(payload)
            while view:
                written = stream.write(view)
                if written is None or written <= 0:
                    raise OSError('incomplete worker input write')
                view = view[written:]
            stream.flush()
        except (OSError, ValueError) as exc:
            transport_errors.append(problem(exc))
        finally:
            try:
                stream.close()
            except (OSError, ValueError) as exc:
                transport_errors.append(problem(exc))

    try:
        if cancellation.is_set():
            status = 'cancelled'
        else:
            if policy['memory']['mode'] == 'windows_job_commit':
                try:
                    job = _WindowsJob(policy['memory']['bytes'])
                except (OSError, AttributeError) as exc:
                    status = 'unsupported_policy'
                    raise RuntimeError('cannot establish Windows Job policy') from exc
            env = {key: value for key, value in os.environ.items()
                   if key.upper() not in ('PYTHONPATH', 'PYTHONHOME')}
            env['PYTHONNOUSERSITE'] = '1'
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            options = {'creationflags': 0x08000000 | 0x200} if os.name == 'nt' else {
                'start_new_session': True}
            process = subprocess.Popen(
                [sys.executable, '-I', '-B', '-m', 'bj._calculation_worker'],
                cwd=directory, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, bufsize=0, **options)
            if job is not None:
                try:
                    job.assign(process)
                    job_assigned = True
                except OSError as exc:
                    status = 'unsupported_policy'
                    raise RuntimeError('worker was not admitted to the Windows Job') from exc
            # The fixed child waits for stdin before importing pricing code.
            # No captured input is sent until containment has been established.
            if cancellation.is_set():
                status = 'cancelled'
                raise RuntimeError('cancelled before releasing the worker input gate')
            if time.monotonic() >= deadline:
                status = 'timed_out'
                raise RuntimeError('deadline reached before releasing the worker input gate')
            for target, args in ((read, (process.stdout, 'stdout')),
                                 (read, (process.stderr, 'stderr')),
                                 (send, (process.stdin,))):
                thread = threading.Thread(target=target, args=args, daemon=True)
                threads.append(thread)
                thread.start()
            while True:
                if cancellation.is_set():
                    status = 'cancelled'
                    break
                if time.monotonic() >= deadline:
                    status = 'timed_out'
                    break
                if overflow.is_set():
                    status, error = 'resource_limited', 'worker transport exceeded 65536 bytes'
                    break
                if transport_errors:
                    error = transport_errors[0]
                    break
                if (process.poll() is not None and all(not t.is_alive() for t in threads)
                        and (job is None or job.empty())):
                    status = 'returned'
                    break
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    except (OSError, RuntimeError, ValueError) as exc:
        error = problem(exc)
    finally:
        cleanup_deadline = time.monotonic() + CLEANUP_SECONDS

        def remaining():
            return max(0.0, cleanup_deadline - time.monotonic())

        def clean(action):
            try:
                action()
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                cleanup_errors.append(problem(exc))

        if process is not None:
            if job_assigned and status != 'returned':
                clean(job.terminate)
            if process.poll() is None:
                clean(process.terminate)
                try:
                    process.wait(timeout=min(0.5, remaining()))
                except subprocess.TimeoutExpired:
                    pass  # Ordinary escalation to kill is not itself a cleanup failure.
                except (OSError, RuntimeError, ValueError) as exc:
                    cleanup_errors.append(problem(exc))
                if process.poll() is None:
                    clean(process.kill)
            clean(lambda: process.wait(timeout=remaining()))
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=remaining())
        job_empty = None
        if job_assigned:
            try:
                while not job.empty() and remaining() > 0:
                    time.sleep(min(0.01, remaining()))
                job_empty = job.empty()
            except OSError as exc:
                cleanup_errors.append(problem(exc))
                job_empty = False
        readers_retired = all(not thread.is_alive() for thread in threads)
        worker_retired = process is None or process.poll() is not None
        # Closing a stream with an active reader can itself block. Leave that
        # explicitly unresolved rather than hiding it behind an unbounded close.
        if readers_retired and process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                clean(stream.close)
        if job is not None:
            clean(job.close)
        if worker_retired and process is not None and os.name == 'nt':
            clean(process._handle.Close)
    retired = worker_retired and readers_retired and job_empty is not False
    return {'status': status, 'error': error,
            'stdout': bytes(buffers['stdout']), 'stderr': bytes(buffers['stderr']),
            'worker': {'pid': process.pid if process is not None else None,
                       'returncode': process.returncode if process is not None else None},
            'policy_established': (job_assigned
                                   if policy['memory']['mode'] == 'windows_job_commit'
                                   else process is not None),
            'cleanup': {'retired': retired, 'worker_retired': worker_retired,
                        'transport_retired': readers_retired, 'job_empty': job_empty,
                        'errors': cleanup_errors},
            'elapsed_seconds': time.monotonic() - started}
