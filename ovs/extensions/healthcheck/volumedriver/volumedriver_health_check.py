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
import time
import timeout_decorator
from ovs.extensions.generic.system import System
from ovs.extensions.generic.filemutex import file_mutex
from timeout_decorator.timeout_decorator import TimeoutError
from ovs.extensions.healthcheck.helpers.configuration import ConfigurationManager, ConfigurationProduct
from ovs.extensions.healthcheck.decorators import ExposeToCli
from ovs.extensions.healthcheck.helpers.vdisk import VDiskHelper
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper
from ovs.extensions.healthcheck.helpers.exceptions import VDiskNotFoundError
from ovs.lib.vdisk import VDiskController
from volumedriver.storagerouter import storagerouterclient as src
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException, ObjectNotFoundException, \
    MaxRedirectsExceededException
from volumedriver.storagerouter.storagerouterclient import FileExistsException



class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """

    MODULE = "volumedriver"
    MACHINE_DETAILS = System.get_my_storagerouter()
    MACHINE_ID = System.get_my_machine_id()
    VDISK_CHECK_SIZE = 1073741824  # 1GB in bytes
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
                try:
                    results = VolumedriverHealthCheck._check_disk_dtl(vdisk_guid=vdisk_guid)
                    if results[1] == "ok_standalone":
                        logger.warning("VDisk {0}'s DTL is disabled".format(results[0]), test_name)
                    elif results[1] == "ok_sync":
                        logger.success("VDisk {0}'s DTL is enabled and running.".format(results[0]), test_name)
                    elif results[1] == "degraded":
                        logger.failure("VDisk {0}'s DTL is degraded.".format(results[0]), test_name)
                    elif results[1] == "catchup" or results[1] == "catch_up":
                        logger.warning("VDisk {0}'s DTL is enabled but still syncing.".format(results[0]), test_name)
                    else:
                        logger.warning("VDisk {0}'s DTL has an unknown status: {1}.".format(results[0], results[1]),
                                       test_name)
                except TimeoutError:
                    logger.warning("VDisk {0}'s DTL has a timeout status: {1}.".format(results[0], results[1]),
                                   test_name)

        else:
            logger.skip("No VDisks present in cluster.", test_name)

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_disk_dtl(vdisk_guid):
        """
        Get dtl status by vdisk guid

        :param vdisk_guid: guid of existing vdisk
        :type vdisk_guid: str
        :return: tuple
        :rtype: tuple
        """
        vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
        return vdisk.name, vdisk.dtl_status

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
        :return: True if succeeds
        :rtype: bool
        """

        VDiskController.create_new(vdisk_name, vdisk_size, storagedriver_guid)
        return True

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
                with file_mutex('ovs-healthcheck_check-volumedrivers'):
                    if vp.guid in VolumedriverHealthCheck.MACHINE_DETAILS.vpools_guids:
                        try:
                            # delete if previous vdisk with this name exists
                            if VolumedriverHealthCheck._check_volumedriver_remove(vpool_name=vp.name, vdisk_name=name,
                                                                                  present=False):
                                storagedriver_guid = next((storagedriver.guid for storagedriver in vp.storagedrivers
                                                           if storagedriver.storagedriver_id == vp.name +
                                                           VolumedriverHealthCheck.MACHINE_ID))
                                # create a new one
                                try:
                                    volume = VolumedriverHealthCheck._check_volumedriver(name, storagedriver_guid,
                                                                                         vp.name)
                                except FileExistsException:
                                    # can be ignored until fixed in framework
                                    # https://github.com/openvstorage/framework/issues/1247
                                    volume = True

                                if volume:
                                    # delete the recently created
                                    time.sleep(3)
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
                        except RuntimeError as ex:
                            logger.failure("Volumedriver of vPool '{0}' seems to have `runtime` problems. "
                                           "Got `{1}` while executing.".format(vp.name, ex), 'volumedriver_{0}'
                                           .format(vp.name))
                        except VDiskNotFoundError:
                            logger.warning("Volume on vPool '{0}' was not found, please retry again".format(vp.name),
                                           'volumedriver_{0}'.format(vp.name))
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
    @ExposeToCli('ovs', 'halted-volumes-test')
    def check_for_halted_volumes(logger):
        """
        Checks for halted volumes on a single or multiple vPools

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking for halted volumes: ")

        vpools = VPoolHelper.get_vpools()

        if len(vpools) != 0:

            for vp in vpools:

                if vp.guid in VolumedriverHealthCheck.MACHINE_DETAILS.vpools_guids:

                    haltedvolumes = []

                    logger.info("Checking vPool '{0}': ".format(vp.name))

                    config_file = ConfigurationManager.get_config_file_path(product=ConfigurationProduct.VPOOL,
                                                                            vpool_guid=vp.guid,
                                                                            vpool_name=vp.name,
                                                                            node_id=VolumedriverHealthCheck.MACHINE_ID)

                    try:
                        voldrv_client = src.LocalStorageRouterClient(config_file)
                        voldrv_volume_list = voldrv_client.list_volumes()

                        for volume in voldrv_volume_list:
                            # check if volume is halted, returns: 0 or 1
                            try:
                                if int(VolumedriverHealthCheck._info_volume(voldrv_client, volume).halted):
                                    haltedvolumes.append(volume)
                            except ObjectNotFoundException:
                                # ignore ovsdb invalid entrees
                                # model consistency will handle it.
                                continue
                            except MaxRedirectsExceededException:
                                # this means the volume is not halted but detached or unreachable for the volumedriver
                                haltedvolumes.append(volume)
                            except RuntimeError:
                                haltedvolumes.append(volume)
                            except TimeoutError:
                                # timeout occured
                                haltedvolumes.append(volume)

                    except (ClusterNotReachableException, RuntimeError) as ex:
                        logger.failure(
                            "Seems like the Volumedriver {0} is not running.".format(vp.name, ex.message),
                            'halted_volumedriver_{0}'.format(vp.name))
                        continue

                    # print all results
                    if len(haltedvolumes) > 0:
                        logger.failure("Detected volumes that are HALTED in vPool '{0}': {1}"
                                       .format(vp.name, ', '.join(haltedvolumes)), 'halted_volumes_{0}'.format(vp.name))
                    else:
                        logger.success("No halted volumes detected in vPool '{0}'"
                                       .format(vp.name), 'halted_volumes_{0}'.format(vp.name))
                else:
                    logger.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                'halted_volumedriver_{0}'.format(vp.name))

        else:
            logger.skip("No vPools found!".format(len(vpools)), 'halted_nofound')

    @staticmethod
    @timeout_decorator.timeout(5)
    def _info_volume(voldrv_client, volume_name):
        """
        Fetch the information from a volume through the volumedriver client

        :param voldrv_client: client of a volumedriver
        :type voldrv_client: volumedriver.storagerouter.storagerouterclient.LocalStorageRouterClient
        :param volume_name: name of a volume in the volumedriver
        :type volume_name: str
        :return: volumedriver volume object
        """

        return voldrv_client.info_volume(volume_name)

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_filedriver(vp_name, test_name):
        """
        Async method to checks if a FILEDRIVER `touch` works on a vpool
        Always try to check if the file exists after performing this method

        :param vp_name: name of the vpool
        :type vp_name: str
        :param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)
        :type test_name: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("touch /mnt/{0}/{1}.xml".format(vp_name, test_name),
                                       stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_filedriver_remove(vp_name):
        """
        Async method to checks if a FILEDRIVER `remove` works on a vpool
        Always try to check if the file exists after performing this method

        :param vp_name: name of the vpool
        :type vp_name: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("rm -f /mnt/{0}/ovs-healthcheck-test-*.xml".format(vp_name),
                                       stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @ExposeToCli('ovs', 'filedrivers-test')
    def check_filedrivers(logger):
        """
        Checks if the FILEDRIVERS work on a local machine (compatible with multiple vPools)

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking filedrivers: ", 'filedriver')

        vpools = VPoolHelper.get_vpools()

        # perform tests
        if len(vpools) != 0:
            for vp in vpools:
                name = "ovs-healthcheck-test-{0}".format(VolumedriverHealthCheck.MACHINE_ID)
                with file_mutex('ovs-healthcheck_filedrivers-test'):
                    if vp.guid in VolumedriverHealthCheck.MACHINE_DETAILS.vpools_guids:
                        try:
                            VolumedriverHealthCheck._check_filedriver(vp.name, name)
                            if os.path.exists("/mnt/{0}/{1}.xml".format(vp.name, name)):
                                # working
                                VolumedriverHealthCheck._check_filedriver_remove(vp.name)
                                logger.success("Filedriver for vPool '{0}' is working fine!".format(vp.name),
                                               'filedriver_{0}'.format(vp.name))
                            else:
                                # not working
                                logger.failure("Filedriver for vPool '{0}' seems to have problems!".format(vp.name),
                                               'filedriver_{0}'.format(vp.name))
                        except TimeoutError:
                            # timeout occured, action took too long
                            logger.failure("Filedriver of vPool '{0}' seems to have `timeout` problems"
                                           .format(vp.name), 'filedriver_{0}'.format(vp.name))
                        except subprocess.CalledProcessError:
                            # can be input/output error by filedriver
                            logger.failure("Filedriver of vPool '{0}' seems to have `input/output` problems"
                                           .format(vp.name), 'filedriver_{0}'.format(vp.name))
                    else:
                        logger.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                    'filedriver_{0}'.format(vp.name))
        else:
            logger.skip("No vPools found!", 'filedrivers_nofound')

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
        VolumedriverHealthCheck.check_for_halted_volumes(logger)
        VolumedriverHealthCheck.check_filedrivers(logger)
