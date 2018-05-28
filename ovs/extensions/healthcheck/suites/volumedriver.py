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
from ovs.dal.dataobject import DataObject
from ovs.dal.hybrids.vdisk import VDisk
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLI
from ovs.extensions.healthcheck.config.error_codes import ErrorCodes
from ovs.extensions.healthcheck.helpers.exceptions import VDiskNotFoundError
from ovs.extensions.healthcheck.helpers.vdisk import VDiskHelper
from ovs.extensions.healthcheck.logger import Logger
from ovs.extensions.storageserver.storagedriver import StorageDriverConfiguration
from ovs.lib.vdisk import VDiskController
from timeout_decorator.timeout_decorator import TimeoutError
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException, FileExistsException, LocalStorageRouterClient,\
    MaxRedirectsExceededException, ObjectNotFoundException


class VolumedriverHealthCheck(object):
    """
    A healthcheck for the volumedriver components
    """
    MODULE = 'volumedriver'
    LOCAL_ID = System.get_my_machine_id()
    LOCAL_SR = System.get_my_storagerouter()
    VDISK_CHECK_SIZE = 1024 ** 3  # 1GB in bytes
    VDISK_HALTED_STATES = DataObject.enumerator('Halted_status', ['HALTED', 'FENCED'])
    VDISK_TIMEOUT_BEFORE_DELETE = 0.5
    # Only used to check status of a fenced volume. This should not be used to link a status of a non-halted/fenced volume
    FENCED_HALTED_STATUS_MAP = {'max_redirect': {'status': VDisk.STATUSES.NON_RUNNING,
                                                 'severity': 'failure',
                                                 'halted': ('These volumes are not running: {0}', ErrorCodes.volume_max_redirect),
                                                 'fenced': ('These volumes are fenced but not running on another node: {0}', ErrorCodes.volume_fenced_max_redirect)},
                                'halted': {'status': VDisk.STATUSES.HALTED,
                                           'severity': 'failure',
                                           'halted': ('These volumes are halted: {0}', ErrorCodes.volume_halted),
                                           'fenced': ('These volumes are fenced and but halted on another node: {0}', ErrorCodes.volume_fenced_halted)},
                                'connection_fail': {'status': 'UNKNOWN',
                                                    'severity': 'failure',
                                                    'halted': ('These volumes experienced a connectivity/timeout problem: {0}', ErrorCodes.voldrv_connection_problem),
                                                    'fenced': ('These volumes are fenced but experienced a connectivity/timeout problem on another node: {0}', ErrorCodes.voldrv_connection_problem)},
                                'ok': {'status': VDisk.STATUSES.RUNNING,
                                       'severity': 'failure',
                                       'halted': ('These volumes are running: {0}', ErrorCodes.volume_ok),
                                       'fenced': ('These volumes are fenced but running on another node: {0}', ErrorCodes.volume_fenced_ok)},
                                'not_found': {'status': 'NOT_FOUND',
                                              'severity': 'warning',
                                              'halted': ('These volumes could not be queried for information: {0}', ErrorCodes.volume_not_found),
                                              'fenced': ('These volumes are fenced but could not be queried for information on another node: {0}', ErrorCodes.volume_fenced_not_found)}}

    logger = Logger('healthcheck-ovs_volumedriver')

    @staticmethod
    @expose_to_cli(MODULE, 'dtl-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that all VDisks their DTL is properly running',
                   short_help='Test if DTL is properly running')
    def check_dtl(result_handler):
        """
        Checks the dtl for all vdisks on the local node
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        # Fetch vdisks hosted on this machine
        local_sr = System.get_my_storagerouter()
        if len(local_sr.vdisks_guids) == 0:
            return result_handler.skip('No VDisks present in cluster.')
        for vdisk_guid in local_sr.vdisks_guids:
            vdisk = VDisk(vdisk_guid)
            vdisk.invalidate_dynamics(['dtl_status', 'info'])
            if vdisk.dtl_status == 'ok_standalone' or vdisk.dtl_status == 'disabled':
                result_handler.success('VDisk {0}s DTL is disabled'.format(vdisk.name), code=ErrorCodes.volume_dtl_standalone)
            elif vdisk.dtl_status == 'ok_sync':
                result_handler.success('VDisk {0}s DTL is enabled and running.'.format(vdisk.name), code=ErrorCodes.volume_dtl_ok)
            elif vdisk.dtl_status == 'degraded':
                result_handler.warning('VDisk {0}s DTL is degraded.'.format(vdisk.name), code=ErrorCodes.volume_dtl_degraded)
            elif vdisk.dtl_status == 'checkup_required':
                result_handler.warning('VDisk {0}s DTL should be configured.'.format(vdisk.name), code=ErrorCodes.volume_dtl_checkup_required)
            elif vdisk.dtl_status == 'catch_up':
                result_handler.warning('VDisk {0}s DTL is enabled but still syncing.'.format(vdisk.name), code=ErrorCodes.volume_dtl_catch_up)
            else:
                result_handler.warning('VDisk {0}s DTL has an unknown status: {1}.'.format(vdisk.name, vdisk.dtl_status), code=ErrorCodes.volume_dtl_unknown)

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
    # @expose_to_cli(MODULE, 'volumedrivers-test', HealthCheckCLI.ADDON_TYPE,
    #                help='Verify that the Volumedrivers are responding to events',
    #                short_help='Test if Volumedrivers are responding to events')
    def check_volumedrivers(result_handler):
        """
        Checks if the VOLUMEDRIVERS work on a local machine (compatible with multiple vPools)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking volumedrivers.', add_to_result=False)
        vpools = VPoolList.get_vpools()
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

    @classmethod
    def _is_volumedriver_timeout(cls, exception):
        """
        Validates whether a certain exception is a timeout exception (RuntimeError, prior to NodeNotReachable in voldriver 6.17)
        :param exception: Exception object to check
        :return: True if it is a timeout or False if it's not
        :rtype: bool
        """
        return isinstance(exception, ClusterNotReachableException) or isinstance(exception, RuntimeError) and 'failed to send XMLRPC request' in str(exception)

    @classmethod
    @expose_to_cli(MODULE, 'halted-volumes-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that there are no halted/fenced volumes within the cluster',
                   short_help='Test if there  are no halted/fenced volumes')
    def check_for_halted_volumes(cls, result_handler):
        """
        Checks for halted volumes on a single or multiple vPools
        This will only check the volume states on the current node. If any other volumedriver would be down,
        only the HA'd volumes would pop-up as they could appear halted here (should be verified by the volumedriver team)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        vpools = VPoolList.get_vpools()
        local_sr = System.get_my_storagerouter()

        if len(vpools) == 0:
            result_handler.skip('No vPools found!'.format(len(vpools)), code=ErrorCodes.vpools_none)
            return
        for vpool in vpools:
            log_start = 'Halted volumes test vPool {0}'.format(vpool.name)
            if vpool.guid not in local_sr.vpools_guids:
                result_handler.skip('{0} - Skipping vPool {1} because it is not living here.'.format(log_start, vpool.name),
                                    code=ErrorCodes.vpool_not_local, add_to_result=False)
                continue

            result_handler.info('{0} - Retrieving all information'.format(log_start), add_to_result=False)
            storagedriver = None
            for std in vpool.storagedrivers:
                if std.storagerouter_guid == local_sr.guid:
                    storagedriver = std
                    break

            if storagedriver is None:
                result_handler.failure('{0} - Could not associate a StorageDriver with this StorageRouter'.format(log_start),
                                       code=ErrorCodes.std_no_str)
                continue

            volume_fenced_states = dict((key, []) for key in cls.FENCED_HALTED_STATUS_MAP.keys())
            volume_lists = {cls.VDISK_HALTED_STATES.HALTED: [], cls.VDISK_HALTED_STATES.FENCED: []}
            volume_states = {cls.VDISK_HALTED_STATES.HALTED: {cls.VDISK_HALTED_STATES.HALTED: volume_lists[cls.VDISK_HALTED_STATES.HALTED]},
                             cls.VDISK_HALTED_STATES.FENCED: volume_fenced_states}  # Less loops to write for outputting
            result_handler.info('{0} - Scanning for halted volumes'.format(log_start), add_to_result=False)
            try:
                voldrv_client = vpool.storagedriver_client
                objectregistry_client = vpool.objectregistry_client
            except Exception:
                cls.logger.exception('{0} - Unable to instantiate the required clients'.format(log_start))
                result_handler.exception('{0} - Unable to load the Volumedriver clients'.format(log_start),
                                         code=ErrorCodes.voldr_unknown_problem)
                continue
            try:
                # Listing all halted volumes with the volumedriver client as it detects stolen volumes too (fenced instances)
                volumes = voldrv_client.list_halted_volumes(str(storagedriver.storagedriver_id))
            except Exception as ex:
                cls.logger.exception('{0} - Exception occurred when listing volumes'.format(log_start))
                if cls._is_volumedriver_timeout(ex) is False:
                    # Unhandled exception at this point
                    result_handler.exception('{0} - Unable to list the Volumes due to an unidentified problem. Please check the logging'.format(log_start),
                                             code=ErrorCodes.voldr_unknown_problem)
                else:
                    result_handler.failure('{0} - Could not list the volumes for due to a connection problem.'.format(log_start),
                                           code=ErrorCodes.voldrv_connection_problem)
                continue
            # Retrieve the parent of the current volume. If this id would not be identical to the one we fetched for, that would mean it is fenced
            # Object registry goes to Arakoon
            # Capturing any possible that would occur to provide a clearer vision of what went wrong
            for volume in volumes:
                try:
                    registry_entry = objectregistry_client.find(volume)
                    if registry_entry.node_id() == storagedriver.storagedriver_id:
                        volume_lists[cls.VDISK_HALTED_STATES.HALTED].append(volume)
                    else:
                        # Fenced
                        volume_lists[cls.VDISK_HALTED_STATES.FENCED].append(volume)
                except Exception:
                    msg = '{0} - Unable to consult the object registry client for volume \'{1}\''.format(log_start, volume)
                    cls.logger.exception(msg)
                    result_handler.exception(msg, code=ErrorCodes.voldr_unknown_problem)
            # Include fenced - OTHER state combo
            for volume in volume_lists[cls.VDISK_HALTED_STATES.FENCED]:
                try:
                    _, state = cls._get_volume_issue(voldrv_client, volume, log_start)
                    volume_fenced_states[state].append(volume)
                except Exception:
                    # Only unhandled at this point
                    result_handler.exception('{0} - Unable to the volume info for volume {1} due to an unidentified problem. Please check the logging'.format(log_start, volume),
                                             code=ErrorCodes.voldr_unknown_problem)
            for halted_state, volume_state_info in volume_states.iteritems():
                for state, volumes in volume_state_info.iteritems():
                    if len(volumes) == 0:
                        continue  # Skip OK/empty lists
                    map_value = cls.FENCED_HALTED_STATUS_MAP[state.lower()]
                    log_func = getattr(result_handler, map_value['severity'])
                    message, code = map_value[halted_state.lower()]
                    log_func('{0} - {1}'.format(log_start, message.format(', '.join(volumes))), code=code)
            # Call success in case nothing is wrong
            if all(len(l) == 0 for l in volume_lists.values()):
                result_handler.success('{0} - No volumes found in halted/fenced state'.format(log_start))

    @classmethod
    def _get_volume_issue(cls, voldrv_client, volume_id, log_start):
        """
        Maps all possible exceptions to a state. These states can be mapped to a status using the FENCED_HALTED_STATUS_MAP
        because the volumedriver does not return a state itself
        :param voldrv_client: Storagedriver client
        :param volume_id: Id of the volume
        :raises: The unhandled exception when such an exception could occur (we try to identify all problems but one could slip past us)
        :return: The volume_id and state
        :rtype: tuple(str, str)
        """
        state = 'ok'
        try:
            # Check if the information can be retrieved about the volume
            vol_info = voldrv_client.info_volume(volume_id, req_timeout_secs=5)
            if vol_info.halted is True:
                state = 'halted'
        except Exception as ex:
            cls.logger.exception('{0} - Exception occurred when fetching the info for volume \'{1}\''.format(log_start, volume_id))
            if isinstance(ex, ObjectNotFoundException):
                # Ignore ovsdb invalid entrees as model consistency will handle it.
                state = 'not_found'
            elif isinstance(ex, MaxRedirectsExceededException):
                # This means the volume is not halted but detached or unreachable for the Volumedriver
                state = 'max_redirect'
            # @todo replace RuntimeError with NodeNotReachableException
            elif any(isinstance(ex, exception) for exception in [ClusterNotReachableException, RuntimeError]):
                if cls._is_volumedriver_timeout(ex) is False:
                    # Unhandled exception at this point
                    raise
                # Timeout / connection problems
                state = 'connection_fail'
            else:
                # Something to be looked at
                raise
        return volume_id, state

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
    # @expose_to_cli(MODULE, 'filedrivers-test', HealthCheckCLI.ADDON_TYPE,
    #                help='Verify that all Volumedrivers are accessible through FUSE',
    #                short_help='Test if that the FUSE layer is responding')
    # @todo replace fuse test with edge test
    def check_filedrivers(result_handler):
        """
        Checks if the file drivers work on a local machine (compatible with multiple vPools)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        """
        result_handler.info('Checking file drivers.', add_to_result=False)
        vpools = VPoolList.get_vpools()
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
    @expose_to_cli(MODULE, 'volume-potential-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that the Volumedrivers have enough VDisk potential left',
                   short_help='Test if the Volumedrivers can create enough VDisks')
    @expose_to_cli.option('--critical-vol-number', '-c', type=int, default=25, help='Minimum number of volumes left to create')
    def check_volume_potential(result_handler, critical_vol_number=25):
        """
        Checks all local storage drivers from a volume driver. Results in a success if enough volumes are available, a warning if the number of volumes is
        lower then a threshold value (critical_volume_number) and a failure if the nr of volumes ==0)
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param critical_vol_number: Mimimal number of volumes that can be made before throwing a warning
        :type critical_vol_number: int
        """
        result_handler.info('Checking volume potential of storagedrivers')

        if not isinstance(critical_vol_number, int) or critical_vol_number < 0:
            raise ValueError('Critical volume number should be a positive integer')

        for std in VolumedriverHealthCheck.LOCAL_SR.storagedrivers:
            try:
                std_config = StorageDriverConfiguration('storagedriver', std.vpool_guid, std.storagedriver_id)
                client = LocalStorageRouterClient(std_config.remote_path)
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

    @staticmethod
    @expose_to_cli(MODULE, 'sco-cache-mountpoint-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that sco-cache mountpoints are up and running',
                   short_help='Test if sco-cache mountpoints are up and running')
    def check_sco_cache_mountpoints(result_handler):
        """
        Iterates over StorageDrivers of a local StorageRouter and will check all its sco cache mount points.
        Will result in a warning log if the sco is in offline state
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        """
        result_handler.info('Checking sco cache mount points on all local storagedrivers')
        for std in VolumedriverHealthCheck.LOCAL_SR.storagedrivers:
            try:
                std_config = StorageDriverConfiguration('storagedriver', std.vpool_guid, std.storagedriver_id)
                client = LocalStorageRouterClient(std_config.remote_path)
                for std_info in client.sco_cache_mount_point_info(str(std.storagedriver_id)):
                    if std_info.offlined is True:
                        result_handler.warning('Mountpoint at location {0} of storagedriver {1} is in offline state'.format(std_info.path, std.storagedriver_id))
                    else:
                        result_handler.success('Mountpoint at location {0} of storagedriver {1} is in online state'.format(std_info.path, std.storagedriver_id))
            except RuntimeError:
                result_handler.exception('Unable to check sco cache mountpoint of storagedriver {0}'.format(std.storagedriver_id))


