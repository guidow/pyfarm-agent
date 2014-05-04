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

from __future__ import with_statement

import sys
assert sys.version_info[0:2] >= (2, 6), "Python 2.6 or higher is required"

from os.path import isfile
from setuptools import setup

install_requires = [
    "psutil>=2.1.0", "netifaces>=0.10.2", "netaddr",
    "colorama", "logutils"]


# Windows is a little special because we have to have pywin32
# installed.  pyfarm.core uses it and certain components of
# other libraries use it too, such as twisted, so we check for
# it here.  Unfortunately, we can't use PyPi for this.
if sys.platform.startswith("win"):
    try:
        import win32api
    except ImportError:
        raise ImportError(
            "On Windows, you must manually install pywin32 before running "
            "pyfarm.core's setup.py.  This is required because there's not "
            "a package that we can pull down and reliably install from "
            "Python package repository.  Please visit "
            "http://sourceforge.net/projects/pywin32/files/pywin32/ to "
            "download and install this package.")
    else:
        install_requires.append("wmi")


if isfile("README.rst"):
    with open("README.rst", "r") as readme:
        long_description = readme.read()
else:
    long_description = ""

setup(
    name="pyfarm.core",
    version="0.7.18",
    packages=["pyfarm",
              "pyfarm.core",
              "pyfarm.core.sysinfo"],
    namespace_packages=["pyfarm"],
    install_requires=install_requires,
    url="https://github.com/pyfarm/pyfarm-core",
    license="Apache v2.0",
    author="Oliver Palmer",
    author_email="development@pyfarm.net",
    description="Sub-library which contains core modules, "
                "classes, and data types which are used by other "
                "parts of PyFarm.",
    long_description=long_description,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        "Topic :: System :: Distributed Computing"])
