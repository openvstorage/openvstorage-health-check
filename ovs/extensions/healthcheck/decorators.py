# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.
import inspect


class ExposeToCli(object):
    def __init__(self, module_name=None, method_name=None):
        if module_name and method_name:
            self.module_name = module_name
            self.method_name = method_name

    def __call__(self, func):
        def get_path_info():
            for item in inspect.stack():
                if item and __file__ not in item:
                    return item[1]
            return __file__
        self.function = func
        func.module_name = self.module_name
        func.method_name = self.method_name
        return func
