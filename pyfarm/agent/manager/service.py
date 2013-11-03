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
Manager Service
===============

Sends and receives information from the master and performs systems level tasks
such as log reading, system information gathering, and management of processes.
"""

from urlparse import urlparse

from zope.interface import implementer
from twisted.python import log, usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker

from pyfarm.agent.service import MultiService, Options as BaseOptions
from pyfarm.agent.manager.tasks import memory_utilization


class Options(BaseOptions):
    optParameters = [
        ("memory-check-interval", "", 10,
         "how often swap and ram resources should be checked and sent to the "
         "master"),
        ("http-auth-user", "u", None,
         "the user to use for connecting to the master's REST api"),
        ("http-auth-password", "v", None,
         "the password to use to connect to the master's REST api"),
        ("master-api", "m", None,
         "The url which points to the master's api, this value is required.  "
         "Examples: https://api.pyfarm.net or http://127.0.0.1:5000"),
        ("port", "p", None,
         "The port which the master should use to talk back to the agent.")]

#
#class IPCReceieverFactory(Factory):
#    """
#    Receives incoming connections and hands them off to the protocol
#    object.  In addition this class will also keep a list of all hosts
#    which have connected so they can be notified upon shutdown.
#    """
#    protocol = IPCProtocol
#    known_hosts = set()
#
#    def stopFactory(self):  # TODO: notify all connected hosts we are stopping
#        if self.known_hosts:
#            log.msg("notifying all known hosts of termination")


class ManagerService(MultiService):
    """the service object itself"""
    DEFAULT_PORT = 50000
    DEFAULT_IPC_PORT = 50001

    def __init__(self, options):
        MultiService.__init__(self, options)
        self.scheduled_tasks.register(
            memory_utilization, self.options.get("memory-check-interval"))

    def convert_option(self, key, value):
        if key == "memory-check-interval":
            return int(value)

        elif key == "master-api":
            if value is None:
                raise usage.UsageError("--%s must be set" % key)

            parsed_url = urlparse(value)
            if not parsed_url.scheme in ("http", "https"):
                raise usage.UsageError(
                    "scheme must be http or https for --%s" % key)

            return value

        return MultiService.convert_option(self, key, value)

    def startService(self):
        self.log("informing master new agent")
        MultiService.startService(self)



@implementer(IServiceMaker, IPlugin)
class ManagerServiceMaker(object):
    """
    Main service which which serves as the entry point into the internals
    of the agent.  This services runs an HTTP server for external interfacing
    and an IPC server based on protocol buffers for internal usage.
    """
    tapname = "pyfarm.agent.manager"
    description = __doc__
    options = Options

    def makeService(self, options):
        service = ManagerService(options)

        # ipc service setup
        #ipc_factory = IPCReceieverFactory()
        #ipc_server = internet.TCPServer(service.config.get("ipc-port"),
        #                                ipc_factory)
        #ipc_server.setServiceParent(service)

        return service
