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

import os
import grp
import glob
import psutil
import socket
import commands
import timeout_decorator
from pwd import getpwuid
from subprocess import CalledProcessError
from timeout_decorator.timeout_decorator import TimeoutError
from ovs.extensions.generic.configuration import NotFoundException
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.decorators import expose_to_cli
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.healthcheck.helpers.helper import Helper
from ovs.extensions.healthcheck.helpers.init_manager import InitManager
from ovs.extensions.healthcheck.helpers.rabbitmq import RabbitMQ
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.storagedriver import StoragedriverHelper
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper
from ovs.lib.storagerouter import StorageRouterController
from volumedriver.storagerouter import storagerouterclient as src
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException


class OpenvStorageHealthCheck(object):
    """
    A healthcheck for the Open vStorage framework
    """
    MODULE = 'openvstorage'
    LOCAL_SR = System.get_my_storagerouter()
    LOCAL_ID = System.get_my_machine_id()

    @staticmethod
    @expose_to_cli('ovs', 'local-settings-test')
    def get_local_settings(logger):
        """
        Fetch settings of the local Open vStorage node

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        ovs_version = Helper.get_ovs_version()

        logger.info('Fetching LOCAL information of node: ')
        # Fetch all details
        try:
            logger.info('Cluster ID: {0}'.format(Helper.get_cluster_id()))
            logger.info('Hostname: {0}'.format(socket.gethostname()))
            logger.info('Storagerouter ID: {0}'.format(OpenvStorageHealthCheck.LOCAL_ID))
            logger.info('Storagerouter TYPE: {0}'.format(OpenvStorageHealthCheck.LOCAL_SR.node_type))
            logger.info('Environment RELEASE: {0}'.format(ovs_version[0]))
            logger.info('Environment BRANCH: {0}'.format(ovs_version[1].title()))
            logger.info('Environment OS: {0}'.format(Helper.check_os()))
            logger.success('Fetched all local settings', 'local-settings')
        except (CalledProcessError, NotFoundException, IOError) as ex:
            logger.failure('Could not fetch local-settings. Got {0}'.format(ex.message), 'local-settings')

    @staticmethod
    @expose_to_cli('ovs', 'log-files-test')
    def check_size_of_log_files(logger):
        """
        Checks the size of the initialized log files

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        collection = []
        good_size = []
        too_big = []

        logger.info('Checking if log files their size is not bigger than {0} MB: '.format(Helper.max_log_size),
                    'checkLogfilesSize')

        # collect log files
        for log, settings in Helper.check_logs.iteritems():
            if settings.get('type') != 'dir':
                # check if filename exists
                if os.path.exists(log):
                    collection.append(log)
                continue
            # check if dirname exists
            if os.path.isdir(log) is False:
                continue
            # check if dirname contains files
            files = OpenvStorageHealthCheck._list_logs_in_directory(log)
            # check if given dirname has files
            for filename in files:
                if settings.get('prefix'):
                    for prefix in list(settings.get('prefix')):
                        if prefix in filename:
                            collection.append(filename)
                else:
                    collection.append(filename)

            # check if has nested_dirs and nested_files
            if not settings.get('contains_nested'):
                continue
            nested_dirs = OpenvStorageHealthCheck._list_dirs_in_directory(log)
            for dirname in nested_dirs:
                nested_files = OpenvStorageHealthCheck._list_logs_in_directory(log+"/"+dirname)
                # check size of log files
                for nested_file in nested_files:
                    if settings.get('prefix'):
                        for prefix in list(settings.get('prefix')):
                            if prefix in nested_file:
                                collection.append(nested_file)
                    else:
                        collection.append(nested_file)

        # process log files
        for c_files in collection:
            # check if logfile is larger than max_size
            if os.stat(c_files).st_size < 1024000 * Helper.max_log_size:
                good_size.append(c_files)
                logger.success('Logfile {0} has a GOOD size!'.format(c_files))
            else:
                too_big.append(c_files)
                logger.failure('Logfile {0} is a BIG logfile!'.format(c_files))

        if len(too_big) != 0:
            logger.failure('Some log files are TOO BIG, please check these files {0}!'.format(', '.join(too_big)),
                           'log_size')
        else:
            logger.success('ALL log files are ok!', 'log_size')

    @staticmethod
    def _list_logs_in_directory(pwd):
        """
        lists the log files in a certain directory

        :param pwd: absolute location of a directory (e.g. /var/log)
        :type pwd: str
        :return: list of files
        :rtype: list
        """

        return glob.glob('{0}/*.log'.format(pwd))

    @staticmethod
    def _list_dirs_in_directory(pwd):
        """
        lists the directories in a certain directory

        :param pwd: absolute location of a directory (e.g. /var/log)
        :type pwd: str
        :return: list of directories
        :rtype: list
        """

        return next(os.walk(pwd))[1]

    @staticmethod
    def _is_port_listening(logger, process_name, port, ip=LOCAL_SR.ip):
        """
        Checks the port connection of a process

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param process_name: name of a certain process running on this local machine
        :type process_name: str
        :param port: port where the service is running on
        :type port: int
        :param ip: ip address to try
        :type ip: str
        """
        logger.info('Checking port {0} of service {1} ...'.format(port, process_name), '_is_port_listening')
        if Helper.check_port_connection(port, ip):
            logger.success('Connection successfully established!',
                           'port_{0}_{1}'.format(process_name, port))
        else:
            logger.failure('Connection FAILED to service {1} on port {0}'.format(port, process_name),
                           'port_{0}_{1}'.format(process_name, port))

    @staticmethod
    @expose_to_cli('ovs', 'required-ports-test')
    def check_required_ports(logger):
        """
        Checks all ports of Open vStorage components (framework, memcached, nginx, rabbitMQ and celery)

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info('Checking PORT CONNECTIONS of OVS & EXTRA services ...', '')

        # check ports for OVS services
        logger.info('Checking OVS ports')
        for sr in ServiceHelper.get_local_services():
            for port in sr.ports:
                if sr.name.split('_')[0] == 'albaproxy':
                    storagedriver_id = "{0}{1}".format(sr.name.split('_')[1], OpenvStorageHealthCheck.MACHINE_ID)
                    ip = StoragedriverHelper.get_by_storagedriver_id(storagedriver_id).storage_ip
                    OpenvStorageHealthCheck._is_port_listening(logger, sr.name, port, ip)
                else:
                    OpenvStorageHealthCheck._is_port_listening(logger, sr.name, port)
        # check NGINX and memcached
        logger.info('Checking EXTRA ports', '')
        for process, ports in Helper.extra_ports.iteritems():
            for port in ports:
                OpenvStorageHealthCheck._is_port_listening(logger, process, port)

        # Check Celery and RabbitMQ
        logger.info('Checking RabbitMQ/Celery.', '')
        if Helper.get_ovs_type() == 'MASTER':
            pcommand = 'celery inspect ping -b amqp://ovs:0penv5tor4ge@{0}//'.format(OpenvStorageHealthCheck.LOCAL_SR.ip)
            pcel = commands.getoutput(pcommand.format(pcommand)).splitlines()
            if len(pcel) != 1 and 'pong' in pcel[1].strip():
                logger.success('Connection successfully established!', 'port_celery')
            else:
                logger.failure('Connection FAILED to service Celery, please check RabbitMQ and ovs-workers?',
                               'port_celery')
        else:
            logger.skip('RabbitMQ is not running/active on this server!', 'port_celery')

    @staticmethod
    @expose_to_cli('ovs', 'packages-test')
    def check_ovs_packages(logger):
        """
        Checks the availability of packages for Open vStorage

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info('Checking OVS packages: ', 'check_ovs_packages')

        for package in Helper.packages:
            result = commands.getoutput('apt-cache policy {0}'.format(package)).splitlines()
            if len(result) != 1:
                logger.success(
                    'Package {0} is present, with version {1}'.format(package, result[2].split(':')[1].strip()),
                    'package_{0}'.format(package))
            else:
                logger.skip('Package {0} is NOT present ...'.format(package),
                            'package_{0}'.format(package))

    @staticmethod
    @expose_to_cli('ovs', 'processes-test')
    def check_ovs_processes(logger):
        """
        Checks the availability of processes for Open vStorage

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        test_name = 'check_ovs_processes'
        logger.info('Checking LOCAL OVS services: ', test_name)
        services = InitManager.get_local_services(prefix='ovs', ip=OpenvStorageHealthCheck.LOCAL_SR.ip)
        if len(services) > 0:
            for service_name in services:
                if InitManager.service_running(service_name=service_name, ip=OpenvStorageHealthCheck.LOCAL_SR.ip):
                    logger.success('Service {0} is running!'.format(service_name),
                                   'process_{0}'.format(service_name))
                else:
                    logger.failure('Service {0} is NOT running, please check this... '.format(service_name),
                                   'process_{0}'.format(service_name))
        else:
            logger.failure('Found no LOCAL OVS services', test_name)

    @staticmethod
    @timeout_decorator.timeout(7)
    def _check_celery():
        """
        Preliminary/Simple check for Celery and RabbitMQ component
        """

        # try if celery works smoothly
        try:
            guid = OpenvStorageHealthCheck.LOCAL_SR.guid
            machine_id = OpenvStorageHealthCheck.LOCAL_SR.machine_id
            obj = StorageRouterController.get_support_info.s(guid).apply_async(routing_key='sr.{0}'.format(machine_id)).get()
        except TimeoutError as ex:
            raise TimeoutError('{0}: Process is taking to long!'.format(ex.value))

        if obj:
            return True
        else:
            return False

    @staticmethod
    @expose_to_cli('ovs', 'ovs-workers-test')
    def check_ovs_workers(logger):
        """
        Extended check of the Open vStorage workers; When the simple check fails, it will execute a full/deep check.

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info('Checking if OVS-WORKERS are running smoothly: ', 'process_celery')

        # checking celery
        try:
            # basic celery check
            OpenvStorageHealthCheck._check_celery()
            logger.success('The OVS-WORKERS are working smoothly!', 'process_celery')
        except TimeoutError:
            # apparently the basic check failed, so we are going crazy
            logger.failure('Error during check of celery! Is RabbitMQ and ovs-workers running?', 'process_celery')

    @staticmethod
    @expose_to_cli('ovs', 'directories-test')
    def check_required_dirs(logger):
        """
        Checks the directories their rights and owners for mistakes

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info('Checking if OWNERS are set correctly on certain maps: ', 'checkRequiredMaps_owners')
        for dirname, owner_settings in Helper.owners_files.iteritems():
            # check if directory/file exists
            if os.path.exists(dirname):
                if owner_settings.get('user') == OpenvStorageHealthCheck._get_owner_of_file(dirname) \
                        and owner_settings.get('group') == OpenvStorageHealthCheck._get_group_of_file(dirname):
                    logger.success('Directory {0} has correct owners!'.format(dirname), 'dir_{0}'.format(dirname))
                else:
                    logger.failure(
                        'Directory {0} has INCORRECT owners! It must be OWNED by USER={1} and GROUP={2}'
                        .format(dirname, owner_settings.get('user'), owner_settings.get('group')),
                        'dir_{0}'.format(dirname))
            else:
                logger.skip('Directory {0} does not exists!'.format(dirname), 'dir_{0}'.format(dirname))

        logger.info('Checking if Rights are set correctly on certain maps: ', 'checkRequiredMaps_rights')
        for dirname, rights in Helper.rights_dirs.iteritems():
            # check if directory/file exists
            if os.path.exists(dirname):
                if OpenvStorageHealthCheck._check_rights_of_file(dirname, rights):
                    logger.success('Directory {0} has correct rights!'.format(dirname),
                                   'dir_{0}'.format(dirname))
                else:
                    logger.failure('Directory {0} has INCORRECT rights! It must be CHMOD={1} '
                                   .format(dirname, rights), 'dir_{0}'.format(dirname))
            else:
                logger.skip('Directory {0} does not exists!'.format(dirname), 'dir_{0}'.format(dirname))

        return True

    @staticmethod
    def _get_owner_of_file(filename):
        """
        Gets the OWNER of a certain file

        :param filename: the absolute pathname of the file
        :type filename: str
        :return: owner name of a file
        :rtype: str
        """

        return getpwuid(os.stat(filename).st_uid).pw_name

    @staticmethod
    def _get_group_of_file(filename):
        """
        Gets the GROUP of a certain file

        :param filename: the absolute pathname of the file
        :type filename: str
        :return: group of a file
        :rtype: str
        """

        return grp.getgrgid(os.stat(filename).st_gid).gr_name

    @staticmethod
    def _check_rights_of_file(filename, rights):
        """
        Checks if there are RIGHTS mistakes in a certain file

        :param filename: the absolute pathname of the file
        :type filename: str
        :param rights: the correct rights that the file needs to have
        :type rights: str
        :return: True if the rights are correct; False if they are wrong
        :rtype: bool
        """

        # fetch file to start compare
        st = os.stat(filename)
        return oct(st.st_mode)[-3:] == str(rights)

    @staticmethod
    @expose_to_cli('ovs', 'dns-test')
    def check_if_dns_resolves(logger, fqdn="google.com"):
        """
        Checks if DNS resolving works on a local machine

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param fqdn: the absolute pathname of the file
        :type fqdn: str
        :return: True if the DNS resolving works; False it doesn't work
        :rtype: bool
        """

        logger.info('Checking DNS resolving: ', 'titleDnsResolving')
        try:
            socket.gethostbyname(fqdn)
            logger.success('DNS resolving works!', 'dns_resolving')
            return True
        except Exception:
            logger.failure('DNS resolving doesnt work, please check /etc/resolv.conf or add correct DNS server and make it immutable: "sudo chattr +i /etc/resolv.conf"!',
                           'dns_resolving')
            return False

    @staticmethod
    @expose_to_cli('ovs', 'zombie-processes-test')
    def get_zombied_and_dead_processes(logger):
        """
        Finds zombie or dead processes on a local machine

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        zombie_processes = []
        dead_processes = []

        logger.info('Checking for zombie/dead processes: ', 'checkForZombieProcesses')

        # check for zombie'd and dead processes
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

        # check if there zombie processes
        if len(zombie_processes) == 0:
            logger.success('There are NO zombie processes on this node!', 'process_zombies')
        else:
            logger.warning('We DETECTED zombie processes on this node: {0}'.format(', '.join(zombie_processes)),
                           'process_zombies')

        # check if there dead processes
        if len(dead_processes) == 0:
            logger.success('There are NO dead processes on this node!', 'process_dead')
        else:
            logger.failure('We DETECTED dead processes on this node: {0}'.format(', '.join(dead_processes)),
                           'process_dead')

    @staticmethod
    @expose_to_cli('ovs', 'model-test')
    def check_model_consistency(logger):
        """
        Checks if the model consistency of OVSDB vs. VOLUMEDRIVER and does a preliminary check on RABBITMQ

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info('Checking model consistency: ', 'check_model_consistency')

        # RabbitMQ check: cluster verification
        logger.info('Pre-check: verification of RabbitMQ cluster: ', 'checkRabbitMQcluster')
        if Helper.get_ovs_type() == 'MASTER':
            r = RabbitMQ(ip=OpenvStorageHealthCheck.LOCAL_SR.ip)
            partitions = r.partition_status()
            if len(partitions) == 0:
                logger.success('RabbitMQ has no partition issues!',
                               'process_rabbitmq')
            else:
                logger.failure('RabbitMQ has partition issues: {0}'.format(', '.join(partitions)),
                               'process_rabbitmq')
        else:
            logger.skip('RabbitMQ is not running/active on this server!',
                        'process_rabbitmq')
        # Checking consistency of volumedriver vs. ovsdb and backwards
        for vp in VPoolHelper.get_vpools():
            if vp.guid not in OpenvStorageHealthCheck.LOCAL_SR.vpools_guids:
                logger.skip('Skipping vPool {0} because it is not living here ...'.format(vp.name), 'discrepancies_voldrv_{0}'.format(vp.name))
                continue
            logger.info('Checking consistency of volumedriver vs. ovsdb for vPool {0}: '.format(vp.name))
            missing_in_volumedriver = []
            missing_in_model = []
            config_file = Configuration.get_configuration_path('/ovs/vpools/{0}/hosts/{1}/config'.format(vp.guid, vp.storagedrivers[0].name))
            try:
                voldrv_client = src.LocalStorageRouterClient(config_file)
                # noinspection PyArgumentList
                voldrv_volume_list = voldrv_client.list_volumes()
            except (ClusterNotReachableException, RuntimeError) as ex:
                logger.failure('Seems like the volumedriver {0} is not running: {1}'.format(vp.name, ex.message),
                               'discrepancies_ovsdb_{0}'.format(vp.name))
                continue

            vdisk_volume_ids = []
            # cross-reference model vs. volumedriver
            for vdisk in vp.vdisks:
                vdisk_volume_ids.append(vdisk.volume_id)
                if vdisk.volume_id not in voldrv_volume_list:
                    missing_in_volumedriver.append(vdisk.guid)
                else:
                    voldrv_volume_list.remove(vdisk.volume_id)
            # cross-reference volumedriver vs. model
            for voldrv_id in voldrv_volume_list:
                if voldrv_id not in vdisk_volume_ids:
                    missing_in_model.append(voldrv_id)

            # display discrepancies for vPool
            if len(missing_in_volumedriver) != 0:
                logger.warning('Detected volumes that are MISSING in volumedriver but ARE in ovsdb in vPool'
                               'vpool name: {0} - vdisk guid(s):{1} '
                               .format(vp.name, ' '.join(missing_in_volumedriver)),
                               'discrepancies_ovsdb_{0}'.format(vp.name))
            else:
                logger.success('NO discrepancies found for ovsdb in vPool {0}'.format(vp.name),
                               'discrepancies_ovsdb_{0}'.format(vp.name))

            if len(missing_in_model) != 0:
                logger.warning('Detected volumes that are AVAILABLE in volumedriver '
                               'but ARE NOT in ovsdb in vPool '
                               'vpool name: {0} - vdisk volume id(s):{1}'
                               .format(vp.name, ' '.join(missing_in_model)),
                               'discrepancies_voldrv_{0}'.format(vp.name))
            else:
                logger.success('NO discrepancies found for voldrv in vPool {0}'.format(vp.name),
                               'discrepancies_voldrv_{0}'.format(vp.name))

    @staticmethod
    @expose_to_cli('ovs', 'test')
    def run(logger):
        OpenvStorageHealthCheck.get_local_settings(logger)
        OpenvStorageHealthCheck.check_ovs_processes(logger)
        OpenvStorageHealthCheck.check_ovs_workers(logger)
        OpenvStorageHealthCheck.check_ovs_packages(logger)
        OpenvStorageHealthCheck.check_required_ports(logger)
        OpenvStorageHealthCheck.get_zombied_and_dead_processes(logger)
        OpenvStorageHealthCheck.check_required_dirs(logger)
        OpenvStorageHealthCheck.check_size_of_log_files(logger)
        OpenvStorageHealthCheck.check_if_dns_resolves(logger)
        OpenvStorageHealthCheck.check_model_consistency(logger)
