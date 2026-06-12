from setuptools import setup, Extension
from Cython.Build import cythonize

exts = [
    Extension("math_cython_pb2", ["math_cython_pb2.pyx", "math.pb.cc"], extra_link_args=["-lprotobuf"], language="c++"),
    Extension("server", ["server.pyx"], extra_link_args=["-lprotobuf"], language="c++")
]

setup(
    name="math_example",
    ext_modules=cythonize(exts, compiler_directives={'language_level': "3"})
)
