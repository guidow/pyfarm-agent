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
Logger
------

Agent specific logging library that combines some of
Twisted's and Python's logging facilities.
"""

from collections import deque
from datetime import datetime
from fnmatch import fnmatch
from logging import DEBUG, INFO, WARNING, CRITICAL, ERROR, FATAL, _levelNames

from twisted.python.log import textFromEventDict

from pyfarm.core.enums import INTERACTIVE_INTERPRETER

CONFIGURATION = {
    "datefmt": "%Y-%m-%d %H:%M:%S",
    "format": "%(asctime)s %(levelname)-8s - %(name)-15s - %(message)s",

      # Defines the cutoff level for different loggers.  By default
      # the only defined cutoff is for root ("").  Logger names
      # should be defined using *'s to define matches.
    "levels": [
        ("", DEBUG),
        ("HTTP11ClientProtocol*", INFO)
    ]}

# Only setup colorama if we're not inside
# of an interpreter.
if not INTERACTIVE_INTERPRETER:
    try:
        colorama
    except NameError:
        from colorama import init, Fore, Back, Style
        init()


class Observer(object):
    INSTANCE = None

    if not INTERACTIVE_INTERPRETER:
        FORMATS = {
            DEBUG: (Style.DIM, Style.RESET_ALL),
            WARNING: (Fore.YELLOW, Fore.RESET),
            ERROR: (Fore.RED, Fore.RESET),
            CRITICAL: (
                Fore.RED + Style.BRIGHT, Fore.RESET + Style.RESET_ALL),
            FATAL: (
                Fore.RED + Style.BRIGHT, Fore.RESET + Style.RESET_ALL)}

        def add_color(self, text, level):
            try:
                head, tail = self.FORMATS[level]
                return head + text + tail
            except KeyError:
                return text

    else:
        FORMATS = {}
        def add_color(self, text, _):
            return text

    def __init__(self):
        self.backlog = deque()
        self.datefmt = None
        self.format = None
        self.levels = []

    def configure(self):
        self.datefmt = CONFIGURATION["datefmt"]
        self.format = CONFIGURATION["format"]

        for name, level in CONFIGURATION["levels"]:
            if not isinstance(level, int):
                try:
                    level = _levelNames[level.upper()]

                except KeyError:
                    raise KeyError(
                        "%r's level %r does not exist" % (name, level))

            self.levels.append((name, level))

    def filter(self, name, level):
        for fname, flevel in CONFIGURATION["levels"]:
            if fname == "" and level > flevel:
                return True

            if (fname == name or fnmatch(name, fname)) and flevel > level:
                return True

    def emit(self, event):
        # Get the message
        text = textFromEventDict(event)
        if text is None:
            return

        # Create a timestamp
        if "time" in event:
            asctime = datetime.fromtimestamp(
                event["time"]).strftime(self.datefmt)
        else:
            # Since we're going to display the time we don't
            # want UTC here.
            asctime = datetime.now().strftime(self.datefmt)

        levelno = event.get("logLevel", DEBUG)
        levelname = _levelNames[levelno]
        name = event.get("system", "twisted")
        message = text % event.get("args", ())

        if name == "-":
            name = "twisted"

        if self.filter(name, levelno):
            return

        print self.add_color(self.format % locals(), levelno)

    def __call__(self, event):
        """
        Handles all logging events which are passed into Twisted's logging
        system.
        """
        # If we have not been fully setup yet then
        # processing any messages would not
        if self.format is None:
            self.backlog.append(event)
            return

        # If we have anything built up in the backlog
        # then be sure we handle these first
        while self.backlog:
            try:
                self.emit(self.backlog.pop())
            except IndexError:
                break

        self.emit(event)
