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

from twisted.web.server import NOT_DONE_YET

from pyfarm.agent.http.core.resource import Resource


class Logging(Resource):
    TEMPLATE = "logging.html"

    def get(self, request):
        def cb(result):
            request.write(result)
            request.finish()
        deferred = self.template.render()
        deferred.addCallback(cb)
        return NOT_DONE_YET
