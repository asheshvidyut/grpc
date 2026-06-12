from setuptools import setup
from Cython.Build import cythonize

setup(
    name="math_example",
    ext_modules=cythonize([
        "math_cython_pb2.pyx",
        "server.pyx"
    ], compiler_directives={'language_level': "3"})
)
