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
from ovs.extensions.healthcheck.helpers.vdisk import VDiskHelper
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper


class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """

    MODULE = "volumedriver"
    MACHINE_DETAILS = System.get_my_storagerouter()
    MACHINE_ID = System.get_my_machine_id()

    @staticmethod
    @ExposeToCli('volumedriver', 'check_dtl')
    def check_dtl(logger):
        """
        Checks the dtl for all vdisks

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        test_name = "check_dtl"

        # Fetch vdisks hosted on this machine
        if len(VolumedriverHealthCheck.MACHINE_DETAILS.vdisks_guids) != 0:
            for vdisk_guid in VolumedriverHealthCheck.MACHINE_DETAILS.vdisks_guids:
                vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
                # Check dtl
                dtl_status = vdisk.dtl_status
                if dtl_status == "ok_standalone":
                    logger.warning("Vdisk {0}'s DTL is disabled because of a single node cluster".format(vdisk.name), test_name)
                elif dtl_status == "ok_sync":
                    logger.success("Vdisk {0}'s DTL is enabled and running.".format(vdisk.name), test_name)
                elif dtl_status == "degraded":
                    logger.failure("Vdisk {0}'s DTL is degraded.".format(vdisk.name), test_name)
                elif dtl_status == "catchup" or dtl_status =="catch_up":
                    logger.warning("Vdisk {0}'s DTL is enabled but still syncing.".format(vdisk.name), test_name)
                else:
                    logger.warning("Vdisk {0}'s DTL has an unknown status: {1}.".format(vdisk.name, dtl_status), test_name)
        else:
            logger.skip("No vdisks present in cluster.", test_name)

    @staticmethod
    @timeout_decorator.timeout(15)
    def _check_volumedriver(file_path):
        """
        Async method to checks if a VOLUMEDRIVER `truncate` works on a vpool
        Always try to check if the file exists after performing this method

        :param file_path: path of the file
        :type file_path: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("truncate -s 10GB {0}".format(file_path), stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @timeout_decorator.timeout(15)
    def _check_volumedriver_remove(file_path):
        """
        Async method to checks if a VOLUMEDRIVER `remove` works on a vpool
        Always try to check if the file exists after performing this method

        :param file_path: path of the file
        :type file_path: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("rm -f {0}".format(file_path), stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @ExposeToCli('volumedriver', 'check-volumedrivers')
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
                        file_path = "/mnt/{0}/{1}.raw".format(vp.name, name)
                        VolumedriverHealthCheck._check_volumedriver(file_path)
                        if os.path.exists(file_path):
                            # working
                            VolumedriverHealthCheck._check_volumedriver_remove(file_path)
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
        VolumedriverHealthCheck.check_volumedrivers(logger)
        VolumedriverHealthCheck.check_dtl(logger)
