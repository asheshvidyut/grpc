# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from setuptools import find_packages, setup

setup(
    name="grpcio-cython",
    version="0.1.0",
    description="Register native (C/C++) handlers with a gRPC Python server.",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "grpcio_cython": ["include/grpcio_cython/handler.h"],
    },
    install_requires=["grpcio>=1.60.0"],
    python_requires=">=3.8",
)
