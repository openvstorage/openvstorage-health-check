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

"""
Exceptions module
"""


class HealthCheckException(Exception):
    """
    Exception class that provides the error codes
    """
    def __init__(self, message, error_code):
        """
        Initialize the class
        :param message: error message
        :param error_code: error code
        """
        # Call the base class constructor with the parameters it needs
        super(HealthCheckException, self).__init__(message)
        # Own properties
        self.error_code = error_code


class VPoolNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class VDiskNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class ObjectNotFoundException(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class DiskNotFoundException(Exception):
    """
    Raised when a ASD disk is not found
    """
    pass


class ConfigNotMatchedException(Exception):
    """
    Raised when a config isn't matched to the desired regex
    """
    pass


class ConnectionFailedException(Exception):
    """
    Raised when a connection is failed
    """
    pass


class AlbaException(Exception):
    """
    Exceptions by AlbaCli will be derived from this class
    """
    # Certain exceptions are unclear.
    EXCEPTION_MAPPING = {
        '(Unix.Unix_error "Connection refused" connect "")': "Could not connect to ASD."
    }

    def __init__(self, message, alba_command):
        # Call the base class constructor with the parameters it needs
        super(AlbaException, self).__init__(message)
        # Own properties
        self.alba_command = alba_command

    def __str__(self):
        return "Command '{0}' failed with '{1}'.".format(self.alba_command, self.EXCEPTION_MAPPING.get(self.message, self.message))


class AlbaTimeOutException(AlbaException):
    def __init__(self, *args):
        super(AlbaTimeOutException, self).__init__(*args)

    def __str__(self):
        return "Command '{0}' has timed out with '{1}'.".format(self.alba_command, self.EXCEPTION_MAPPING.get(self.message, self.message))