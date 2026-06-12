import setuptools

setuptools.setup(
    name='grpc_cython',
    version='1.0.0',
    description='Cython extensions for high performance gRPC Python',
    packages=setuptools.find_packages(),
    install_requires=[
        'grpcio>=1.0.0',
    ],
)
