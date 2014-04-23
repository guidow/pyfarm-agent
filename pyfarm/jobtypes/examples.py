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

"""
Examples
--------

This module contains some basic example job type implementations.
"""

from pyfarm.core.files import which
from pyfarm.jobtypes.core.jobtype import JobType
from pyfarm.jobtypes.core.process import ProcessInputs


class ListFiles(JobType):
    def build_process_inputs(self):
        for task in self.assignments():
            path = "/tmp/foo%s" % task["frame"]

            # generate the test file
            with open(path, "w") as stream:
                pass

            yield ProcessInputs(task, (which("ls"), path))