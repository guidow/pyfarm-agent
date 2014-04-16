# No shebang line, this module is meant to be imported
#
# Copyright 2013 Oliver Palmer
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

"""
Manager
-------

Root class for spawning and management of new processes.
"""

from functools import partial

from twisted.python import log
from twisted.internet import reactor, defer

from pyfarm.agent.process.protocol import WorkerProcess


class TooManyProcesses(Exception):
    pass


class ProcessManager(object):
    processes = {}

    def __init__(self, config):
        self.config = config
        self.log = partial(log.msg, system=self.__class__.__name__)
        self.current_process = None
        self.current_batch = None

    def load_jobclass(self, load_type, load_from):
        # TODO: handle the other import_type cases after this is working
        # TODO: check class exists as attribute (add new error to pyfarm.core)
        # TODO: ensure class is subclassing the jobtype base class (error if not)
        raise NotImplementedError

    def process_running(self):
        return self.current_process is not None

    def spawn(self, assignment):
        self.log(
            "attempting to spawn process for "
            "job %(job)s task %(tasks)s" % assignment)

        if self.current_process:
            self.log("Error: Attempted to spawn a child process while one is "
                     "already running")
            raise TooManyProcesses("There is already a process running")

        deferred = defer.Deferred()
        deferred.addCallback(self.callback_process_ended)
        self.current_process = WorkerProcess(self.config, deferred)
        self.current_batch = assignment

        reactor.spawnProcess(self.current_process, '/bin/ls', ['ls'])
        """
        # attempt to load the jobtype class
        jobclass = self.load_jobclass(
            assignment["jobtype"]["load_type"],
            assignment["jobtype"]["load_from"])

        if jobclass is None:
            self.log("spawn failed for job %(job)s task %(task)s" % assignment)
            return
        """
        # TODO: instance jobclass with assignment data
        # TODO: instance the protocol object, pass in jobclass
        # TODO: use jobclass to construct arguments to reactor.spawnProcess
        # TODO: run reactor.spawnProcess (protocol will use jobclass to POST to /tasks/<id>)
        # TODO: store in self.processes

        return deferred

    def callback_process_ended(self, _):
        print("In callback_process_ended()")
        self.current_process = None
        self.current_batch = None

    def stop(self, assignment):
        # TODO: /basically/ the reverse of the above
        pass



