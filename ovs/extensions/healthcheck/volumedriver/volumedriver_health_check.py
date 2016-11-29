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
from ovs.dal.exceptions import ObjectNotFoundException
from ovs.lib.vdisk import VDiskController


class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """

    MODULE = "volumedriver"
    MACHINE_DETAILS = System.get_my_storagerouter()
    MACHINE_ID = System.get_my_machine_id()
    VDISK_CHECK_SIZE = 10737418240  # 10GB in bytes

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
                try:
                    vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
                except ObjectNotFoundException:
                    # ignore because this can create a race condition
                    pass

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
    def _check_volumedriver(volume_name, vpool_guid, volume_size=VDISK_CHECK_SIZE):
        """
        Async method to checks if a VOLUMEDRIVER `truncate` works on a vpool
        Always try to check if the file exists after performing this method

        :param volume_name:
        :param volume_size:
        :param vpool_guid:
        :return:
        """
        vpool = VPoolHelper.get_vpool_by_guid(vpool_guid)
        storagedriver = None
        for std in vpool.storagedrivers:
            if VolumedriverHealthCheck.MACHINE_DETAILS.guid == std.storagerouter_guid:
                storagedriver = std
                break
        if storagedriver is None:
            raise ValueError('Could not find the right storagedriver for storagerouter {0}'.format(VolumedriverHealthCheck.MACHINE_DETAILS.guid))
        try:
            return VDiskController.create_new(volume_name, volume_size, storagedriver.guid)
        except Exception as ex:
            raise IOError(ex.message)

    @staticmethod
    @timeout_decorator.timeout(15)
    def _check_volumedriver_remove(vdisk_guid):
        """
        Async method to checks if a VOLUMEDRIVER `remove` works on a vpool
        Always try to check if the file exists after performing this method

        :param vdisk_guid: guid of the vdisk
        :type vdisk_guid: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        try:
            VDiskController.delete(vdisk_guid)
            return True
        except RuntimeError as ex:
            raise IOError('Could not remove vdisk {0}. Got {1}'.format(vdisk_guid, ex.message))

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
                name = "ovs-healthcheck-test-{0}.raw".format(VolumedriverHealthCheck.MACHINE_ID)
                if vp.guid in VolumedriverHealthCheck.MACHINE_DETAILS.vpools_guids:
                    try:
                        file_path = "/mnt/{0}/{1}".format(vp.name, name)
                        try:
                            vdisk_guid = VolumedriverHealthCheck._check_volumedriver(name, vp.guid)
                        except IOError as ex:
                            # Try to cleanup
                            try:
                                subprocess.check_output("rm -rf {0}".format(file_path), stderr=subprocess.STDOUT, shell=True)
                            except:
                                pass
                            raise
                        if os.path.exists(file_path):
                            # working
                            VolumedriverHealthCheck._check_volumedriver_remove(vdisk_guid)
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
                    except IOError as ex:
                        # can be input/output error by volumedriver
                        logger.failure("Volumedriver of vPool '{0}' seems to have `input/output` problems. Got {1} while executing."
                                       .format(vp.name, ex.message), 'volumedriver_{0}'.format(vp.name))
                    except ValueError as ex:
                        logger.failure(ex, 'volumedriver_{0}'.format(vp.name))

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
