"""
Build script for the Cython extension of this package.

The project metadata lives in `pyproject.toml`. This script only exists to
declare the extension module, since a Cython extension cannot be described
declaratively.

The extension is built from `revisionstore/revisionstore.py`, which is written
in the pure Python mode of Cython. The type annotations in that module are what
the compiler turns into C types.
"""

from Cython.Build import cythonize
from setuptools import Extension, setup

setup(
    ext_modules=cythonize(
        [
            Extension(
                "revisionstore.revisionstore",
                sources=["revisionstore/revisionstore.py"],
            )
        ],
        compiler_directives={
            "language_level": "3",
            "embedsignature": True,
        },
    )
)
