# Copyright (c) LinkedIn Corporation. All rights reserved. Licensed under the BSD-2 Clause license.
# See LICENSE in the project root for license information.

import setuptools
import re
import string

setuptools.setup(
    name='iris_admin',
    version='0.0.1',
    package_dir={'': 'src'},
    packages=setuptools.find_packages('src'),
    include_package_data=True,
    install_requires=open('requirements.txt').readlines(),
)
