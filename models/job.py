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
.. include:: ../include/references.rst
"""

import os
from datetime import datetime
from UserDict import UserDict

try:
    import pwd
except ImportError:
    pwd = None

try:
    import json
except ImportError:
    import simplejson as json

try:
    property.setter
except AttributeError:
    from pyfarm.backports import _property as property

from textwrap import dedent
from sqlalchemy import event
from sqlalchemy.orm import validates
from sqlalchemy.schema import UniqueConstraint

from pyfarm.flaskapp import db
from pyfarm.config.enum import WorkState
from pyfarm.models.core import (
    DBCFG, TABLE_JOB, TABLE_JOB_TAGS, TABLE_JOB_SOFTWARE, IDColumn
)
from pyfarm.models.mixins import StateValidationMixin, StateChangedMixin


class JobTagsModel(db.Model):
    """
    Model which provides tagging for :class:`.JobModel` objects

    .. note::
        This table enforces two forms of uniqueness.  The :attr:`id` column
        must be unique and the combination of these columns must also be
        unique to limit the frequency of duplicate data:

            * :attr:`_jobid`
            * :attr:`tag`

    .. autoattribute:: _jobid
    """
    __tablename__ = TABLE_JOB_TAGS
    __table_args__ = (UniqueConstraint("_jobid", "tag"),)
    id = IDColumn()
    _jobid = db.Column(db.Integer, db.ForeignKey("%s.id" % TABLE_JOB),
                       doc=dedent("""
                       The foreign key which stores :attr:`JobModel.id`"""))

    tag = db.Column(db.String, nullable=False)


class JobSoftwareModel(db.Model):
    """
    Model which allows specific software to be associated with a
    :class:`.JobModel` object.

    .. note::
        This table enforces two forms of uniqueness.  The :attr:`id` column
        must be unique and the combination of these columns must also be
        unique to limit the frequency of duplicate data:

            * :attr:`_jobid`
            * :attr:`software`
            * :attr:`version`

    .. autoattribute:: _jobid
    """
    __tablename__ = TABLE_JOB_SOFTWARE
    __table_args__ = (UniqueConstraint("_jobid", "software", "version"),)
    id = IDColumn()
    _jobid = db.Column(db.Integer, db.ForeignKey("%s.id" % TABLE_JOB),
                       doc=dedent("""
                       The foreign key which stores :attr:`JobModel.id`"""))
    software = db.Column(db.String, nullable=False,
                         doc=dedent("""
                         The name of the software required to run a job"""))
    version = db.Column(db.String, default="any", nullable=False,
                        doc=dedent("""
                        The version of software required to run the job.  This
                        value does not follow any special formatting rules
                        because the format depends on the 3rd party."""))


class JobModel(db.Model, StateValidationMixin, StateChangedMixin):
    """
    Defines the attributes and environment for a job.  Individual commands
    are kept track of by |TaskModel|

    .. autoattribute:: _environ
    .. autoattribute:: _data
    .. autoattribute:: _args
    """
    __tablename__ = TABLE_JOB
    STATE_ENUM = WorkState()
    STATE_DEFAULT = STATE_ENUM.QUEUED

    id = IDColumn()

    # job state/general data not specific to a task
    state = db.Column(db.Integer, default=STATE_DEFAULT,
                      doc=dedent("""
                      The state of the job with a value provided by
                      :class:`.WorkState`
                      """))
    priority = db.Column(db.Integer, default=DBCFG.get("job.priority"),
                         doc=dedent("""
                         The priority of the job relative to others in the
                         queue.  This is not the same as task priority.

                         **configured by**: `job.priority`
                         """))
    user = db.Column(db.String(DBCFG.get("job.max_username_length")),
                     doc=dedent("""
                     The user this job should execute as.  The agent
                     process will have to be running as root on platforms
                     that support setting the user id.

                     .. note::
                        The length of this field is limited by the
                        configuration value `job.max_username_length`

                     .. warning::
                        this may not behave as expected on all platforms
                        (windows in particular)"""))
    notes = db.Column(db.Text, default="",
                      doc=dedent("""
                      Notes that are provided on submission or added after
                      the fact. This column is only provided for human
                      consumption is not scanned, index, or used when
                      searching"""))

    # time information
    time_submitted = db.Column(db.DateTime, default=datetime.now,
                               doc=dedent("""
                               The time the job was submitted.  By default this
                               defaults to using :meth:`datetime.datetime.now`
                               as the source of submission time.  This value
                               will not be set more than once and will not
                               change even after a job is requeued."""))
    time_started = db.Column(db.DateTime,
                             doc=dedent("""
                             The time this job was started.  By default this
                             value is set when :attr:`state` is changed to
                             an appropriate value or when a job is
                             requeued."""))
    time_finished = db.Column(db.DateTime,
                              doc=dedent("""
                              Time the job was finished.  This will be set
                              when the last task finishes and reset if a job
                              is requeued.
                              """))

    # task data
    cmd = db.Column(db.String,
                    doc=dedent("""
                    The platform independent command to run. Each agent will
                    resolve this value for itself when the task begins so a
                    command like `ping` will work on any platform it's
                    assigned to.  The full commend could be provided here,
                    but then the job must be tagged using
                    :class:`.JobSoftwareModel` to limit which agent(s) it will
                    run on."""))
    start = db.Column(db.Float,
                      doc=dedent("""
                      The first frame of the job to run.  This value may
                      be a float so subframes can be processed."""))
    end = db.Column(db.Float,
                      doc=dedent("""
                      The last frame of the job to run.  This value may
                      be a float so subframes can be processed."""))
    by = db.Column(db.Float, default=1,
                      doc=dedent("""
                      The number of frames to count by between `start` and
                      `end`.  This column may also sometimes be referred to
                      as 'step' by other software."""))
    batch = db.Column(db.Integer, default=DBCFG.get("job.batch"),
                      doc=dedent("""
                      Number of tasks to run on a single agent at once.
                      Depending on the capabilities of the software being run
                      this will either cause a single process to execute on
                      the agent or multiple processes on after the other.

                      **configured by**: `job.batch`"""))
    requeue = db.Column(db.Integer, default=DBCFG.get("job.requeue"),
                        doc=dedent("""
                        Number of times to requeue failed tasks

                        .. csv-table:: **Special Values**
                            :header: Value, Result
                            :widths: 10, 50

                            0, never requeue failed tasks
                            -1, requeue failed tasks indefinitely

                        **configured by**: `job.requeue`"""))
    cpus = db.Column(db.Integer, default=DBCFG.get("job.cpus"),
                     doc=dedent("""
                     Number of cpus or threads each task should consume on
                     each agent.  Depending on the job type being executed
                     this may result in additional cpu consumption, longer
                     wait times in the queue (2 cpus means 2 'fewer' cpus on
                     an agent), or all of the above.

                     .. csv-table:: **Special Values**
                        :header: Value, Result
                        :widths: 10, 50

                        0, minimum number of cpu resources not required
                        -1, agent cpu is exclusive for a task from this job

                     **configured by**: `job.cpus`"""))
    ram = db.Column(db.Integer, default=DBCFG.get("job.ram"),
                    doc=dedent("""
                    Amount of ram a task from this job will require to be
                    free in order to run.  A task exceeding this value will
                    not result in any special behavior.

                    .. csv-table:: **Special Values**
                        :header: Value, Result
                        :widths: 10, 50

                        0, minimum amount of free ram not required
                        -1, agent ram is exclusive for a task from this job

                    **configured by**: `job.ram`"""))
    ram_warning = db.Column(db.Integer, default=-1,
                            doc=dedent("""
                            Amount of ram used by a task before a warning
                            raised.  A task exceeding this value will not
                            cause any work stopping behavior.

                            .. csv-table:: **Special Values**
                                :header: Value, Result
                                :widths: 10, 50

                                -1, not set"""))
    ram_max = db.Column(db.Integer, default=-1,
                        doc=dedent("""
                        Maximum amount of ram a task is allowed to consume on
                        an agent.

                        .. warning::
                            The task will be **terminated** if the ram in use
                            by the process exceeds this value.

                        .. csv-table:: **Special Values**
                            :header: Value, Result
                            :widths: 10, 50

                            -1, not set
                        """))

    # underlying storage for properties
    _environ = db.Column(db.Text,
                         doc=dedent("""
                         Text containing a json dictionary which has some
                         information about the environment.  This value
                         is read by :attr:`.environ`"""))
    _args = db.Column(db.Text,
                      doc=dedent("""
                      Text containing a json list which stores
                      the arguments that are intended by be passed onto
                      the task's command.  This value is read by :attr:`.args`.
                      """))
    _data = db.Column(db.Text,
                      doc=dedent("""
                      Text containing extra data which a job type may want
                      to handle.  This data is not formatted and handled by
                      :attr:`.data`"""))

    # relationships
    _parentjob = db.Column(db.Integer, db.ForeignKey("%s.id" % TABLE_JOB))

    siblings = db.relationship("JobModel", backref=db.backref("parent",
                                                         remote_side=[id]),
                               doc=dedent("""
                               Relationship between this model and other
                               :class:`.JobModel` objects which have the same
                               parent.
                               """))

    tasks = db.relationship("TaskModel", backref="job", lazy="dynamic",
                            doc=dedent("""
                            Relationship between this job and and child
                            |TaskModel| objects
                            """))

    tasks_done = db.relationship("TaskModel", lazy="dynamic",
        primaryjoin="(TaskModel.state == %s) & "
                    "(TaskModel._jobid == JobModel.id)" % STATE_ENUM.DONE,
        doc=dedent("""
        Relationship between this job and any |TaskModel| objects which are
        done."""))

    tasks_failed = db.relationship("TaskModel", lazy="dynamic",
        primaryjoin="(TaskModel.state == %s) & "
                    "(TaskModel._jobid == JobModel.id)" % STATE_ENUM.FAILED,
        doc=dedent("""
        Relationship between this job and any |TaskModel| objects which have
        failed."""))

    tasks_queued = db.relationship("TaskModel", lazy="dynamic",
        primaryjoin="(TaskModel.state == %s) & "
                    "(TaskModel._jobid == JobModel.id)" % STATE_ENUM.QUEUED,
        doc=dedent("""
        Relationship between this job and any |TaskModel| objects which
        are queued."""))

    tags = db.relationship("JobTagsModel", backref="job", lazy="dynamic",
                           doc=dedent("""
                           Relationship between this job and
                           :class:`.JobTagsModel` objects"""))
    software = db.relationship("JobSoftwareModel", backref="job",
                               lazy="dynamic",
                               doc=dedent("""
                               Relationship between this job and
                               :class:`.JobSoftwareModel` objects"""))

    @property
    def environ(self):
        """
        Property which will produce an environment that a task can use on
        an agent.  If an environment was not provided as part of
        :attr:`_environ` then the current environment will be used instead.
        """
        environ = os.environ.copy()

        if not self._environ:
            return environ

        envbase = json.loads(self._environ)
        assert isinstance(envbase, dict), "expected a dictionary from _environ"
        environ.update(envbase)
        return environ

    @environ.setter
    def environ(self, value):
        """Takes the incoming `value` and stores it in `_environ`"""
        if isinstance(value, dict):
            value = json.dumps(value)
        elif isinstance(value, UserDict):
            value = json.dumps(value.data)
        else:
            raise TypeError("expected a dict or UserDict object for `environ`")

        self._environ = value

    @property
    def data(self):
        """Loads and produces data from :attr:`.data`"""
        return json.loads(self._data)

    @data.setter
    def data(self, value):
        """Takes the incoming `value` and stores it in `_data`"""
        self._data = json.dumps(value)

    @property
    def args(self):
        """Loads and produces data from :attr:`.args`"""
        return json.loads(self._args)

    @args.setter
    def args(self, value):
        assert isinstance(value, list), "expected a list for `args`"
        self._args = json.dumps(value)

    @validates("environ")
    def validate_environ(self, key, value):
        """
        Validation that ensures the value we're attempting to set on
        :attr:`.environ` is of type we expect
        """
        if not isinstance(value, (dict, UserDict, basestring)):
            raise TypeError("expected a dictionary or string for %s" % key)

        return value

    @validates("_environ")
    def validate_json(self, key, value):
        """
        Validation that ensures the underlying environment data is something
        we could store as a json document
        """
        try:
            json.dumps(value)
        except Exception, e:
            raise ValueError("failed to dump `%s` to json: %s" % (key, e))

        return value

    @validates("ram", "cpus")
    def validate_resource(self, key, value):
        """
        Validation that ensures that the value provided for either
        :attr:`.ram` or :attr:`.cpus` is a valid value with a given range
        """
        if value is None:
            return value

        min_value = DBCFG.get("agent.min_%s" % key)
        max_value = DBCFG.get("agent.max_%s" % key)

        # quick sanity check of the incoming config
        assert isinstance(min_value, int), "db.min_%s must be an integer" % key
        assert isinstance(max_value, int), "db.max_%s must be an integer" % key
        assert min_value >= 1, "db.min_%s must be > 0" % key
        assert max_value >= 1, "db.max_%s must be > 0" % key

        # check the provided input
        if min_value > value or value > max_value:
            msg = "value for `%s` must be between " % key
            msg += "%s and %s" % (min_value, max_value)
            raise ValueError(msg)

        return value


event.listen(JobModel.state, "set", JobModel.stateChangedEvent)


class Job(JobModel):
    """
    Provides :meth:`__init__` for :class:`.JobModel` so the model can
    be instanced with initial values.

    .. note::
        The :class:`.JobModel` allows nearly all of its columns to be nullable.
        This is done so an `id` could be retrieved without creating a new
        job however this class does not allow that
    """