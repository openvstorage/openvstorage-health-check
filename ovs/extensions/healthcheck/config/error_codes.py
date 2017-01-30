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


class ErrorCode(object):
    """
    Error code class. Every error code is defined by a unique code and provides information and a solution to a problem
    """
    def __init__(self, error_code, information, solution):
        self.error_code = error_code
        self.information = information
        self.solution = solution


class ErrorCodes(object):
    """
    Data list class containing all error codes
    """
    default = ErrorCode('HC000', 'Default code', 'Default code')  # Used in the start of these error codes. Means no code is in place
    # example_arakoon = type('ArakoonCode', (), {'error_code': 'ARA000', 'information': 'Occurs when arakoon is not running.', 'solution': 'Restart Arakoon'})
    # example_arakoon2 = type('ArakoonCode', (), {'error_code': 'ARA001', 'information': 'Occurs when arakoon is not responding.', 'solution': 'Restart Arakoon'})
