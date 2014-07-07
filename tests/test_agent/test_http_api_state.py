# No shebang line, this module is meant to be imported
#
# Copyright 2014 Oliver Palmer
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
from json import loads
from datetime import datetime, timedelta

try:
    from httplib import ACCEPTED, OK, BAD_REQUEST
except ImportError:  # pragma: no cover
    from http.client import ACCEPTED, OK, BAD_REQUEST

import psutil
from twisted.web.server import NOT_DONE_YET

from pyfarm.core.enums import AgentState
from pyfarm.agent.config import config
from pyfarm.agent.http.api.state import Stop, Status
from pyfarm.agent.sysinfo import memory
from pyfarm.agent.testutil import BaseAPITestCase
from pyfarm.agent.utility import total_seconds


class TestStop(BaseAPITestCase):
    URI = "/stop"
    CLASS = Stop

    def test_invalid_type_for_data(self):
        request = self.post(data={"foo": 1})
        stop = Stop()
        result = stop.render(request)
        self.assertEqual(result, NOT_DONE_YET)
        self.assertIn(
            "Failed to validate the request data against the schema",
            request.response()["error"])
        self.assertEqual(request.code, BAD_REQUEST)
        self.assertTrue(request.finished)

    def test_stops_agent(self):
        request = self.post(data={})
        stop = Stop()
        result = stop.render(request)
        self.assertEqual(result, NOT_DONE_YET)
        self.assertEqual(request.code, ACCEPTED)
        self.assertTrue(request.finished)
        with self.assertRaises(ValueError):
            request.response()

        return self.agent.stopped

    def test_stops_and_waits_for_agent(self):
        request = self.post(data={"wait": True})
        stop = Stop()
        result = stop.render(request)
        self.assertEqual(result, NOT_DONE_YET)
        self.assertEqual(request.code, OK)
        self.assertTrue(request.finished)
        with self.assertRaises(ValueError):
            request.response()
        return self.agent.stopped


class TestStatus(BaseAPITestCase):
    URI = "/status"
    CLASS = Status

    def prepare_config(self):
        super(TestStatus, self).prepare_config()
        config.update(
            state=AgentState.ONLINE,
            pids=[1, 2, 3],
            start=time.time())

    def test_get_requires_no_input(self):
        request = self.get()
        status = Status()
        self.assertIsInstance(loads(status.render(request)), dict)

    def test_get_result(self):
        process = psutil.Process()
        direct_child_processes = len(process.children(recursive=False))
        all_child_processes = len(process.children(recursive=True))
        grandchild_processes = all_child_processes - direct_child_processes

        # Determine the last time we talked to the master (if ever)
        contacted = config.master_contacted(update=False)
        if isinstance(contacted, datetime):
            contacted = datetime.utcnow() - contacted

        # Determine the last time we announced ourselves to the
        # master (if ever)
        last_announce = config.get("last_announce", None)
        if isinstance(last_announce, datetime):
            last_announce = datetime.utcnow() - last_announce

        expected_data = {
            "state": config["state"],
            "agent_hostname": config["agent_hostname"],
            "agent_process_ram": int(memory.process_memory()),
            "consumed_ram": int(memory.total_consumption()),
            "child_processes": direct_child_processes,
            "grandchild_processes": grandchild_processes,
            "pids": config["pids"],
            "id": config.get("agent-id", None),
            "agent_systemid": config["agent_systemid"],
            "last_master_contact": contacted,
            "last_announce": last_announce,
            "agent_lock_file": config["agent_lock_file"],
            "uptime": total_seconds(
                timedelta(seconds=time.time() - config["start"])),
            "jobs": list(config["jobtypes"].keys())}

        request = self.get()
        status = Status()
        data = loads(status.render(request))

        # Pop off and test keys which are 'close'
        self.assertApproximates(
            data.pop("uptime"), expected_data.pop("uptime"), .5)
        self.assertApproximates(
            data.pop("free_ram"), int(memory.ram_free()), 25)

        self.assertEqual(data, expected_data)