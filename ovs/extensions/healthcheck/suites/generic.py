#!/usr/bin/python

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
Generic healthcheck module
"""
from __future__ import absolute_import

import os
import psutil
from ovs.dal.hybrids.storagerouter import StorageRouter
from ovs.dal.lists.domainlist import DomainList
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.config.error_codes import ErrorCodes
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLI
from ovs.extensions.healthcheck.helpers.filesystem import FilesystemHelper
from ovs.extensions.healthcheck.helpers.helper import Helper
from ovs.extensions.healthcheck.helpers.network import NetworkHelper
from ovs.extensions.healthcheck.helpers.rabbitmq import RabbitMQ
from ovs.extensions.packages.packagefactory import PackageFactory
from ovs.extensions.services.servicefactory import ServiceFactory
from ovs.lib.storagerouter import StorageRouterController
from timeout_decorator import timeout
from timeout_decorator.timeout_decorator import TimeoutError
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException


class OpenvStorageHealthCheck(object):
    """
    A healthcheck for the Open vStorage framework
    """
    MODULE = 'ovs'
    LOCAL_SR = System.get_my_storagerouter()
    LOCAL_ID = System.get_my_machine_id()

    CELERY_CHECK_TIME = 7

    @staticmethod
    @expose_to_cli(MODULE, 'log-files-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that all log files are not too big',
                   short_help='Test if log files are not too big')
    @expose_to_cli.option('--max-log-size', '-m', type=float, default=Helper.max_log_size, help='Maximum size of the file (in MB)')
    def check_size_of_log_files(result_handler, max_log_size=Helper.max_log_size):
        """
        Checks the size of the initialized log files
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param max_log_size: maximum log size of a log file (in MB)
        :type max_log_size: double
        :return: None
        :rtype: NoneType
        """
        def get_log_files_by_path(start_path, recursive=True):
            files_to_check = []
            for entry in os.listdir(start_path):
                entry_path = '{0}/{1}'.format(start_path, entry)
                if os.path.isdir(entry_path) and recursive is True:
                    files_to_check.extend(get_log_files_by_path(entry_path))
                elif entry.endswith('.log'):
                    files_to_check.append(entry_path)
            return files_to_check

        good_size = []
        too_big = []
        result_handler.info('Checking if log files their size is not bigger than {0} MB: '.format(max_log_size), add_to_result=False)

        for c_files in get_log_files_by_path('/var/log/'):
            # check if logfile is larger than max_size
            if os.stat(c_files).st_size < 1024 ** 2 * max_log_size:
                good_size.append(c_files)
                result_handler.success('Logfile {0} size is fine!'.format(c_files), code=ErrorCodes.log_file_size)
            else:
                too_big.append(c_files)
                result_handler.warning('Logfile {0} is larger than {1} MB!'.format(c_files, max_log_size), code=ErrorCodes.log_file_size)

        if len(too_big) != 0:
            result_handler.warning('The following log files are too big: {0}.'.format(', '.join(too_big)), code=ErrorCodes.log_file_size)
        else:
            result_handler.success('All log files are ok!', code=ErrorCodes.log_file_size)

    @staticmethod
    @expose_to_cli(MODULE, 'port-ranges-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that there are enough ports remaining for OVS use',
                   short_help='Test if there are enough ports remaining')
    @expose_to_cli.option('--minimal_port_amount', '-m', type=int, default=20, help='Minimal number of ports')
    def check_port_ranges(result_handler, minimal_port_amount=20):
        """
        Checks whether the expected amount of ports is available for the requested amount of ports
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param minimal_port_amount: minimal number of ports without warning
        :type minimal_port_amount: int
        :return: None
        :rtype: NoneType
        """
        # @todo: check other port ranges too
        port_range = Configuration.get('/ovs/framework/hosts/{0}/ports|storagedriver'.format(OpenvStorageHealthCheck.LOCAL_ID))
        expected_ports = System.get_free_ports(selected_range=port_range, amount=0)
        result_handler.info('Checking if enough ports are still available for OpenvStorage')
        if len(expected_ports) >= minimal_port_amount:
            result_handler.success('{} ports free'.format(len(expected_ports)))
        else:
            result_handler.warning('{} ports found, less than {}'.format(len(expected_ports), minimal_port_amount))

    @staticmethod
    @expose_to_cli(MODULE, 'nginx-ports-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that NGINX is reachable',
                   short_help='Test if NGINX is reachable')
    def check_nginx_ports(result_handler):
        """
        Checks if this node can connect to it's own Nginx
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        return OpenvStorageHealthCheck._check_extra_ports(result_handler, 'nginx')

    @staticmethod
    @expose_to_cli(MODULE, 'memcached-ports-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that memcached is reachable',
                   short_help='Test if memcached is reachable')
    def check_memcached_ports(result_handler):
        """
        Checks the connection of this node to all Memcached endpoints
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        memcached_ips = [endpoint.rsplit(':')[0] for endpoint in Configuration.get('ovs/framework/memcache|endpoints', default=[])]
        return OpenvStorageHealthCheck._check_extra_ports(result_handler, 'memcached', ips=memcached_ips)

    @staticmethod
    def _check_extra_ports(result_handler, key, ips=None):
        """
        Checks the extra ports for key specified in the settings.json
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param key: check all ports for this key
        :type key: string
        :param ips: IPs to check the port on. Default the local IP
        :type ips: list
        :return: None
        :rtype: NoneType
        """
        if ips is None:
            ips = [OpenvStorageHealthCheck.LOCAL_SR.ip]
        result_handler.info('Checking {0} ports'.format(key), add_to_result=False)
        if key not in Helper.extra_ports:
            raise RuntimeError('Settings.json is incorrect! The extra ports to check do not have {0}'.format(key))
        for port in Helper.extra_ports[key]:
            for ip in ips:
                result_handler.info('Checking socket {0}:{1} of service {2}.'.format(ip, port, key), add_to_result=False)
                result = NetworkHelper.check_port_connection(port, ip)
                if result:
                    result_handler.success('Connection successfully established to service {0} on {1}:{2}'.format(key, ip, port), code=getattr(ErrorCodes, 'port_{0}'.format(key)))
                else:
                    result_handler.failure('Connection FAILED to service {0} on {1}:{2}'.format(key, ip, port), code=getattr(ErrorCodes, 'port_{0}'.format(key)))

    @staticmethod
    @expose_to_cli(MODULE, 'celery-ports-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that RabbitMQ is reachable',
                   short_help='Test if RabbitMQ is reachable')
    def check_rabbitmq_ports(result_handler):
        """
        Checks all ports of Open vStorage components rabbitMQ and celery
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        # Check Celery and RabbitMQ
        if OpenvStorageHealthCheck.LOCAL_SR.node_type != 'MASTER':
            result_handler.skip('RabbitMQ is not running/active on this server!')
            return
        result_handler.info('Checking Celery.', add_to_result=False)
        from errno import errorcode
        try:
            # noinspection PyUnresolvedReferences
            from celery.task.control import inspect
            stats = inspect().stats()
            if stats:
                result_handler.success('Successfully connected to Celery on all nodes.', code=ErrorCodes.port_celery)
            else:
                result_handler.failure('No running Celery workers were found.', code=ErrorCodes.port_celery)
        except IOError as ex:
            msg = 'Could not connect to Celery. Got {0}.'.format(ex)
            if len(ex.args) > 0 and errorcode.get(ex.args[0]) == 'ECONNREFUSED':
                msg += ' Check that the RabbitMQ server is running.'
                result_handler.failure(msg, code=ErrorCodes.port_celery)
        except ImportError as ex:
            result_handler.failure('Could not import the celery module. Got {}'.format(str(ex)), code=ErrorCodes.port_celery)

    @staticmethod
    @expose_to_cli(MODULE, 'packages-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that all required packages are installed',
                   short_help='Test if all required packages are installed')
    def check_ovs_packages(result_handler):
        """
        Checks the availability of packages for Open vStorage
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking OVS packages: ', add_to_result=False)
        client = SSHClient(OpenvStorageHealthCheck.LOCAL_SR)
        package_manager = PackageFactory.get_manager()
        # Get all base packages
        base_packages = set()
        for names in package_manager.package_info['names'].itervalues():
            base_packages = base_packages.union(names)
        base_packages = list(base_packages)
        extra_packages = Helper.packages
        installed = package_manager.get_installed_versions(client=client, package_names=base_packages)
        installed.update(package_manager.get_installed_versions(client=client, package_names=Helper.packages))
        for package in base_packages + extra_packages:
            version = installed.get(package)
            if version:
                version = str(version)
                result_handler.success('Package {0} is installed with version {1}'.format(package, version),
                                       code=ErrorCodes.package_required)
            else:
                if package in package_manager.package_info['mutually_exclusive']:
                    # Mutually exclusive package, so ignore
                    continue
                if package in base_packages:
                    result_handler.warning('Package {0} is not installed.'.format(package),
                                           code=ErrorCodes.package_required)
                elif package in extra_packages:
                    result_handler.skip('Package {0} is not installed.'.format(package))

    @staticmethod
    @expose_to_cli(MODULE, 'processes-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that all OVS related processes are running',
                   short_help='Test if OVS processes are running')
    def check_ovs_processes(result_handler):
        """
        Checks the availability of processes for Open vStorage
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking local ovs services.')
        client = SSHClient(System.get_my_storagerouter())
        service_manager = ServiceFactory.get_manager()
        services = [service for service in service_manager.list_services(client=client) if service.startswith(OpenvStorageHealthCheck.MODULE)]
        if len(services) == 0:
            result_handler.warning('Found no local ovs services.')
        for service_name in services:
            if service_manager.get_service_status(service_name, client) == 'active':
                result_handler.success('Service {0} is running!'.format(service_name), code=ErrorCodes.process_fwk)
            else:
                result_handler.failure('Service {0} is not running, please check this.'.format(service_name), code=ErrorCodes.process_fwk)

    @staticmethod
    @timeout(CELERY_CHECK_TIME)
    def _check_celery():
        """
        Preliminary/Simple check for Celery and RabbitMQ component
        """
        # try if celery works smoothly
        try:
            machine_id = OpenvStorageHealthCheck.LOCAL_SR.machine_id
            obj = StorageRouterController.get_support_info.s().apply_async(routing_key='sr.{0}'.format(machine_id)).get()
        except TimeoutError as ex:
            raise TimeoutError('{0}: Process is taking to long!'.format(ex.value))
        if obj:
            return True
        else:
            return False

    @staticmethod
    @expose_to_cli(MODULE, 'workers-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that the ovs-workers are working',
                   short_help='Test if the ovs-workers are working')
    def check_ovs_workers(result_handler):
        """
        Extended check of the Open vStorage workers; When the simple check fails, it will execute a full/deep check.
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking if OVS-WORKERS are running smoothly.', add_to_result=False)
        # Checking celery
        try:
            # Basic celery check
            OpenvStorageHealthCheck._check_celery()
            result_handler.success('The OVS-WORKERS are working smoothly!', code=ErrorCodes.process_celery_timeout)
        except TimeoutError:
            # Apparently the basic check failed, so we are going crazy
            result_handler.failure('The test timed out after {0}s! Is RabbitMQ and ovs-workers running?'.format(OpenvStorageHealthCheck.CELERY_CHECK_TIME), code=ErrorCodes.process_celery_timeout)
        except Exception as ex:
            result_handler.failure('The celery check has failed with {0}'.format(str(ex)), code=ErrorCodes.process_celery_timeout)

    @staticmethod
    @expose_to_cli(MODULE, 'directories-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that all OVS related directories have correct ownership and rights',
                   short_help='Test if directories their ownership and rights are correct')
    def check_required_dirs(result_handler):
        """
        Checks the directories their rights and owners for mistakes
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking if owner rights are set correctly on certain directories.', add_to_result=False)
        for dirname, owner_settings in Helper.owners_files.iteritems():
            # check if directory/file exists
            if os.path.exists(dirname):
                if owner_settings.get('user') == FilesystemHelper.get_owner_of_file(dirname) \
                        and owner_settings.get('group') == FilesystemHelper.get_group_of_file(dirname):
                    result_handler.success('Directory {0} has correct owners!'.format(dirname), code=ErrorCodes.directory_ownership_incorrect)
                else:
                    result_handler.warning('Directory {0} has INCORRECT owners! It must be OWNED by USER={1} and GROUP={2}'.format(dirname, owner_settings.get('user'), owner_settings.get('group')),
                                           code=ErrorCodes.directory_ownership_incorrect)
            else:
                result_handler.skip('Directory {0} does not exists!'.format(dirname))

        result_handler.info('Checking if Rights are set correctly on certain maps.', add_to_result=False)
        for dirname, rights in Helper.rights_dirs.iteritems():
            # check if directory/file exists
            if os.path.exists(dirname):
                if FilesystemHelper.check_rights_of_file(dirname, rights):
                    result_handler.success('Directory {0} has correct rights!'.format(dirname), code=ErrorCodes.directory_rights_incorrect)
                else:
                    result_handler.warning('Directory {0} has INCORRECT rights! It must be CHMOD={1} '.format(dirname, rights),
                                           code=ErrorCodes.directory_rights_incorrect)
            else:
                result_handler.skip('Directory {0} does not exists!'.format(dirname))

    @staticmethod
    @expose_to_cli(MODULE, 'dns-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that the node can resolve DNS names',
                   short_help='Test if the node can resolve DNS names')
    def check_if_dns_resolves(result_handler, fqdn='google.com'):
        """
        Checks if DNS resolving works on a local machine
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param fqdn: the absolute pathname of the file
        :type fqdn: str
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking DNS resolving.', add_to_result=False)
        result = NetworkHelper.check_if_dns_resolves(fqdn)
        if result is True:
            result_handler.success('DNS resolving works!', code=ErrorCodes.dns_resolve_fail)
        else:
            result_handler.warning('DNS resolving doesnt work, please check /etc/resolv.conf or add correct DNS server and make it immutable: "sudo chattr +i /etc/resolv.conf"!',
                                   code=ErrorCodes.dns_resolve_fail)

    @staticmethod
    @expose_to_cli(MODULE, 'zombie-processes-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that no zombie processes are running on the machine',
                   short_help='Test if there are zombie processes running')
    def check_zombied_and_dead_processes(result_handler):
        """
        Finds zombie or dead processes on a local machine
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        zombie_processes = []
        dead_processes = []

        result_handler.info('Checking for zombie/dead processes.', add_to_result=False)

        # Check for zombie'd and dead processes
        for proc in psutil.process_iter():
            try:
                pinfo = proc.as_dict(attrs=['pid', 'name', 'status'])
            except psutil.NoSuchProcess:
                pass
            else:
                if pinfo.get('status') == psutil.STATUS_ZOMBIE:
                    zombie_processes.append('{0}({1})'.format(pinfo.get('name'), pinfo.get('pid')))

                if pinfo.get('status') == psutil.STATUS_DEAD:
                    dead_processes.append('{0}({1})'.format(pinfo.get('name'), pinfo.get('pid')))

        # Check if there zombie processes
        if len(zombie_processes) == 0:
            result_handler.success('There are no zombie processes on this node!', code=ErrorCodes.process_zombie_found)
        else:
            result_handler.warning('We DETECTED zombie processes on this node: {0}'.format(', '.join(zombie_processes)),
                                   code=ErrorCodes.process_zombie_found)

        # Check if there dead processes
        if len(dead_processes) == 0:
            result_handler.success('There are no dead processes on this node!', code=ErrorCodes.process_dead_found)
        else:
            result_handler.warning('We DETECTED dead processes on this node: {0}'.format(', '.join(dead_processes)),
                                   code=ErrorCodes.process_dead_found)

    @staticmethod
    @expose_to_cli(MODULE, 'model-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that the Framework model is in sync with the one from the Volumedriver',
                   short_help='Test if Framework and Volumedriver model match')
    def check_model_consistency(result_handler):
        """
        Checks if the model consistency of OVSDB vs. VOLUMEDRIVER and does a preliminary check on RABBITMQ
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking model consistency: ')

        # Checking consistency of volumedriver vs. ovsdb and backwards
        for vp in VPoolList.get_vpools():
            if vp.guid not in OpenvStorageHealthCheck.LOCAL_SR.vpools_guids:
                result_handler.skip('Skipping vPool {0} because it is not living here.'.format(vp.name))
                continue
            result_handler.info('Checking consistency of volumedriver vs. ovsdb for {0}: '.format(vp.name), add_to_result=False)
            missing_in_volumedriver = []
            missing_in_model = []
            try:
                # noinspection PyArgumentList
                voldrv_volume_list = vp.storagedriver_client.list_volumes()
            except (ClusterNotReachableException, RuntimeError) as ex:
                result_handler.warning('Seems like the volumedriver {0} is not running. Got {1}'.format(vp.name, str(ex)),
                                       code=ErrorCodes.voldrv_connection_problem)
                continue

            vdisk_volume_ids = []
            # Cross-reference model vs. volumedriver
            for vdisk in vp.vdisks:
                vdisk_volume_ids.append(vdisk.volume_id)
                if vdisk.volume_id not in voldrv_volume_list:
                    missing_in_volumedriver.append(vdisk.guid)
                else:
                    voldrv_volume_list.remove(vdisk.volume_id)
            # Cross-reference volumedriver vs. model
            for voldrv_id in voldrv_volume_list:
                if voldrv_id not in vdisk_volume_ids:
                    missing_in_model.append(voldrv_id)

            # Display discrepancies for vPool
            if len(missing_in_volumedriver) != 0:
                result_handler.warning('Detected volumes that are MISSING in volumedriver but are in ovsdb in vpool: {0} - vdisk guid(s):{1}.'
                                       .format(vp.name, ' '.join(missing_in_volumedriver)),
                                       code=ErrorCodes.missing_volumedriver)
            else:
                result_handler.success('No discrepancies found for ovsdb in vPool {0}'.format(vp.name), code=ErrorCodes.missing_volumedriver)

            if len(missing_in_model) != 0:
                result_handler.warning('Detected volumes that are AVAILABLE in volumedriver but are not in ovsdb in vpool: {0} - vdisk volume id(s):{1}'
                                       .format(vp.name, ', '.join(missing_in_model)),
                                       code=ErrorCodes.missing_ovsdb)
            else:
                result_handler.success('No discrepancies found for voldrv in vpool {0}'.format(vp.name), code=ErrorCodes.missing_ovsdb)

    @staticmethod
    @expose_to_cli(MODULE, 'verify-rabbitmq-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that RabbitMQ is properly running',
                   short_help='Test if RabbitMQ is properly running')
    def verify_rabbitmq(result_handler):
        """
        Verify rabbitmq
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        # RabbitMQ check: cluster verification
        result_handler.info('Pre-check: verification of RabbitMQ cluster.', add_to_result=False)
        if OpenvStorageHealthCheck.LOCAL_SR.node_type == 'MASTER':
            r = RabbitMQ(ip=OpenvStorageHealthCheck.LOCAL_SR.ip)
            partitions = r.partition_status()
            if len(partitions) == 0:
                result_handler.success('RabbitMQ has no partition issues!', code=ErrorCodes.process_rabbit_mq)
            else:
                result_handler.failure('RabbitMQ has partition issues: {0}'.format(', '.join(partitions)), code=ErrorCodes.process_rabbit_mq)
        else:
            result_handler.skip('RabbitMQ is not running/active on this server!')

    @staticmethod
    @expose_to_cli(MODULE, 'recovery-domain-test', HealthCheckCLI.ADDON_TYPE,
                   help='Verify that all recovery domains are setup as regular domain',
                   short_help='Test if all recovery domains are setup as regular domain')
    def check_recovery_domains(result_handler):
        result_handler.info('Checking recovery domains:')
        prim_domains = [domain.name for domain in DomainList.get_domains() if len(domain.storage_router_layout['regular']) >= 1]
        for domain in DomainList.get_domains():
            layout = domain.storage_router_layout
            recovery = layout['recovery']
            regular = layout['regular']
            # Check recovery usage
            if len(recovery) >= 1 and domain.name not in prim_domains:
                sr_ips = ', '.join([StorageRouter(guid).ip for guid in recovery])
                result_handler.warning('Domain {0} set as recovery domain on storagerouter(s) {1}, but nowhere as regular domain'.format(domain.name, sr_ips))
            else:
                result_handler.info('Domain {0} passed test, set {1} time(s) as regular domain'.format(domain.name, len(regular)))

            # Check for double usage
            intersection = set(recovery).intersection(regular)
            if intersection:
                sr_ips = ', '.join([StorageRouter(guid).ip for guid in intersection])
                result_handler.warning('Recovery domain {0} is also found to be a regular domain in {1}.'.format(domain.name, sr_ips))
