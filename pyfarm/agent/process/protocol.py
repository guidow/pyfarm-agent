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
Protocol
--------

The protocol implementation for a single process.
"""

from twisted.internet.protocol import ProcessProtocol
from twisted.internet.error import ProcessDone, ProcessTerminated


class WorkerProcess(ProcessProtocol):
    def __init__(self, config, deferred):
        #ProcessProtocol.__init__(self)
        self.config = config
        self.deferred = deferred

    def outReceived(self, data):
        print("Received output from process: %s" % data)

    def processEnded(self, status):
        if isinstance(status.value, ProcessDone):
            print("Process has finished successfully")
            self.deferred.callback(None)
        else:
            print("Process has terminated, return code: ", status.value.exitCode)
            self.deferred.errback(None)

class TestProto(ProcessProtocol):
    """
    Subclass of :class:`.Protocol` which hooks into the various systems
    necessary to run and manage a process.  More specifically, this helps
    to act as plumbing between the process being run and the job type.
    """
    def __init__(self, config):
        ProcessProtocol.__init__(self)
        self.config = config
        # TODO: pull in settings specific to the process
        # TODO: register a manager so we can send events up to a central class

    def connectionMade(self):
        # TODO: **below should all be handled by the jobtype**
        # TODO: post to the master (task no longer ALLOC)
        pass

    def processEnded(self, reason):
        # TODO: **below should all be handled by the jobtype**
        # TODO: post state change to master
        # TODO: shutdown logger(s) and optionally gzip any files on disk
        pass

    def outReceived(self, data):
        # TODO: **below should all be handled by the jobtype**
        # TODO: emit log message (logstash handler too?)
        # TODO: set the stream id using logger.LOGSTREAM
        pass

    def errReceived(self, data):
        if self.combined_output_streams:
            self.outReceived(data)
        else:
            # TODO: **below should all be handled by the jobtype**
            # TODO: emit log message (logstash handler too?)
            # TODO: set the stream id using logger.LOGSTREAM
            pass