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
Module containing the exceptions used in the Healthcheck
"""


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
