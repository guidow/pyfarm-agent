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

"""
Job Type Internals
==================

Contains classes which contain internal methods for
the :class:`pyfarm.jobtypes.core.jobtype.JobType` class.
"""

import imp
import os
import sys
import tempfile
from errno import EEXIST
from datetime import datetime
from os.path import dirname, isdir, join, isfile
from string import Template
from uuid import UUID
from functools import partial

try:
    from httplib import (
        OK, INTERNAL_SERVER_ERROR, CREATED, ACCEPTED, CONFLICT)
except ImportError:  # pragma: no cover
    from http.client import (
        OK, INTERNAL_SERVER_ERROR, CREATED, ACCEPTED, CONFLICT)

try:
    import pwd
    import grp
except ImportError:  # pragma: no cover
    pwd = NotImplemented
    grp = NotImplemented

from twisted.internet import reactor, threads
from twisted.internet.defer import Deferred, DeferredList

import treq

from pyfarm.core.enums import INTEGER_TYPES, STRING_TYPES, WorkState
from pyfarm.agent.config import config
from pyfarm.agent.logger import getLogger
from pyfarm.agent.http.core.client import get, post, http_retry_delay
from pyfarm.jobtypes.core.log import STDOUT, logpool
from pyfarm.jobtypes.core.process import ReplaceEnvironment

USER_GROUP_TYPES = tuple(
    list(STRING_TYPES) + list(INTEGER_TYPES) + [type(None)])
ITERABLE_CONTAINERS = (list, tuple, set)

logcache = getLogger("jobtypes.cache")
logger = getLogger("jobtypes.core")
logfile = getLogger("jobtypes.log")


class Cache(object):
    """Internal methods for caching job types"""
    cache = {}
    JOBTYPE_VERSION_URL = \
        "%(master_api)s/jobtypes/%(name)s/versions/%(version)s"
    CACHE_DIRECTORY = config.get("jobtype_cache_directory", "")

    if not CACHE_DIRECTORY:  # pragma: no cover
        CACHE_DIRECTORY = None  # make sure it's None
        logger.warning("Job type cache directory has been disabled.")

    else:
        try:
            os.makedirs(CACHE_DIRECTORY)

        except OSError as e:  # pragma: no cover
            if e.errno != EEXIST:
                logger.error(
                    "Failed to create %r.  Job type caching is "
                    "now disabled.", CACHE_DIRECTORY)
                raise
        else:
            logger.info("Created job type cache directory %r", CACHE_DIRECTORY)

        logger.debug("Job type cache directory is %r", CACHE_DIRECTORY)

    @classmethod
    def _download_jobtype(cls, name, version):
        """
        Downloads the job type specified in ``assignment``.  This
        method will pass the response it receives to :meth:`_cache_jobtype`
        however failures will be retried.
        """
        logger.debug("Downloading job type %r version %s", name, version)
        url = str(cls.JOBTYPE_VERSION_URL % {
            "master_api": config["master_api"],
            "name": name, "version": version})

        result = Deferred()
        download = lambda *_: \
            get(url,
                callback=result.callback,
                errback=lambda: reactor.callLater(http_retry_delay(), download))
        download()
        return result

    @classmethod
    def _cache_filepath(cls, cache_key, classname, version):
        return str(join(
            cls.CACHE_DIRECTORY, "%s_%s_v%s.py" % (
                cache_key, classname, version)))

    @classmethod
    def _cache_key(cls, assignment):
        return assignment["jobtype"]["name"], assignment["jobtype"]["version"]

    @classmethod
    def _jobtype_download_complete(cls, response, cache_key):
        # Server is offline or experiencing issues right
        # now so we should retry the request.
        if response.code >= INTERNAL_SERVER_ERROR:
            logger.debug(
                "Could not download jobtype because of internal server error.")
            return reactor.callLater(
                http_retry_delay(),
                response.request.retry)

        downloaded_data = response.json()

        if not config["jobtype_enable_cache"]:
            logger.debug("Jobtype cache is disabled, loading the jobtype.")
            return cls._load_jobtype(downloaded_data, None)

        else:
            # When the download is complete, cache the results
            logger.debug("Caching the jobtype locally.")
            caching = cls._cache_jobtype(cache_key, downloaded_data)
            caching.addCallback(
                lambda result: cls._load_jobtype(*result))
            return caching


    @classmethod
    def _cache_jobtype(cls, cache_key, jobtype):
        """
        Once the job type is downloaded this classmethod is called
        to store it on disk.  In the rare even that we fail to write it
        to disk, we store it in memory instead.
        """
        if isinstance(cache_key, tuple):
            cache_key = cache_key[0]

        assert isinstance(cache_key, STRING_TYPES)
        assert isinstance(jobtype, dict)
        filename = cls._cache_filepath(
            cache_key, jobtype["classname"], jobtype["version"])
        success = Deferred()
        jobtype = jobtype.copy()

        def write_to_disk(filename):
            parent_dir = dirname(filename)
            try:
                os.makedirs(parent_dir)
            except (IOError, OSError) as e:  # pragma: no cover
                if e.errno != EEXIST:
                    logger.error("Failed to create %s: %s", parent_dir, e)
            else:
                logger.debug("Created %s", parent_dir)

            if isfile(filename):  # pragma: no cover
                logcache.warning("%s is already cached on disk", filename)
                jobtype.pop("code", None)
                return jobtype, filename

            try:
                with open(filename, "w") as stream:
                    stream.write(jobtype["code"])

            # If the above fails, use a temp file instead
            except (IOError, OSError) as e:  # pragma: no cover
                _, tmpfilepath = tempfile.mkstemp(suffix=".py")
                logcache.warning(
                    "Failed to write %s, using %s instead: %s",
                    filename, tmpfilepath, e)

                with open(tmpfilepath, "w") as stream:
                    stream.write(jobtype["code"])

                jobtype.pop("code", None)
                return jobtype, tmpfilepath

            else:
                logger.debug(
                    "Wrote job type %s version %s to %s",
                    jobtype["name"], jobtype["version"], filename)
                jobtype.pop("code", None)
                return jobtype, filename

        def written_to_disk(results):
            jobtype, filename = results
            cls.cache[cache_key] = (jobtype, filename)
            logcache.info("Created cache for %r at %s", cache_key, filename)
            success.callback((jobtype, filename))

        def failed_to_write_to_disk(error):  # pragma: no cover
            logcache.error(
                "Failed to write job type cache to disk, will use "
                "memory instead: %s", error)

            # The code exists in the job type because it's
            # only removed on success.
            cls.cache[cache_key] = (jobtype, None)
            success.callback((jobtype, None))

        # Defer the write process to a thread so we don't
        # block the reactor if the write is slow
        logger.debug(
            "Caching job type %s version %s to %s",
            jobtype["classname"], jobtype.get("version", "?"), filename)
        writer = threads.deferToThread(write_to_disk, filename)
        writer.addCallbacks(written_to_disk, failed_to_write_to_disk)
        return success

    @classmethod
    def _module_for_jobtype(cls, jobtype):
        return "pyfarm.jobtypes.cached.%s%s%s" % (
            jobtype["classname"], jobtype["name"], jobtype["version"])

    @classmethod
    def _load_jobtype(cls, jobtype, filepath):
        def load_jobtype(jobtype_data, path):
            module_name = cls._module_for_jobtype(jobtype_data)

            # Create or load the module
            if filepath is not None:
                logger.debug("Attempting to load module from file path %s",
                             filepath)
                try:
                    module = imp.load_source(module_name, path)
                except Exception as e:
                    type = sys.exc_info()[0]
                    value = sys.exc_info()[1]
                    logger.error("Importing module from jobtype file failed: "
                                 "%s, value: %s", type, value)
                    raise
            else:
                logcache.warning(
                    "Loading (%s, %s) directly from memory",
                    jobtype_data["name"], jobtype_data["version"])

                module = imp.new_module(module_name)
                exec jobtype_data["code"] in module.__dict__
                sys.modules[module_name] = module

            logger.debug("Returning class %s from module",
                         jobtype_data["classname"])
            return getattr(module, jobtype_data["classname"])

        # Load the job type itself in a thread so we limit disk I/O
        # and other blocking issues in the main thread.
        return threads.deferToThread(load_jobtype, jobtype, filepath)


class Process(object):
    """Methods related to process control and management"""
    logging = {}

    def __init__(self):
        self.start_called = False
        self.stop_called = False
        self._stopped_deferred = None
        self._start_deferred = None

    @property
    def stopped_deferred(self):
        if not self.start_called:
            raise RuntimeError("Not yet started")
        return self._stopped_deferred

    @property
    def start_deferred(self):
        if not self.start_called:
            raise RuntimeError("Not yet started")
        return self._stopped_deferred

    @stopped_deferred.setter
    def stopped_deferred(self, value):
        assert self.start_called
        assert self._stopped_deferred is None
        assert isinstance(value, Deferred)
        self._stopped_deferred = value

    @start_deferred.setter
    def start_deferred(self, value):
        assert self.start_called
        assert self._start_deferred is None
        assert isinstance(value, Deferred)
        self._start_deferred = value

    def _before_spawn_process(self, command, protocol):
        logger.debug(
            "%r._before_spawn_process(%r, %r)", self, command, protocol)
        self.before_spawn_process(command, protocol)

    def _spawn_twisted_process(
            self, _, command, process_protocol, kwargs):
        """
        Handles the spawning of the process itself using
        :func:`reactor.spawnProcess`.

        :param tuple _:
            An ignored argument containing the protocol id and
            csv log file
        """
        self._before_spawn_process(command, process_protocol)

        # The way Twisted handles the env keyword varies by platform.  To
        kwargs.setdefault("env", None)
        if kwargs["env"] is not None:
            raise RuntimeError(
                "The `env` keyword should always be set to None.")

        with ReplaceEnvironment(command.env):
            reactor.spawnProcess(process_protocol, command.command, **kwargs)

    def _start(self):
        # Make sure _start() is not called twice
        if self.start_called:
            raise RuntimeError("%s has already been started" % self)

        self._before_start()
        logger.debug("%r.start()", self.__class__.__name__)
        self.start()
        self.start_called = True
        logger.debug("Collecting started deferreds from spawned processes")
        started_deferreds = []
        for process in self.processes.values():
            started_deferreds.append(process.started)
        logger.debug("Making deferred list self.started_deferred")
        self.started_deferred = DeferredList(started_deferreds)
        self.stopped_deferred = Deferred()
        return self.started_deferred, self.stopped_deferred

    def _stop(self):
        if self.stop_called:
            raise RuntimeError("%s has already been stopped" % self)

        return self.stop()

    def get_uid_gid(self, user, group):
        """
        Overridable method to convert a named user and group into their
        respective user and group ids.
        """
        uid = None
        gid = None

        # Convert user to uid
        if all([user is not None, pwd is not NotImplemented]):
            uid = self._get_uid_gid_value(
                user, "username", "get_uid", pwd, "pwd")

        # Convert group to gid
        if all([group is not None, grp is not NotImplemented]):
            gid = self._get_uid_gid_value(
                group, "group", "get_gid", grp, "grp")

        return uid, gid

    def _before_start(self):
        logger.debug("%r._before_start()", self)
        self.before_start()

    def _process_started(self, protocol):
        """
        Called by :meth:`.ProcessProtocol.connectionMade` when a process has
        started running.
        """
        logger.debug("%r._process_started(%r)", self, protocol)
        logpool.log(protocol.uuid, STDOUT, "Started %r" % protocol)
        proess_data = self.processes[protocol.uuid]
        proess_data.started.callback(protocol)
        if not self.stop_called:
            self.process_started(protocol)
        else:
            self.stop()

    def _process_stopped(self, protocol, reason):
        """
        Internal implementation for :meth:`process_stopped`.

        If ``--capture-process-output`` was set when the agent was launched
        all standard output from the process will be sent to the stdout
        of the agent itself.  In all other cases we send the data to the
        logger pool so it can be stored in a file without blocking the
        event loop.
        """
        logger.info("%r stopped (code: %r)", protocol, reason.value.exitCode)
        process_data = self.processes.pop(protocol.uuid)

        if self.is_successful(reason):
            logpool.log(
                protocol.uuid, STDOUT,
                "Process has terminated successfully, code %s" %
                reason.value.exitCode)
        else:
            self.failed_processes.add((protocol, reason))
            logpool.log(
                protocol.uuid, STDOUT,
                "Process has not terminated successfully, code %s" %
                reason.value.exitCode)

        try:
            self.process_stopped(protocol, reason)
        except Exception as e:
            logger.error("Exception caught from process_stopped, traceback: %s",
                         e.getTraceback())
        logpool.close_log(protocol.uuid)
        process_data.stopped.callback(reason)

        self._upload_logfile(process_data.log_identifier)

        # If there are no processes running at this point, we assume
        # the assignment is finished
        if len(self.processes) == 0:
            # TODO Mark tasks that have not yet been marked otherwise as FAILED
            if not self.failed_processes:
                logger.info("Processes in assignment %s stopped, no failures",
                            self)
            else:
                logger.warning("There was at least one failed process in the "
                               "assignment %s", self)
            self.stopped_deferred.callback(None)

    def _has_running_processes(self):
        """
        Internal functionto determine whether the batch represented by this
        instance still has running child processes.
        """
        for process in self.processes.values():
            if process.protocol.running():
                return True

        return False

    def _register_logfile_on_master(self, log_path):
        def post_logfile(task, log_path, delay=0):
            url = "%s/jobs/%s/tasks/%s/attempts/%s/logs/" % (
                config["master_api"], self.assignment["job"]["id"], task["id"],
                task["attempt"])
            data = {"identifier": log_path,
                    "agent_id": self.node()["id"]}
            post_func = partial(
                post, url, data=data,
                callback=lambda x: result_callback(task, log_path, x),
                errback=lambda x: error_callback(task, log_path, x))
            reactor.callLater(delay, post_func)

        def result_callback(task, log_path, response):
            if 500 <= response.code < 600:
                delay = http_retry_delay()
                logger.error(
                    "Server side error while registering log file %s for "
                    "task %s (frame %s) in job %s (id %s), status code: %s. "
                    "Retrying. in %s seconds",
                    log_path, task["id"], task["frame"],
                    self.assignment["job"]["title"],
                    self.assignment["job"]["id"], response.code, delay)
                post_logfile(task, log_path, delay=delay)

            # The server will return CONFLICT if we try to register a logfile
            # twice
            elif response.code not in [OK, CONFLICT, CREATED]:
                # Nothing else we could do about that, this is
                # a problem on our end.
                logger.error(
                    "Could not register logfile %s for task %s (frame %s) in "
                    "job %s (id %s), status code: %s. This is a client side "
                    "error, giving up.",
                    log_path, task["id"], task["frame"],
                    self.assignment["job"]["title"],
                    self.assignment["job"]["id"], response.code)

            else:
                logger.info("Registered logfile %s for task %s on master",
                            log_path, task["id"])

        def error_callback(task, log_path, failure_reason):
            delay = http_retry_delay()
            logger.error(
                "Error while registering logfile %s for task %s on master: "
                "\"%s\", retrying in %s seconds.",
                log_path, task["id"], failure_reason, delay)
            post_logfile(task, log_path, delay=delay)

        for task in self.assignment["tasks"]:
            post_logfile(task, log_path)

    def _upload_logfile(self, log_identifier):
        path = join(config["jobtype_task_logs"], log_identifier)
        url = "%s/jobs/%s/tasks/%s/attempts/%s/logs/%s/logfile" % (
                config["master_api"], self.assignment["job"]["id"],
                self.assignment["tasks"][0]["id"],
                self.assignment["tasks"][0]["attempt"],
                log_identifier)

        def upload(url, log_identifier, delay=0):
            logfile = open(path, "rb")
            if delay != 0:
                reactor.callLater(delay, upload, url,
                                  log_identifier=log_identifier)
            else:
                deferred = treq.put(url=url, data=logfile,
                                    headers={"Content-Type": ["text/csv"]})
                deferred.addCallback(lambda x: result_callback(
                    url, log_identifier, x))
                deferred.addErrback(lambda x: error_callback(
                    url, log_identifier, x))

        def result_callback(url, log_identifier, response):
            if 500 <= response.code < 600:
                delay = http_retry_delay()
                logger.error(
                    "Server side error while uploading log file %s, "
                    "status code: %s. Retrying. in %s seconds",
                    log_identifier, response.code, delay)
                upload(url, log_identifier, delay=delay)

            elif response.code not in [OK, CREATED, ACCEPTED]:
                # Nothing else we could do about that, this is
                # a problem on our end.
                logger.error(
                    "Could not upload logfile %s status code: %s. "
                    "This is a client side error, giving up.",
                    log_identifier, response.code)

            else:
                logger.info("Uploaded logfile %s for to master",
                            log_identifier)

        def error_callback(url, log_identifier, failure_reason):
            delay = http_retry_delay()
            logger.error(
                "Error while registering logfile %s on master: "
                "%r, retrying in %s seconds.",
                log_identifier, failure_reason, delay)
            upload(url, log_identifier, delay=delay)

        logger.info("Uploading log file %s to master, URL %r", log_identifier,
                    url)
        upload(url, log_identifier)

    # complete coverage provided by other tests
    def _get_uid_gid_value(self, value, value_name, func_name,
                           module, module_name):  # pragma: no cover
        """
        Internal function which handles both user name and group conversion.
        """
        if not isinstance(value, STRING_TYPES):
            raise TypeError("Expected string for `value`")

        # This platform does not implement the module
        if module is NotImplemented:
            logger.warning(
                "This platform does not implement the %r module, skipping "
                "%s()", module_name, func_name)

        # Convert a user/group string to an integer
        elif isinstance(value, STRING_TYPES):
            try:
                if module_name == "pwd":
                    return pwd.getpwnam(value).pw_uid
                elif module_name == "grp":
                    return grp.getgrnam(value).gr_gid
                else:
                    raise ValueError(
                        "Internal error, failed to get module to use for "
                        "conversion.  Was given %r" % module)
            except KeyError:
                logger.error(
                    "Failed to convert %s to a %s",
                    value, func_name.split("_")[1])

                if not config.get("jobtype_ignore_id_mapping_errors"):
                    raise

        # Verify that the provided user/group string is real
        elif isinstance(value, INTEGER_TYPES):
            try:
                if module_name == "pwd":
                    pass
                elif module_name == "grp":
                    pass
                else:
                    raise ValueError(
                        "Internal error, failed to get module to use for "
                        "conversion.  Was given %r" % module)

                # Seems to check out, return the original value
                return value
            except KeyError:
                logger.error(
                    "%s %s does not seem to exist", value_name, value)

                if not config.get("jobtype_ignore_id_mapping_errors"):
                    raise
        else:
            raise ValueError(
                "Expected an integer or string for `%s`" % value_name)


class TypeChecks(object):
    def _check_expandvars_inputs(self, value, environment):
        """Checks input arguments for :meth:`expandvars`"""
        if not isinstance(value, STRING_TYPES):
            raise TypeError("Expected a string for `value`")

        if environment is not None and not isinstance(environment, dict):
            raise TypeError("Expected None or a dictionary for `environment`")

    def _check_map_path_inputs(self, path):
        """Checks input arguments for :meth:`map_path`"""
        if not isinstance(path, STRING_TYPES):
            raise TypeError("Expected string for `path`")

    def _check_csvlog_path_inputs(self, protocol_uuid, now):
        """Checks input arguments for :meth:`get_csvlog_path`"""
        if not isinstance(protocol_uuid, UUID):
            raise TypeError("Expected UUID for `protocol_uuid`")

        if now is not None and not isinstance(now, datetime):
            raise TypeError("Expected None or datetime for `now`")

    def _check_command_list_inputs(self, cmdlist):
        """Checks input arguments for :meth:`get_command_list`"""
        if not isinstance(cmdlist, (tuple, list)):
            raise TypeError("Expected tuple or list for `cmdlist`")

    def _check_set_states_inputs(self, tasks, state):
        """Checks input arguments for :meth:`set_states`"""
        if not isinstance(tasks, ITERABLE_CONTAINERS):
            raise TypeError("Expected tuple, list or set for `tasks`")

        if state not in WorkState:
            raise ValueError("Expected `state` to be in %s" % list(WorkState))
