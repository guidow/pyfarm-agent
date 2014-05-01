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

from pyfarm.agent.testutil import TestCase
from pyfarm.jobtypes.core.process import ProcessInputs


class TestProcessInputs(TestCase):
    def test_task_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs(None, []))

    def test_command_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs({}, None,))

    def test_env_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs({}, [], env=-1))

    def test_path_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs({}, [], path=-1))
        
    def test_user_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs({}, [], user=-1))
        
    def test_group_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs({}, [], group=-1))

    def convert_command_type(self):
        self.assertRaises(TypeError,
            lambda: ProcessInputs({}, [None]))

    def test_convert_numeric_command_values(self):
        self.assertEqual(ProcessInputs({}, [1]).command, ("1", ))