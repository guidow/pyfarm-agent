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
Configuration Object
====================

Basic module used for changing and storing configuration values used by all
modules at execution time.
"""

try:
    from ast import literal_eval
except ImportError:
    from pyfarm.core.backports import literal_eval

NOTSET = object()


class Config(object):
    """
    Dictionary like object used to centrally store configuration
    information.  Generally this will be used at the module level and
    populated on startup.
    """
    def __init__(self, data=None):
        assert isinstance(data, dict) or data is None, "bad type for `data`"
        self.__data = {} if data is None else data.copy()

    def __iter__(self):
        return self.__data.__iter__()

    def __repr__(self):  # pragma: no cover
        return self.__data.__repr__()

    def __contains__(self, item):
        return self.__data.__contains__(item)

    def items(self):
        """same as :meth:`dict.iteritems` in Python < 3.x"""
        return self.__data.iteritems()

    def get(self, key, default=NOTSET):
        """
        similar to :meth:`dict.get` except that if a value does not exist
        it will raise an exception unless a default is provided
        """
        if default is NOTSET and key not in self:
            raise KeyError("%s not found" % key)
        return self.__data.get(key, default)

    def set(self, key, value):
        """sets `key` to `value`"""
        self.__data.__setitem__(key, value)

    def setdefault(self, key, default=None):
        return self.__data.setdefault(key, default)

    def update(self, data):
        """
        similar to :meth:`dict.update` except only a dictionary as input
        is allowed
        """
        assert isinstance(data, dict), "`data` must be a dictionary"
        return self.__data.update(data)


def read_env(envvar, default=NOTSET, desc=None, log_value=True,
             warn_if_default=False, raise_eval_exception=True):
    """
    Lookup and evaluate an environment variable.

    :param string envvar:
        The environment variable to lookup in :class:`os.environ`

    :param object default:
        Alternate value to return if ``envvar`` is not present.  If this
        is instead set to ``NOTSET`` then an exception will be raised if
        ``envvar`` is not found.

    :keyword string desc:
        Describes the purpose of the value being returned.  This may also
        be read in at the time the documentation is built.

    :keyword bool log_value:
        If True, log the value we're returning for the environment variable.

    :keyword bool warn_if_default:
        If True, log a warning if the value being returned is the same
        as ``default``

    :keyword bool raise_eval_exception:
        If True and we failed to parse ``envvar`` with :func:`.literal_eval`
        then raise a :class:`EnvironmentKeyError`
    """
    pass

cfg = Config()