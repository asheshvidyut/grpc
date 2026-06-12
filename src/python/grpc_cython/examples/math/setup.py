from setuptools import setup, Extension
from Cython.Build import cythonize

exts = [
    Extension("math_cython_pb2", ["math_cython_pb2.pyx", "math.pb.cc"], libraries=["protobuf"], language="c++"),
    Extension("server", ["server.pyx"], libraries=["protobuf"], language="c++")
]

setup(
    name="math_example",
    ext_modules=cythonize(exts, compiler_directives={'language_level': "3"})
)
