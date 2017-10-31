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
from ovs.dal.exceptions import ObjectNotFoundException
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLIRunner
from ovs.extensions.healthcheck.helpers.exceptions import VDiskNotFoundError
from ovs.extensions.healthcheck.helpers.vdisk import VDiskHelper
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper
from ovs.extensions.storageserver.storagedriver import StorageDriverConfiguration
from ovs.lib.vdisk import VDiskController
from timeout_decorator.timeout_decorator import TimeoutError
from volumedriver.storagerouter import storagerouterclient as src
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException, ObjectNotFoundException, MaxRedirectsExceededException, FileExistsException


class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """
    MODULE = 'volumedriver'
    LOCAL_SR = System.get_my_storagerouter()
    LOCAL_ID = System.get_my_machine_id()
    VDISK_CHECK_SIZE = 1024 ** 3  # 1GB in bytes
    VDISK_TIMEOUT_BEFORE_DELETE = 0.5

    @staticmethod
    @expose_to_cli(MODULE, 'dtl-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_dtl(result_handler):
        """
        Checks the dtl for all vdisks on the local node
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        # Fetch vdisks hosted on this machine
        VolumedriverHealthCheck.LOCAL_SR.invalidate_dynamics('vdisks_guids')
        if len(VolumedriverHealthCheck.LOCAL_SR.vdisks_guids) == 0:
            return result_handler.skip('No VDisks present in cluster.')
        for vdisk_guid in VolumedriverHealthCheck.LOCAL_SR.vdisks_guids:
            try:
                vdisk = VDiskHelper.get_vdisk_by_guid(vdisk_guid)
                vdisk.invalidate_dynamics(['dtl_status', 'info'])
            except TimeoutError:
                result_handler.warning('VDisk {0}s DTL has a timeout status: {1}.'.format(vdisk.name, vdisk.dtl_status))
            if vdisk.dtl_status == 'ok_standalone' or vdisk.dtl_status == 'disabled':
                result_handler.success('VDisk {0}s DTL is disabled'.format(vdisk.name))
            elif vdisk.dtl_status == 'ok_sync':
                result_handler.success('VDisk {0}s DTL is enabled and running.'.format(vdisk.name))
            elif vdisk.dtl_status == 'degraded':
                result_handler.warning('VDisk {0}s DTL is degraded.'.format(vdisk.name))
            elif vdisk.dtl_status == 'checkup_required':
                result_handler.warning('VDisk {0}s DTL should be configured.'.format(vdisk.name))
            elif vdisk.dtl_status == 'catch_up':
                result_handler.warning('VDisk {0}s DTL is enabled but still syncing.'.format(vdisk.name))
            else:
                result_handler.warning('VDisk {0}s DTL has an unknown status: {1}.'.format(vdisk.name, vdisk.dtl_status))

    @staticmethod
    @timeout_decorator.timeout(30)
    def _check_volumedriver(vdisk_name, storagedriver_guid, logger, vdisk_size=VDISK_CHECK_SIZE):
        """
        Checks if the volumedriver can create a new vdisk
        :param vdisk_name: name of a vdisk (e.g. test.raw)
        :type vdisk_name: str
        :param storagedriver_guid: guid of a storagedriver
        :type storagedriver_guid: str
        :param vdisk_size: size of the volume in bytes (e.g. 10737418240 is 10GB in bytes)
        :type vdisk_size: int
        :param logger: logger instance
        :type logger: ovs.extensions.healthcheck.result.HCResults
        :return: True if succeeds
        :rtype: bool
        """
        try:
            VDiskController.create_new(vdisk_name, vdisk_size, storagedriver_guid)
        except FileExistsException:
            # can be ignored until fixed in framework
            # https://github.com/openvstorage/framework/issues/1247
            return True
        except Exception as ex:
            logger.failure('Creation of the vdisk failed. Got {0}'.format(str(ex)))
            return False
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
            # not found, if it should be present, re-raise the exception
            if present:
                raise
            else:
                return True

    @staticmethod
    # @expose_to_cli(MODULE, 'volumedrivers-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_volumedrivers(result_handler):
        """
        Checks if the VOLUMEDRIVERS work on a local machine (compatible with multiple vPools)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking volumedrivers.', add_to_result=False)
        vpools = VPoolHelper.get_vpools()
        if len(vpools) == 0:
            result_handler.skip('No vPools found!')
            return
        for vp in vpools:
            name = 'ovs-healthcheck-test-{0}.raw'.format(VolumedriverHealthCheck.LOCAL_ID)
            if vp.guid not in VolumedriverHealthCheck.LOCAL_SR.vpools_guids:
                result_handler.skip('Skipping vPool {0} because it is not living here.'.format(vp.name))
                continue
            try:
                # delete if previous vdisk with this name exists
                storagedriver_guid = next((storagedriver.guid for storagedriver in vp.storagedrivers
                                           if storagedriver.storagedriver_id == vp.name +
                                           VolumedriverHealthCheck.LOCAL_ID))
                # create a new one
                volume = VolumedriverHealthCheck._check_volumedriver(name, storagedriver_guid, result_handler)

                if volume is True:
                    # delete the recently created
                    try:
                        VolumedriverHealthCheck._check_volumedriver_remove(vpool_name=vp.name, vdisk_name=name)
                    except Exception as ex:
                        raise RuntimeError('Could not delete the created volume. Got {0}'.format(str(ex)))
                    # Working at this point
                    result_handler.success('Volumedriver of vPool {0} is working fine!'.format(vp.name))
                else:
                    # not working
                    result_handler.failure('Something went wrong during vdisk creation on vpool {0}.'.format(vp.name))

            except TimeoutError:
                # timeout occurred, action took too long
                result_handler.warning('Volumedriver of vPool {0} seems to timeout.'.format(vp.name))
            except IOError as ex:
                # can be input/output error by volumedriver
                result_handler.failure('Volumedriver of vPool {0} seems to have IO problems. Got `{1}` while executing.'.format(vp.name, ex.message))
            except RuntimeError as ex:
                result_handler.failure('Volumedriver of vPool {0} seems to have problems. Got `{1}` while executing.'.format(vp.name, ex))
            except VDiskNotFoundError:
                result_handler.warning('Volume on vPool {0} was not found, please retry again'.format(vp.name))
            except Exception as ex:
                result_handler.failure('Uncaught exception for Volumedriver of vPool {0}.Got {1} while executing.'.format(vp.name, ex))
            finally:
                # Attempt to delete the created vdisk
                try:
                    VolumedriverHealthCheck._check_volumedriver_remove(vpool_name=vp.name, vdisk_name=name, present=False)
                except:
                    pass

    @staticmethod
    @expose_to_cli(MODULE, 'halted-volumes-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_for_halted_volumes(result_handler):
        """
        Checks for halted volumes on a single or multiple vPools
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking for halted volumes.', add_to_result=False)
        vpools = VPoolHelper.get_vpools()

        if len(vpools) == 0:
            result_handler.skip('No vPools found!'.format(len(vpools)))
            return

        for vp in vpools:
            if vp.guid not in VolumedriverHealthCheck.LOCAL_SR.vpools_guids:
                result_handler.skip('Skipping vPool {0} because it is not living here.'.format(vp.name))
                continue

            haltedvolumes = []
            result_handler.info('Checking vPool {0}: '.format(vp.name), add_to_result=False)
            if len(vp.storagedrivers) > 0:
                config_file = Configuration.get_configuration_path('/ovs/vpools/{0}/hosts/{1}/config'.format(vp.guid, vp.storagedrivers[0].name))
            else:
                result_handler.failure('The vpool {0} does not have any storagedrivers associated to it!'.format(vp.name))
                continue

            try:
                voldrv_client = src.LocalStorageRouterClient(config_file)
                # noinspection PyArgumentList
                voldrv_volume_list = voldrv_client.list_volumes()
                for volume in voldrv_volume_list:
                    # check if volume is halted, returns: 0 or 1
                    try:
                        # noinspection PyTypeChecker
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
                        # timeout occurred
                        haltedvolumes.append(volume)
                result_handler.success('Volumedriver {0} is up and running.'.format(vp.name))
            except (ClusterNotReachableException, RuntimeError) as ex:
                result_handler.failure('Seems like the Volumedriver {0} is not running.'.format(vp.name, ex.message))
                continue

            # print all results
            if len(haltedvolumes) > 0:
                result_handler.failure('Detected volumes that are HALTED in vPool {0}: {1}'.format(vp.name, ', '.join(haltedvolumes)))
            else:
                result_handler.success('No halted volumes detected in vPool {0}'.format(vp.name))

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
        # noinspection PyUnresolvedReferences
        return voldrv_client.info_volume(volume_name)

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_filedriver(vp_name, test_name):
        """
        Async method to checks if a FILEDRIVER `touch` works on a vpool
        Always try to check if the file exists after performing this method
        :param vp_name: name of the vpool
        :type vp_name: str
        :param test_name: name of the test file (e.g. `ovs-healthcheck-LOCAL_ID`)
        :type test_name: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """
        return subprocess.check_output('touch /mnt/{0}/{1}.xml'.format(vp_name, test_name), stderr=subprocess.STDOUT, shell=True)

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
        subprocess.check_output('rm -f /mnt/{0}/ovs-healthcheck-test-*.xml'.format(vp_name), stderr=subprocess.STDOUT, shell=True)
        return not os.path.exists('/mnt/{0}/ovs-healthcheck-test-*.xml'.format(vp_name))

    @staticmethod
    # @expose_to_cli(MODULE, 'filedrivers-test', HealthCheckCLIRunner.ADDON_TYPE)
    # @todo replace fuse test with edge test
    def check_filedrivers(result_handler):
        """
        Checks if the file drivers work on a local machine (compatible with multiple vPools)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        """
        result_handler.info('Checking file drivers.', add_to_result=False)
        vpools = VPoolHelper.get_vpools()
        # perform tests
        if len(vpools) == 0:
            result_handler.skip('No vPools found!')
            return
        for vp in vpools:
            name = 'ovs-healthcheck-test-{0}'.format(VolumedriverHealthCheck.LOCAL_ID)
            if vp.guid not in VolumedriverHealthCheck.LOCAL_SR.vpools_guids:
                result_handler.skip('Skipping vPool {0} because it is not living here.'.format(vp.name))
                continue
            try:
                VolumedriverHealthCheck._check_filedriver(vp.name, name)
                if os.path.exists('/mnt/{0}/{1}.xml'.format(vp.name, name)):
                    # working
                    VolumedriverHealthCheck._check_filedriver_remove(vp.name)
                    result_handler.success('Filedriver for vPool {0} is working fine!'.format(vp.name))
                else:
                    # not working
                    result_handler.failure('Filedriver for vPool {0} seems to have problems!'.format(vp.name))
            except TimeoutError:
                # timeout occurred, action took too long
                result_handler.warning('Filedriver of vPool {0} seems to have `timeout` problems'.format(vp.name))
            except subprocess.CalledProcessError:
                # can be input/output error by filedriver
                result_handler.failure('Filedriver of vPool {0} seems to have `input/output` problems'.format(vp.name))

    @staticmethod
    @expose_to_cli(MODULE, 'volume-potential-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_volume_potential(result_handler, critical_vol_number=25):
        """
        Checks all local storage drivers from a volume driver. Results in a success if enough volumes are available, a warning if the number of volumes is
        lower then a threshold value (critical_volume_number) and a failure if the nr of volumes ==0)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param critical_vol_number: maximal number of volumes that result in a warning
        :type critical_vol_number: int
        """
        if not isinstance(critical_vol_number, int) and critical_vol_number >= 0:
            raise ValueError('Critical volume number should be a positive integer')

        for std in VolumedriverHealthCheck.LOCAL_SR.storagedrivers:
            try:
                std_config = StorageDriverConfiguration(std.vpool_guid, std.storagedriver_id)
                client = src.LocalStorageRouterClient(std_config.remote_path)
                vol_potential = client.volume_potential(str(std.storagedriver_id))
                if vol_potential >= critical_vol_number:
                    log_level = 'success'
                elif critical_vol_number > vol_potential > 0:
                    log_level = 'warning'
                else:
                    log_level = 'failure'
                getattr(result_handler, log_level)('Volume potential of local storage driver: {0}: {1} (potential at: {2})'.format(std.storagedriver_id, log_level.upper(), vol_potential))
            except RuntimeError:
                result_handler.exception('Unable to retrieve configuration for storagedriver {0}'.format(std.storagedriver_id))
