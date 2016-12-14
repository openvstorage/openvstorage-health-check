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


class SectionNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class DirectoryNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class ArakoonClusterNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class UnsupportedInitManager(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class PresetNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class AlbaBackendNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


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


class VPoolNotFoundError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class ImageConvertError(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass

class ObjectNotFoundException(Exception):
    """
    Raised when an object was queries that doesn't exist
    """
    pass


class CommandException(Exception):
    """
    Raised when an object was queries that returns non-zero
    """
    pass


class UnsupportedPlatformException(Exception):
    """
    Raised when an platform is not supported
    """
    pass


class ScrubberException(Exception):
    """
    Raised when scrubber failed
    """
    pass


class ConnectionFailedException(Exception):
    """
    Raised when a connection is failed
    """
    pass


class DiskNotFoundException(Exception):
    """
    Raised when a ASD disk is not found
    """
    pass


class ConfigNotFoundException(Exception):
    """
    Raised when a config isn't found
    """
    pass


class ConfigNotMatchedException(Exception):
    """
    Raised when a config isn't matched to the desired regex
    """
    pass


class PlatformNotSupportedException(Exception):
    """
    Raised when the platform is not supported
    """
    pass


class AlbaException(Exception):
    """
    Exceptions by AlbaCli will be derived from this class
    """
    ALBA_COMMANDS = [
        "proxy-create-namespace",
        "show-namespace",
        "proxy-upload-object",
        "download-object",
        "proxy-delete-object",
        "asd-delete",
        "asd-multi-get",
        "asd-set"
     ]
    # Certain exceptions are unclear.
    EXCEPTION_MAPPING = {
        '(Unix.Unix_error "Connection refused" connect "")': "Could not connect to to ASD."
    }

    def __init__(self, message, alba_command):
        # Call the base class constructor with the parameters it needs
        super(AlbaException, self).__init__(message)
        # Own properties
        if alba_command in AlbaException.ALBA_COMMANDS:
            self.alba_command = alba_command
        else:
            raise ValueError("'{0}' is not a valid alba command. Valid commands are {1}"
                             .format(alba_command, " ".join(AlbaException.ALBA_COMMANDS)))

    def __str__(self):
        return "Command '{0}' failed with '{1}'.".format(self.alba_command, self.EXCEPTION_MAPPING.get(self.message,
                                                                                                       self.message))
