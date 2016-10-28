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
from ovs.extensions.healthcheck.decorators import ExposeToCli


class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """

    @staticmethod
    @ExposeToCli('alba', 'check_dtl')
    def check_dtl(logger):
        """
        Checks the dtl for all vdisks

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        pass

    @staticmethod
    def run(logger):
        """
        Testing suite for volumedriver

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        VolumedriverHealthCheck.check_dtl(logger)
