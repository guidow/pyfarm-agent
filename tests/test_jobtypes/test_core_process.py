# No shebang line, this module is meant to be imported
#
# Copyright 2014 Oliver Palmer
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from collections import namedtuple

import psutil
from twisted.internet import reactor
from twisted.internet.defer import Deferred, DeferredList
from twisted.internet.protocol import ProcessProtocol as _ProcessProtocol

from pyfarm.agent.testutil import TestCase
from pyfarm.jobtypes.core.process import ReplaceEnvironment, ProcessProtocol

DummyInputs = namedtuple("DummyInputs", ("task", ))


class FakeJobType(object):
    def __init__(self, stdout=None, stderr=None):
        self.started = Deferred()
        self.stopped = Deferred()
        self.stdout = stdout
        self.stderr = stderr

    def process_started(self, protocol):
        self.started.callback(protocol)

    def process_stopped(self, protocol, reason):
        self.stopped.callback((protocol, reason))

    def received_stdout(self, protocol, data):
        if self.stdout is not None:
            self.stdout(protocol, data)

    def received_stderr(self, protocol, data):
        if self.stderr is not None:
            self.stderr(protocol, data)


class TestProtocol(TestCase):
    def _launch_python(self, jobtype, script="i = 42"):
        protocol = ProcessProtocol(jobtype, *[None] * 6)
        reactor.spawnProcess(
            protocol, "python", ["python", "-c", script])
        return protocol

    def test_subclass(self):
        protocol = ProcessProtocol(*[None] * 7)
        self.assertIsInstance(protocol, _ProcessProtocol)

    def test_pid(self):
        fake_jobtype = FakeJobType()
        protocol = self._launch_python(fake_jobtype)
        self.assertEqual(protocol.pid, protocol.transport.pid)
        return fake_jobtype.stopped

    def test_process(self):
        fake_jobtype = FakeJobType()
        protocol = self._launch_python(fake_jobtype)
        self.assertIs(protocol.process, protocol.transport)
        return fake_jobtype.stopped

    def test_psutil_process_after_exit(self):
        fake_jobtype = FakeJobType()
        protocol = self._launch_python(fake_jobtype)

        def exited(*_):
            self.assertIsNone(protocol.psutil_process)

        fake_jobtype.stopped.addCallback(exited)
        return fake_jobtype.stopped

    def test_psutil_process_running(self):
        fake_jobtype = FakeJobType()
        protocol = self._launch_python(fake_jobtype)
        self.assertIsInstance(protocol.psutil_process, psutil.Process)
        self.assertEqual(protocol.psutil_process.pid, protocol.pid)
        return fake_jobtype.stopped

    def test_connectionMade(self):
        fake_jobtype = FakeJobType()

        def stopped(*_):
            self.assertTrue(fake_jobtype.started.called)

        fake_jobtype.started.addCallback(
            lambda value: self.assertIsInstance(value, ProcessProtocol))
        fake_jobtype.stopped.addCallback(stopped)
        self._launch_python(fake_jobtype)
        return fake_jobtype.stopped

    def test_processEnded(self):
        fake_jobtype = FakeJobType()

        def stopped(*_):
            self.assertTrue(fake_jobtype.stopped.called)

        fake_jobtype.stopped.addCallback(
            lambda data: self.assertIsInstance(data[0], ProcessProtocol))
        fake_jobtype.stopped.addCallback(stopped)
        self._launch_python(fake_jobtype)
        return fake_jobtype.stopped

    def test_outReceived(self):
        finished = Deferred()
        rand_str = os.urandom(24).encode("hex")

        def check_stdout(protocol, data):
            self.assertIsInstance(protocol, ProcessProtocol)
            self.assertEqual(data.strip(), rand_str)
            finished.callback(None)

        fake_jobtype = FakeJobType(stdout=check_stdout)
        self._launch_python(
            fake_jobtype,
            "import sys; print >> sys.stdout, %r" % rand_str)
        return DeferredList([finished, fake_jobtype.stopped])

    def test_errReceived(self):
        finished = Deferred()
        rand_str = os.urandom(24).encode("hex")

        def check_stdout(protocol, data):
            self.assertIsInstance(protocol, ProcessProtocol)
            self.assertEqual(data.strip(), rand_str)
            finished.callback(None)

        fake_jobtype = FakeJobType(stderr=check_stdout)
        self._launch_python(
            fake_jobtype,
            "import sys; print >> sys.stderr, %r" % rand_str)
        return DeferredList([finished, fake_jobtype.stopped])


class TestReplaceEnvironment(TestCase):
    original_environment = os.environ.copy()

    def tearDown(self):
        super(TestReplaceEnvironment, self).tearDown()
        os.environ.clear()
        os.environ.update(self.original_environment)

    def test_uses_os_environ(self):
        os.environ.clear()
        os.environ.update(
            {os.urandom(16).encode("hex"): os.urandom(16).encode("hex")})
        env = ReplaceEnvironment(None)
        self.assertEqual(env.environment, os.environ)
        self.assertIs(env.environment, os.environ)

    def test_enter(self):
        original = {os.urandom(16).encode("hex"): os.urandom(16).encode("hex")}
        frozen = {os.urandom(16).encode("hex"): os.urandom(16).encode("hex")}
        os.environ.clear()
        os.environ.update(original)

        with ReplaceEnvironment(frozen, os.environ) as env:
            self.assertEqual(env.original_environment, original)
            self.assertEqual(os.environ, frozen)

    def test_exit(self):
        original = {os.urandom(16).encode("hex"): os.urandom(16).encode("hex")}
        original_copy = original.copy()
        frozen = {os.urandom(16).encode("hex"): os.urandom(16).encode("hex")}
        os.environ.clear()
        os.environ.update(original)

        with ReplaceEnvironment(frozen, os.environ) as env:
            pass

        self.assertEqual(os.environ, original_copy)
