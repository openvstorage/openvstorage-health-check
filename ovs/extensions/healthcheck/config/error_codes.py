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


class ErrorCodesType(type):
    """
    Class which customizes the properties for a certain other class
    This class is meant to be a metaclass
    """
    def __getattr__(self, item):
        return self._internal_codes[item]


class ErrorCodes(object):
    """
    Container for all error codes
    """
    __metaclass__ = ErrorCodesType

    _internal_codes = {
        ###############
        # Healthcheck #
        ###############
        'default': ErrorCode('HC0000', 'Default code', 'Default code'),  # Used in the start of these error codes. Means no code is in place
        ########
        # ALBA #
        ########

        #############
        # Framework #
        #############

        ###########
        # Arakoon #
        ###########

        ################
        # Volumedriver #
        ################
        'voldrv_connection_problem': ErrorCode('VOL1003', 'Volumedriver is not responding to calls (fast enough)', 'Verify whether this volumedriver is running'),
        # vPools
        'vpools_none': ErrorCode('VOL0000', 'No vPools present', 'Add vPools to this node'),
        'vpool_not_local': ErrorCode('VOL0001', 'vPool not on this node', 'Extend vPool to this node'),
        # Volume states
        'volume_not_found': ErrorCode('VOL1001', 'Volumedriver does not recognize this volume', 'Verify whether this volume is still present'),
        'volume_max_redir': ErrorCode('VOL1002', 'Volumedriver can\'t retrieve information about the volume. This indicates the volume might be down', 'Verify whether this volume is running'),
        'volume_halted': ErrorCode('VOL1004', 'Volume is in the \'halted\' state. The volume could still be failing over to another node', 'A possible solution is restarting this volume (after the failover is done)'),
        # Volume DTL
        'volume_dtl_unknown': ErrorCode('VOL1011', 'The volumes DTL state which is not recognized', 'Report this issue to OpenvStorage'),
        'volume_dtl_catch_up': ErrorCode('VOL1012', 'The volumes DTL state is still syncing', 'Wait for the sync to finish'),
        'volume_dtl_checkup_required': ErrorCode('VOL1013', 'The volumes DTL should be configured', 'Configure the DTL for this volume'),
        'volume_dtl_degraded': ErrorCode('VOL1014', 'The volumes DTL is degraded', 'Perform the DTL checkup for this volume')
        }
