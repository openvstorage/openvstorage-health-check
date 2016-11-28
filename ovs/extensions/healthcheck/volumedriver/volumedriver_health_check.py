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
import time
import timeout_decorator
from ovs.lib.vdisk import VDiskController
from ovs.extensions.generic.system import System
from timeout_decorator.timeout_decorator import TimeoutError
from ovs.extensions.healthcheck.decorators import ExposeToCli
from ovs.extensions.healthcheck.helpers.vdisk import VDiskHelper
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper
from ovs.extensions.healthcheck.helpers.exceptions import VDiskNotFoundError


class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """

    MODULE = "volumedriver"
    MACHINE_DETAILS = System.get_my_storagerouter()
    MACHINE_ID = System.get_my_machine_id()
    VDISK_CHECK_SIZE = 10737418240  # 10GB in bytes
    VDISK_TIMEOUT_BEFORE_DELETE = 0.5

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
    @timeout_decorator.timeout(30)
    def _check_volumedriver(vdisk_name, storagedriver_guid, vpool_name, vdisk_size=VDISK_CHECK_SIZE):
        """
        Checks if the volumedriver can create a new vdisk

        :param vdisk_name: name of a vdisk (e.g. test.raw)
        :type vdisk_name: str
        :param vdisk_size: size of the volume in bytes (e.g. 10737418240 is 10GB in bytes)
        :type vdisk_size: int
        :param storagedriver_guid: guid of a storagedriver
        :type storagedriver_guid: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        VDiskController.create_new(vdisk_name, vdisk_size, storagedriver_guid)

        return os.path.exists("/mnt/{0}/{1}".format(vpool_name, vdisk_name))

    @staticmethod
    @timeout_decorator.timeout(30)
    def _check_volumedriver_remove(vpool_name, vdisk_name, present=True):
        """
        Remove a vdisk from a vpool

        :param vdisk_name: name of a vdisk (e.g. test.raw)
        :type vdisk_name: str
        :param vpool_name: name of a vpool
        :type vpool_name: str
        :param present: should the disk be present?
        :type present: bool
        :return: True if disk is not present anymore
        :rtype: bool
        """

        try:
            vdisk = VDiskHelper.get_vdisk_by_name(vdisk_name=vdisk_name, vpool_name=vpool_name)
            VDiskController.delete(vdisk.guid)

            return True
        except VDiskNotFoundError:
            # not found, if it should be present, reraise the exception
            if present:
                raise
            else:
                return True

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
                        # delete if previous vdisk with this name exists
                        if VolumedriverHealthCheck._check_volumedriver_remove(vpool_name=vp.name, vdisk_name=name,
                                                                              present=False):
                            storagedriver_guid = next((storagedriver.guid for storagedriver in vp.storagedrivers
                                                       if storagedriver.storagedriver_id == vp.name +
                                                       VolumedriverHealthCheck.MACHINE_ID))
                            # create a new one
                            if VolumedriverHealthCheck._check_volumedriver(name, storagedriver_guid, vp.name):
                                # delete the recently created
                                if VolumedriverHealthCheck._check_volumedriver_remove(vpool_name=vp.name,
                                                                                      vdisk_name=name):
                                    # working
                                    logger.success("Volumedriver of vPool '{0}' is working fine!".format(vp.name),
                                                   'volumedriver_{0}'.format(vp.name))
                                else:
                                    # not working
                                    logger.failure("Volumedriver of vPool '{0}' seems to have problems"
                                                   .format(vp.name), 'volumedriver_{0}'.format(vp.name))
                            else:
                                # not working
                                logger.failure("Something went wrong during vdisk creation on vpool '{0}' ..."
                                               .format(vp.name), 'volumedriver_{0}'.format(vp.name))
                        else:
                            logger.failure("Volumedriver of vPool '{0}' seems to have problems if vdisk already exists"
                                           .format(vp.name), 'volumedriver_{0}'.format(vp.name))

                    except TimeoutError:
                        # timeout occured, action took too long
                        logger.failure("Volumedriver of vPool '{0}' seems to have `timeout` problems"
                                       .format(vp.name), 'volumedriver_{0}'.format(vp.name))
                    except IOError as ex:
                        # can be input/output error by volumedriver
                        logger.failure("Volumedriver of vPool '{0}' seems to have `input/output` problems. "
                                       "Got `{1}` while executing.".format(vp.name, ex.message),
                                       'volumedriver_{0}'.format(vp.name))
                    except (RuntimeError, VDiskNotFoundError) as ex:
                        logger.failure("Volumedriver of vPool '{0}' seems to have `runtime` problems. "
                                       "Got `{1}` while executing.".format(vp.name, ex), 'volumedriver_{0}'
                                       .format(vp.name))
                    except Exception as ex:
                        logger.failure("Volumedriver of vPool '{0}' seems to have `exception` problems. "
                                       "Got `{1}` while executing.".format(vp.name, ex), 'volumedriver_{0}'
                                       .format(vp.name))
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
