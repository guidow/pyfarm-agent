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

import uuid
from json import dumps

try:
    from httplib import (
        OK, BAD_REQUEST, NO_CONTENT, INTERNAL_SERVER_ERROR, ACCEPTED)
except ImportError:  # pragma: no cover
    from http.client import (
        OK, BAD_REQUEST, NO_CONTENT, INTERNAL_SERVER_ERROR, ACCEPTED)

from twisted.internet.defer import Deferred

from pyfarm.agent.config import config
from pyfarm.agent.testutil import BaseAPITestCase
from pyfarm.agent.http.api.tasks import Tasks


class TestTasks(BaseAPITestCase):
    URI = "/tasks/"
    CLASS = Tasks
    POP_CONFIG_KEYS = ["current_assignments", "jobtypes"]

    def test_master_contacted(self):
        try:
            last_master_contact = config["last_master_contact"]
        except KeyError:
            last_master_contact = None

        request = self.get(headers={"User-Agent": config["master_user_agent"]})
        tasks = Tasks()
        tasks.render(request)
        self.assertNotEqual(last_master_contact, config["last_master_contact"])

    def test_returns_current_assignments(self):
        # NOTE: current_assignments is improperly constructed here but we
        # only care about the values.
        config["current_assignments"] = {
            "a": {u"tasks": [{u"id": unicode(uuid.uuid4()), u"frame": 1}]},
            "b": {u"tasks": [{u"id": unicode(uuid.uuid4()), u"frame": 2}]},
            "c": {u"tasks": [{u"id": unicode(uuid.uuid4()), u"frame": 3}]}
        }
        current_tasks = []
        for item in config["current_assignments"].values():
            current_tasks += item["tasks"]

        request = self.get()
        tasks = Tasks()
        tasks.render(request)
        self.assertEqual(request.written, [dumps(current_tasks)])

    def test_delete_task_id_not_integer(self):
        request = self.delete(
            uri=["aaa"],
            headers={"User-Agent": config["master_user_agent"]})

        tasks = Tasks()
        tasks.render(request)
        self.assertEqual(
            request.written, ['{"error": "Task id was not an integer"}'])
        self.assertEqual(request.responseCode, BAD_REQUEST)

    def test_delete_assignment_does_not_exist(self):
        request = self.delete(
            uri=["2"],
            headers={"User-Agent": config["master_user_agent"]})

        tasks = Tasks()
        tasks.render(request)
        self.assertEqual(request.written, [""])
        self.assertEqual(request.responseCode, NO_CONTENT)

    def test_delete_assignment_found_but_no_jobtype(self):
        config["jobtypes"] = {}
        config["current_assignments"] = {
            "a": {
                "id": 1,
                "tasks": [{u"id": 2}],
            }
        }

        request = self.delete(
            uri=["2"],
            headers={"User-Agent": config["master_user_agent"]})

        tasks = Tasks()
        tasks.render(request)
        self.assertEqual(
            request.written,
            ['{"error": "Assignment found, but no jobtype instance exists."}'])
        self.assertEqual(request.responseCode, INTERNAL_SERVER_ERROR)

    def test_delete_stop_jobtype(self):
        deferred = Deferred()

        class FakeJobType(object):
            def stop(self):
                deferred.callback(None)

        config["jobtypes"] = {
            3: FakeJobType()
        }
        config["current_assignments"] = {
            "a": {
                "id": 1,
                "tasks": [{u"id": 2}],
                "jobtype": {"id": 3}
            }
        }

        request = self.delete(
            uri=["2"],
            headers={"User-Agent": config["master_user_agent"]})

        tasks = Tasks()
        tasks.render(request)
        self.assertEqual(request.written, [""])
        self.assertEqual(request.responseCode, ACCEPTED)

        return deferred
