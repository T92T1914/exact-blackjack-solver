"""Owned worker and pipe cleanup using inert process substitutes."""
import unittest
from unittest.mock import patch

from tools import compare_joint_split as study


class Connection:
    def __init__(self, events, name):
        self.events = events
        self.name = name
        self.closed = False
        self.close_error = None
        self.poll_error = None
        self.finished = None
        self.process = None

    def close(self):
        self.events.append(self.name + '.close')
        error, self.close_error = self.close_error, None
        if error is not None:
            raise error
        self.closed = True

    def poll(self, timeout):
        self.events.append(self.name + '.poll')
        if self.poll_error is not None:
            raise self.poll_error
        return self.finished is not None

    def recv(self):
        self.process.alive = False
        self.process.code = 0
        return dict(self.finished)


class Process:
    def __init__(self, events):
        self.events = events
        self.pid = None
        self.alive = False
        self.closed = False
        self.code = None
        self.before_start_error = None
        self.after_start_error = None
        self.join_error = None

    @property
    def exitcode(self):
        if self.closed:
            raise ValueError('closed process')
        return self.code

    def start(self):
        self.events.append('process.start')
        if self.before_start_error is not None:
            raise self.before_start_error
        self.pid = 1234
        self.alive = True
        if self.after_start_error is not None:
            raise self.after_start_error

    def join(self, timeout):
        if self.pid is None:
            raise AssertionError('joined an unstarted process')
        self.events.append(('process.join', timeout))
        error, self.join_error = self.join_error, None
        if error is not None:
            raise error

    def is_alive(self):
        self.events.append('process.is_alive')
        return self.alive

    def terminate(self):
        if self.pid is None:
            raise AssertionError('terminated an unstarted process')
        self.events.append('process.terminate')
        self.alive = False
        self.code = -1

    def close(self):
        self.events.append('process.close')
        if self.alive:
            raise ValueError('cannot close a running process')
        self.closed = True


class Context:
    def __init__(self):
        self.events = []
        self.receiver = Connection(self.events, 'receiver')
        self.sender = Connection(self.events, 'sender')
        self.process = Process(self.events)
        self.receiver.process = self.process
        self.constructor_error = None

    def Pipe(self, duplex):
        assert duplex is False
        return self.receiver, self.sender

    def Process(self, target, args):
        self.events.append('process.construct')
        assert target is study._worker and args[0] is self.sender
        if self.constructor_error is not None:
            raise self.constructor_error
        return self.process


class StartupCleanupTests(unittest.TestCase):
    def invoke(self, context, wall_seconds=0):
        with patch.object(study.mp, 'get_context', return_value=context):
            return study.run_case({'id': 'inert-case'}, {
                'limits': {'case_wall_seconds': wall_seconds}})

    def assert_handles_retired(self, context):
        self.assertTrue(context.receiver.closed)
        self.assertTrue(context.sender.closed)
        self.assertTrue(context.process.closed)
        self.assertFalse(context.process.alive)

    def test_constructor_failure_closes_both_pipes_without_touching_process(self):
        context = Context()
        failure = OSError('constructor failed')
        context.constructor_error = failure
        with self.assertRaises(OSError) as caught:
            self.invoke(context)
        self.assertIs(caught.exception, failure)
        self.assertTrue(context.receiver.closed)
        self.assertTrue(context.sender.closed)
        self.assertEqual(context.events, [
            'process.construct', 'sender.close', 'receiver.close'])

    def test_start_failure_closes_pipes_without_joining_or_terminating(self):
        for kind in (OSError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                context = Context()
                failure = kind('start failed before launch')
                context.process.before_start_error = failure
                with self.assertRaises(kind) as caught:
                    self.invoke(context)
                self.assertIs(caught.exception, failure)
                self.assert_handles_retired(context)
                self.assertNotIn('process.terminate', context.events)
                self.assertFalse(any(isinstance(event, tuple) for event in context.events))

    def test_start_error_after_visible_launch_retires_the_owned_child(self):
        context = Context()
        failure = KeyboardInterrupt('start completed before interruption')
        context.process.after_start_error = failure
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.invoke(context)
        self.assertIs(caught.exception, failure)
        self.assert_handles_retired(context)
        self.assertIn('process.terminate', context.events)
        self.assertIn(('process.join', 0.5), context.events)
        self.assertIn(('process.join', 2), context.events)

    def test_sender_close_interruption_retires_child_and_closes_both_pipes(self):
        for kind in (OSError, KeyboardInterrupt, SystemExit):
            with self.subTest(kind=kind.__name__):
                context = Context()
                failure = kind('sender close interrupted')
                context.sender.close_error = failure
                with self.assertRaises(kind) as caught:
                    self.invoke(context)
                self.assertIs(caught.exception, failure)
                self.assert_handles_retired(context)
                self.assertEqual(context.events.count('sender.close'), 2)
                self.assertIn('process.terminate', context.events)

    def test_poll_interruption_retires_child(self):
        context = Context()
        failure = KeyboardInterrupt('receive interrupted')
        context.receiver.poll_error = failure
        with self.assertRaises(KeyboardInterrupt) as caught:
            self.invoke(context, wall_seconds=1)
        self.assertIs(caught.exception, failure)
        self.assert_handles_retired(context)

    def test_cleanup_error_does_not_replace_the_original_start_error(self):
        context = Context()
        failure = SystemExit('start completed before interruption')
        context.process.after_start_error = failure
        context.process.join_error = OSError('first join failed')
        with self.assertRaises(SystemExit) as caught:
            self.invoke(context)
        self.assertIs(caught.exception, failure)
        self.assert_handles_retired(context)
        self.assertIn('OSError', failure.__notes__[0])

    def test_failed_cleanup_note_does_not_replace_the_original_error(self):
        class NoNote(SystemExit):
            def add_note(self, note):
                raise KeyboardInterrupt('note failed')

        context = Context()
        failure = NoNote('original stop')
        context.process.after_start_error = failure
        context.process.join_error = OSError('first join failed')
        with self.assertRaises(NoNote) as caught:
            self.invoke(context)
        self.assertIs(caught.exception, failure)
        self.assert_handles_retired(context)

    def test_cleanup_failure_on_success_propagates_after_other_handles_close(self):
        context = Context()
        context.receiver.finished = {'stage': 'finished', 'status': 'completed'}
        failure = OSError('receiver close failed')
        context.receiver.close_error = failure
        with self.assertRaises(OSError) as caught:
            self.invoke(context, wall_seconds=1)
        self.assertIs(caught.exception, failure)
        self.assertTrue(context.process.closed)
        self.assertFalse(context.process.alive)
        self.assertTrue(context.sender.closed)
        self.assertFalse(context.receiver.closed)

    def test_completed_result_keeps_exit_code_before_process_handle_close(self):
        context = Context()
        context.receiver.finished = {'stage': 'finished', 'status': 'completed',
                                     'reference': {'value': -0.125, 'states': 4}}
        result = self.invoke(context, wall_seconds=1)
        self.assert_handles_retired(context)
        self.assertEqual(result['id'], 'inert-case')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['worker_exit_code'], 0)
        self.assertEqual(result['reference'], {'value': -0.125, 'states': 4})

    def test_timeout_still_retires_child_and_preserves_the_timeout(self):
        context = Context()
        result = self.invoke(context)
        self.assert_handles_retired(context)
        self.assertEqual(result['status'], 'timed_out')
        self.assertEqual(result['worker_exit_code'], -1)
        self.assertNotIn('reference', result)
