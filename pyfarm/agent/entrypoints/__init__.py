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
Entry Points
------------

This module contains
"""

from pyfarm.agent.entrypoints.agent import AgentEntryPoint, fake_render

# the entrypoint used in setup.py
agent = AgentEntryPoint()


# Normally this shouldn't be included in source code but we're
# doing so here so a job type types not have to have the virtual
# environment loaded.
if __name__ == "__main__":
    fake_render()
