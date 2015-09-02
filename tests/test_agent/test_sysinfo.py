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

import ctypes
import os
import socket
import time
import psutil
import subprocess
import sys
import uuid
from contextlib import nested
from os.path import isfile

try:
    import pwd
except ImportError:  # pragma: no cover
    pwd = NotImplemented

try:  # pragma: no cover
    import win32api
    from win32com.shell import shell
except ImportError:  # pragma: no cover
    win32api = NotImplemented

try:
    import getpass
except ImportError:  # pragma: no cover
    getpass = NotImplemented

try:
    from os import getuid
except ImportError:  # pragma: no cover
    getuid = NotImplemented

import netifaces
from mock import Mock, patch

from pyfarm.core.utility import convert
from pyfarm.core.enums import LINUX, WINDOWS
from pyfarm.agent.testutil import TestCase, skipIf
from pyfarm.agent.sysinfo import system, network, cpu, memory, user, disks


class TestSystem(TestCase):
    def test_uptime(self):
        t1 = system.uptime()
        t2 = time.time() - psutil.boot_time()
        self.assertEqual(t2 - t1 < 5, True)

    def test_case_sensitive_filesystem(self):
        path = self.create_file()
        self.assertEqual(
            not all(map(isfile, [path, path.lower(), path.upper()])),
            system.filesystem_is_case_sensitive())

    def test_case_sensitive_environment(self):
        envvar_lower = "PYFARM_CHECK_ENV_CASE_" + uuid.uuid4().hex
        envvar_upper = envvar_lower.upper()

        # populate environment then compare the difference
        os.environ.update({envvar_lower: "0", envvar_upper: "1"})
        self.assertEqual(
            os.environ[envvar_lower] != os.environ[envvar_upper],
            system.environment_is_case_sensitive())

        # remove the envvars we just made
        for envvar in (envvar_lower, envvar_upper):
            os.environ.pop(envvar, None)

    def test_operation_system(self):
        self.assertEqual(system.operating_system("linux"), "linux")
        self.assertEqual(system.operating_system("windows"), "windows")
        self.assertEqual(system.operating_system("darwin"), "mac")
        self.assertEqual(system.operating_system("foobar"), "other")

    def test_machine_architecture(self):
        for arch in ("amd64", "x86_64", "ia64", "Syswow64"):
            self.assertEqual(system.machine_architecture(arch), 64)

        for arch in ("i386", "i686", "x86"):
            self.assertEqual(system.machine_architecture(arch), 32)

        with self.assertRaises(NotImplementedError):
            system.machine_architecture("")

        with self.assertRaises(NotImplementedError):
            system.machine_architecture("foobar")


class TestNetwork(TestCase):
    def test_hostname_ignore_dns_mappings(self):
        reverse_hostnames = set()
        for address in network.addresses():
            try:
                dns_name, aliases, dns_addresses = socket.gethostbyaddr(address)
            except socket.herror:
                pass
            else:
                if address in dns_addresses:
                    reverse_hostnames.add(dns_name)

        local_hostname = socket.gethostname()
        local_fqdn_query = socket.getfqdn()

        if local_fqdn_query in reverse_hostnames:
            hostname = local_fqdn_query
        elif local_hostname in reverse_hostnames:
            hostname = local_hostname
        else:
            hostname = socket.getfqdn(local_hostname)

        self.assertEqual(
            network.hostname(trust_name_from_ips=False),
            hostname)

    def test_hostname_trust_dns_mappings(self):
        reverse_hostnames = set()
        for address in network.addresses():
            try:
                dns_name, aliases, dns_addresses = socket.gethostbyaddr(address)
            except socket.herror:
                pass
            else:
                if address in dns_addresses:
                    reverse_hostnames.add(dns_name)

        if len(reverse_hostnames) == 1:
            self.assertEqual(
                network.hostname(trust_name_from_ips=True),
                reverse_hostnames.pop())

        if not reverse_hostnames:
            self.skipTest(
                "Could not retrieve any DNS names for this host")

        if len(reverse_hostnames) > 1:
            self.skipTest(
                "This host's addresses resolve to more than one hostname")

    def test_addresses(self):
        self.assertGreaterEqual(len(network.addresses(private_only=False)), 1)

    def test_addresses_type(self):
        self.assertIsInstance(network.addresses(), tuple)

    def test_interfaces(self):
        names = list(network.interfaces())
        self.assertEqual(len(names) > 1, True)
        self.assertEqual(isinstance(names, list), True)
        self.assertEqual(all(name in netifaces.interfaces() for name in names),
                         True)

        addresses = map(netifaces.ifaddresses, names)
        self.assertEqual(all(socket.AF_INET in i for i in addresses), True)


class TestCPU(TestCase):
    def test_count(self):
        self.assertEqual(psutil.cpu_count(), cpu.total_cpus())

    def test_load(self):
        # Make several attempts to test cpu.load().  Because this
        # depends on the system load at the time we make a few
        # attempts to get the results we expect.
        for _ in range(15):
            load = psutil.cpu_percent(.25) / cpu.total_cpus()
            try:
                self.assertApproximates(cpu.load(.25), load, .75)
            except AssertionError:
                continue
            else:
                break
        else:
            self.fail("Failed get a non-failing result after several attempts")

    def test_user_time(self):
        self.assertEqual(psutil.cpu_times().user <= cpu.user_time(), True)

    def test_system_time(self):
        self.assertEqual(psutil.cpu_times().system <= cpu.system_time(), True)

    def test_idle_time(self):
        self.assertEqual(psutil.cpu_times().idle <= cpu.idle_time(), True)

    def test_iowait(self):
        if LINUX:
            self.assertEqual(cpu.iowait() <= psutil.cpu_times().iowait, True)
        else:
            self.assertEqual(cpu.iowait(), None)


class TestMemory(TestCase):
    def test_totalram(self):
        self.assertEqual(memory.total_ram(),
                         int(convert.bytetomb(psutil.virtual_memory().total)))

    def test_ramused(self):
        v1 = memory.total_ram() - memory.free_ram()
        v2 = memory.used_ram()
        self.assertApproximates(v1, v2, 5)

    def test_ramfree(self):
        v1 = convert.bytetomb(psutil.virtual_memory().available)
        v2 = memory.free_ram()
        self.assertApproximates(v1, v2, 5)

    def test_process_memory(self):
        process = psutil.Process()
        v1 = convert.bytetomb(process.memory_info().rss)
        v2 = memory.process_memory()
        self.assertApproximates(v1, v2, 5)

    def test_total_consumption(self):
        # Spawn a child process so we have something
        # to iterate over
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"])
        parent = psutil.Process()
        start_total = total = parent.memory_info().rss

        for child_process in parent.children(recursive=True):
            try:
                total += child_process.memory_info().rss
            except psutil.NoSuchProcess:
                pass

        # These should not be equal if we've iterated
        # over any children at all.
        self.assertNotEqual(start_total, total)

        v1 = convert.bytetomb(total)
        v2 = memory.total_consumption()
        child.kill()
        self.assertApproximates(v1, v2, 5)


class TestUser(TestCase):
    @skipIf(pwd is NotImplemented, "pwd is NotImplemented")
    def test_username_pwd(self):
        self.assertEqual(pwd.getpwuid(os.getuid())[0], user.username())

    @skipIf(win32api is NotImplemented, "win32api is NotImplemented")
    def test_username_win32api(self):
        self.assertEqual(win32api.GetUserName(), user.username())

    @skipIf(getpass is NotImplemented, "getpass is NotImplemented")
    def test_username_getpass(self):
        self.assertEqual(getpass.getuser(), user.username())

    @skipIf(getuid is NotImplemented, "getuid is NotImplemented")
    def test_administrator_getuid(self):
        self.assertEqual(getuid() == 0, user.is_administrator())

    @skipIf(win32api is NotImplemented, "win32api is NotImplemented")
    def test_administrator_win32api(self):
        self.assertEqual(shell.IsUserAnAdmin(), user.is_administrator())

    @skipIf(win32api is NotImplemented and not WINDOWS,
            "win32api is NotImplemented and not WINDOWS")
    def test_administrator_no_win32api_and_windows(self):
        self.assertEqual(ctypes.windll.shell32.IsUserAnAdmin() != 0,
                         user.is_administrator())


class TestDisks(TestCase):
    def setUp(self):
        super(TestDisks, self).setUp()
        self.disks = [
            Mock(mountpoint="/mnt/1"),
            Mock(mountpoint="/mnt/2")
        ]
        self.disk_usage_data = {
            "/mnt/1": Mock(free=1, size=2),
            "/mnt/2": Mock(free=1, size=2)
        }

        self.namedtuple_type = []
        for disk in self.disks:
            info = self.disk_usage(disk.mountpoint)
            self.namedtuple_type.append(
                disks.DiskInfo(
                    mountpoint=disk.mountpoint,
                    free=info.free,
                    size=info.total
                )
            )

    def disk_usage(self, mountpoint):
        return self.disk_usage_data[mountpoint]

    def test_return_type(self):
        self.assertIsInstance(disks.disks(), list)

    def test_return_type_namedtuple(self):
        result = []
        for disk in self.disks:
            info = self.disk_usage(disk.mountpoint)
            result.append(
                disks.DiskInfo(
                    mountpoint=disk.mountpoint,
                    free=info.free,
                    size=info.total
                )
            )

        with nested(
            patch.object(psutil, "disk_partitions", return_value=self.disks),
            patch.object(psutil, "disk_usage", self.disk_usage)
        ):
            self.assertEqual(disks.disks(), result)

    def test_return_type_dict(self):
        result = []
        for disk in self.disks:
            usage = self.disk_usage(disk.mountpoint)
            result.append(
                {
                    "mountpoint": disk.mountpoint,
                    "free": usage.free,
                    "size": usage.total
                }
            )

        with nested(
            patch.object(psutil, "disk_partitions", return_value=self.disks),
            patch.object(psutil, "disk_usage", self.disk_usage)
        ):
            self.assertEqual(disks.disks(as_dict=True), result)



