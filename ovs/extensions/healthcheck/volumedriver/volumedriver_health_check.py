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
import os
import subprocess
import timeout_decorator
from ovs.extensions.generic.system import System
from timeout_decorator.timeout_decorator import TimeoutError
from ovs.extensions.healthcheck.decorators import ExposeToCli
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper

class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """

    MODULE = "volumedriver"
    MACHINE_DETAILS = System.get_my_storagerouter()

    @staticmethod
    @ExposeToCli('alba', 'check_dtl')
    def check_dtl(logger):
        """
        Checks the dtl for all vdisks

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        # Fetch vdisks hosted on this machine

        pass

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_volumedriver(vp_name, test_name):
        """
        Async method to checks if a VOLUMEDRIVER `truncate` works on a vpool
        Always try to check if the file exists after performing this method

        :param vp_name: name of the vpool
        :type vp_name: str
        :param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)
        :type test_name: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("truncate -s 10GB /mnt/{0}/{1}.raw".format(vp_name, test_name),
                                       stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_volumedriver_remove(vp_name):
        """
        Async method to checks if a VOLUMEDRIVER `remove` works on a vpool
        Always try to check if the file exists after performing this method

        :param vp_name: name of the vpool
        :type vp_name: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("rm -f /mnt/{0}/ovs-healthcheck-test-*.raw".format(vp_name),
                                       stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @ExposeToCli('volumedriver', 'check')
    def check_volumedrivers(logger):
        """
        Checks if the VOLUMEDRIVERS work on a local machine (compatible with multiple vPools)

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking volumedrivers: ", 'check_volumedrivers')

        vpools = VPoolHelper.get_vpools()

        if len(vpools) != 0:
            for vp in vpools:
                name = "ovs-healthcheck-test-{0}".format(VolumedriverHealthCheck.MACHINE_ID)
                if vp.guid in VolumedriverHealthCheck.MACHINE_DETAILS.vpools_guids:
                    try:
                        VolumedriverHealthCheck._check_volumedriver(vp.name, name)

                        if os.path.exists("/mnt/{0}/{1}.raw".format(vp.name, name)):
                            # working
                            VolumedriverHealthCheck._check_volumedriver_remove(vp.name)
                            logger.success("Volumedriver of vPool '{0}' is working fine!".format(vp.name),
                                           'volumedriver_{0}'.format(vp.name))
                        else:
                            # not working, file does not exists
                            logger.failure("Volumedriver of vPool '{0}' seems to have problems"
                                           .format(vp.name), 'volumedriver_{0}'.format(vp.name))
                    except TimeoutError:
                        # timeout occured, action took too long
                        logger.failure("Volumedriver of vPool '{0}' seems to have `timeout` problems"
                                       .format(vp.name), 'volumedriver_{0}'.format(vp.name))
                    except subprocess.CalledProcessError:
                        # can be input/output error by volumedriver
                        logger.failure("Volumedriver of vPool '{0}' seems to have `input/output` problems"
                                       .format(vp.name), 'volumedriver_{0}'.format(vp.name))

                else:
                    logger.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                'volumedriver_{0}'.format(vp.name))
        else:
            logger.skip("No vPools found!", 'volumedrivers_nofound')

    @staticmethod
    @ExposeToCli('volumedriver', 'test')
    def run(logger):
        """
        Testing suite for volumedriver

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        VolumedriverHealthCheck.check_dtl(logger)
