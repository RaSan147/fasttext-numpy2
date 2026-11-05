#!/usr/bin/env python

# Copyright (c) 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
import setuptools
import os
import subprocess
import io
import re


def _version_from_git():
    try:
        tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return None
    return tag.lstrip("vV") if tag else None


def get_version():
    """Prefer CI/tag version so release asset names always match the tag."""
    for key in ("PACKAGE_VERSION", "SETUPTOOLS_SCM_PRETEND_VERSION"):
        value = os.environ.get(key)
        if value:
            return value.lstrip("vV")
    git_version = _version_from_git()
    if git_version and re.match(r"^\d+\.\d+", git_version):
        return git_version
    # Fallback for non-git / untagged local builds only.
    return "0.10.6"


__version__ = get_version()
FASTTEXT_SRC = "src"

# Based on https://github.com/pybind/python_example


class get_pybind_include:
    """Helper class to determine the pybind11 include path

    The purpose of this class is to postpone importing pybind11
    until it is actually installed, so that the ``get_include()``
    method can be invoked."""

    def __init__(self, user=False):
        try:
            pass
        except ImportError:
            if subprocess.call([sys.executable, "-m", "pip", "install", "pybind11"]):
                raise RuntimeError("pybind11 install failed.")

        self.user = user

    def __str__(self):
        import pybind11

        return pybind11.get_include(self.user)


try:
    coverage_index = sys.argv.index("--coverage")
except ValueError:
    coverage = False
else:
    del sys.argv[coverage_index]
    coverage = True

fasttext_src_files = map(str, os.listdir(FASTTEXT_SRC))
fasttext_src_cc = list(filter(lambda x: x.endswith(".cc"), fasttext_src_files))

fasttext_src_cc = list(
    map(lambda x: str(os.path.join(FASTTEXT_SRC, x)), fasttext_src_cc)
)

ext_modules = [
    Extension(
        str("fasttext_pybind"),
        [
            str("python/fasttext_module/fasttext/pybind/fasttext_pybind.cc"),
        ]
        + fasttext_src_cc,
        include_dirs=[
            # Path to pybind11 headers
            get_pybind_include(),
            get_pybind_include(user=True),
            # Path to fasttext source code
            FASTTEXT_SRC,
        ],
        language="c++",
        extra_compile_args=[
            "-O0 -fno-inline -fprofile-arcs -pthread -march=native"
            if coverage
            else "-O3 -funroll-loops -pthread -march=native"
        ],
    ),
]


# As of Python 3.6, CCompiler has a `has_flag` method.
# cf http://bugs.python.org/issue26689
def has_flag(compiler, flags):
    """Return a boolean indicating whether a flag name is supported on
    the specified compiler.
    """
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".cpp") as f:
        f.write("int main (int argc, char **argv) { return 0; }")
        try:
            compiler.compile([f.name], extra_postargs=flags)
        except setuptools.distutils.errors.CompileError:
            return False
    return True


def cpp_flag(compiler):
    """Return the -std=c++17 compiler flag."""
    standards = ["-std=c++17"]
    for standard in standards:
        if has_flag(compiler, [standard]):
            return standard
    raise RuntimeError("Unsupported compiler -- at least C++17 support " "is needed!")


class BuildExt(build_ext):
    """A custom build extension for adding compiler-specific options."""

    c_opts = {
        "msvc": ["/EHsc"],
        "unix": [],
    }

    def build_extensions(self):
        if sys.platform == "darwin":
            # Do not pin to the builder's macOS version (e.g. 26.x on GHA),
            # or delocate/cibuildwheel will reject the wheel. Respect an
            # existing env var (CI) and otherwise target a portable baseline.
            deployment_target = os.environ.get("MACOSX_DEPLOYMENT_TARGET") or "11.0"
            os.environ["MACOSX_DEPLOYMENT_TARGET"] = deployment_target
            all_flags = [
                "-stdlib=libc++",
                "-mmacosx-version-min=%s" % deployment_target,
            ]
            if has_flag(self.compiler, [all_flags[0]]):
                self.c_opts["unix"] += [all_flags[0]]
            elif has_flag(self.compiler, all_flags):
                self.c_opts["unix"] += all_flags
            else:
                raise RuntimeError(
                    "libc++ is needed! Failed to compile with {} and {}.".format(
                        " ".join(all_flags), all_flags[0]
                    )
                )
        ct = self.compiler.compiler_type
        opts = self.c_opts.get(ct, [])
        extra_link_args = []

        if coverage:
            coverage_option = "--coverage"
            opts.append(coverage_option)
            extra_link_args.append(coverage_option)

        if ct == "unix":
            opts.append('-DVERSION_INFO="%s"' % self.distribution.get_version())
            opts.append(cpp_flag(self.compiler))
            if has_flag(self.compiler, ["-fvisibility=hidden"]):
                opts.append("-fvisibility=hidden")
        elif ct == "msvc":
            # C++17 is required for std::string_view (dictionary.h).
            opts.append("/std:c++17")
            opts.append('/DVERSION_INFO=\\"%s\\"' % self.distribution.get_version())
        for ext in self.extensions:
            ext.extra_compile_args = opts
            ext.extra_link_args = extra_link_args
        build_ext.build_extensions(self)


def _get_readme():
    """
    Use pandoc to generate rst from md.
    pandoc --from=markdown --to=rst --output=python/README.rst python/README.md
    """
    with io.open("python/README.rst", encoding="utf-8") as fid:
        return fid.read()


setup(
    name="fasttext-numpy2",
    version=__version__,
    author="Onur Celebi",
    author_email="celebio@fb.com",
    description="fasttext Python bindings, fixed numpy 2 compatibiliy",
    long_description=_get_readme(),
    ext_modules=ext_modules,
    url="https://github.com/simon-ging/fasttext-numpy2",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Software Development",
        "Topic :: Scientific/Engineering",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Operating System :: Unix",
        "Operating System :: MacOS",
    ],
    install_requires=["pybind11>=2.2", "setuptools >= 0.7.0", "numpy"],
    cmdclass={"build_ext": BuildExt},
    packages=[
        str("fasttext"),
        str("fasttext.util"),
        str("fasttext.tests"),
    ],
    package_dir={str(""): str("python/fasttext_module")},
    zip_safe=False,
)
