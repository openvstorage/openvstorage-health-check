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
import re
import os
import grp
import glob
import psutil
import socket
import commands
import subprocess
import timeout_decorator
from pwd import getpwuid
from subprocess import CalledProcessError
from timeout_decorator.timeout_decorator import TimeoutError
from ovs.extensions.generic.configuration import NotFoundException
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.decorators import ExposeToCli
from ovs.extensions.healthcheck.helpers.configuration import ConfigurationManager, ConfigurationProduct
from ovs.extensions.healthcheck.helpers.helper import Helper
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.storagedriver import StoragedriverHelper
from ovs.extensions.healthcheck.helpers.vpool import VPoolHelper
from ovs.lib.storagerouter import StorageRouterController
from volumedriver.storagerouter import storagerouterclient as src
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException, ObjectNotFoundException, \
    MaxRedirectsExceededException


class OpenvStorageHealthCheck(object):
    """
    A healthcheck for the Open vStorage framework
    """
    MODULE = "openvstorage"
    MACHINE_DETAILS = System.get_my_storagerouter()
    MACHINE_ID = System.get_my_machine_id()

    @staticmethod
    @ExposeToCli('ovs', 'local-settings-test')
    def get_local_settings(logger):
        """
        Fetch settings of the local Open vStorage node

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        ovs_version = Helper.get_ovs_version()

        logger.info("Fetching LOCAL information of node: ")
        # Fetch all details
        try:
            logger.info("Cluster ID: {0}".format(Helper.get_cluster_id()))
            logger.info("Hostname: {0}".format(socket.gethostname()))
            logger.info("Storagerouter ID: {0}".format(OpenvStorageHealthCheck.MACHINE_ID))
            logger.info("Storagerouter TYPE: {0}".format(OpenvStorageHealthCheck.MACHINE_DETAILS.node_type))
            logger.info("Environment RELEASE: {0}".format(ovs_version[0]))
            logger.info("Environment BRANCH: {0}".format(ovs_version[1].title()))
            logger.info("Environment OS: {0}".format(Helper.check_os()))
            logger.success('Fetched all local settings', 'local-settings')
        except (CalledProcessError, NotFoundException, IOError) as ex:
            logger.failure('Could not fetch local-settings. Got {0}'.format(ex.message), 'local-settings')

    @staticmethod
    @ExposeToCli('ovs', 'log-files-test')
    def check_size_of_log_files(logger):
        """
        Checks the size of the initialized log files

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        collection = []
        good_size = []
        too_big = []

        logger.info("Checking if logfiles their size is not bigger than {0} MB: ".format(Helper.max_log_size),
                    'checkLogfilesSize')

        # collect log files
        for log, settings in Helper.check_logs.iteritems():
            if settings.get('type') == 'dir':
                # check if dirname exists
                if os.path.isdir(log):
                    # check if dirname contains files
                    files = OpenvStorageHealthCheck._list_logs_in_directory(log)
                    # check if given dirname has files
                    if len(files) != 0:
                        # check size of log files
                        for filename in files:
                            if settings.get('prefix'):
                                for prefix in list(settings.get('prefix')):
                                    if prefix in filename:
                                        collection.append(filename)
                            else:
                                collection.append(filename)

                    # check if has nested_dirs and nested_files
                    if settings.get('contains_nested'):
                        nested_dirs = OpenvStorageHealthCheck._list_dirs_in_directory(log)
                        for dirname in nested_dirs:
                            nested_files = OpenvStorageHealthCheck._list_logs_in_directory(log+"/"+dirname)
                            if len(nested_files) != 0:
                                # check size of log files
                                for nested_file in nested_files:
                                    if settings.get('prefix'):
                                        for prefix in list(settings.get('prefix')):
                                            if prefix in filename:
                                                collection.append(nested_file)
                                    else:
                                        collection.append(nested_file)
            else:
                # check if filename exists
                if os.path.exists(log):
                    collection.append(log)

        # process log files
        for c_files in collection:
            # check if logfile is larger than max_size
            if os.stat(c_files).st_size < 1024000 * Helper.max_log_size:
                good_size.append(c_files)
                logger.success("Logfile '{0}' has a GOOD size!".format(c_files))
            else:
                too_big.append(c_files)
                logger.failure("Logfile '{0}' is a BIG logfile!".format(c_files))

        if len(too_big) != 0:
            logger.failure("Some logfiles are TOO BIG, please check these files {0}!".format(', '.join(too_big)),
                           'log_size')
        else:
            logger.success("ALL log files are ok!", 'log_size')

    @staticmethod
    def _list_logs_in_directory(pwd):
        """
        lists the log files in a certain directory

        :param pwd: absolute location of a directory (e.g. /var/log)
        :type pwd: str
        :return: list of files
        :rtype: list
        """

        return glob.glob("{0}/*.log".format(pwd))

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
    def _is_port_listening(logger, process_name, port, ip=MACHINE_DETAILS.ip):
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
        logger.info("Checking port {0} of service {1} ...".format(port, process_name), '_is_port_listening')
        if Helper.check_port_connection(port, ip):
            logger.success("Connection successfully established!",
                           'port_{0}_{1}'.format(process_name, port))
        else:
            logger.failure("Connection FAILED to service '{1}' on port {0}".format(port, process_name),
                           'port_{0}_{1}'.format(process_name, port))

    @staticmethod
    @ExposeToCli('ovs', 'required-ports-test')
    def check_required_ports(logger):
        """
        Checks all ports of Open vStorage components (framework, memcached, nginx, rabbitMQ and celery)

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking PORT CONNECTIONS of OVS & EXTRA services ...", '')

        # check ports for OVS services
        logger.info("Checking OVS ports", '')
        for sr in ServiceHelper.get_services():
            if sr.storagerouter_guid == OpenvStorageHealthCheck.MACHINE_DETAILS.guid:
                for port in sr.ports:
                    if sr.name.split('_')[0] == 'albaproxy':
                        storagedriver_id = "{0}{1}".format(sr.name.split('_')[1], OpenvStorageHealthCheck.MACHINE_ID)
                        ip = StoragedriverHelper.get_by_storagedriver_id(storagedriver_id).storage_ip
                        OpenvStorageHealthCheck._is_port_listening(logger, sr.name, port, ip)
                    else:
                        OpenvStorageHealthCheck._is_port_listening(logger, sr.name, port)

        # check NGINX and memcached
        logger.info("Checking EXTRA ports", '')
        for process, ports in Helper.extra_ports.iteritems():
            for port in ports:
                OpenvStorageHealthCheck._is_port_listening(logger, process, port)

        # Check Celery and RabbitMQ
        logger.info("Checking RabbitMQ/Celery ...", '')
        if Helper.get_ovs_type() == "MASTER":
            pcommand = "celery inspect ping -b amqp://ovs:0penv5tor4ge@{0}//"\
                .format(OpenvStorageHealthCheck.MACHINE_DETAILS.ip)
            pcel = commands.getoutput(pcommand.format(process)).split("\n")
            if len(pcel) != 1 and 'pong' in pcel[1].strip():
                logger.success("Connection successfully established!", 'port_celery')
            else:
                logger.failure("Connection FAILED to service Celery, please check 'RabbitMQ' and 'ovs-workers'?",
                               'port_celery')
        else:
            logger.skip("RabbitMQ is not running/active on this server!", 'port_celery')

    @staticmethod
    @ExposeToCli('ovs', 'packages-test')
    def check_ovs_packages(logger):
        """
        Checks the availability of packages for Open vStorage

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking OVS packages: ", 'check_ovs_packages')

        for package in Helper.packages:
            result = commands.getoutput("apt-cache policy {0}".format(package)).split("\n")
            if len(result) != 1:
                logger.success(
                    "Package '{0}' is present, with version '{1}'".format(package, result[2].split(':')[1].strip()),
                    'package_{0}'.format(package))
            else:
                logger.skip("Package '{0}' is NOT present ...".format(package),
                            'package_{0}'.format(package))

    @staticmethod
    @ExposeToCli('ovs', 'processes-test')
    def check_ovs_processes(logger):
        """
        Checks the availability of processes for Open vStorage

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking LOCAL OVS services: ", 'check_ovs_processes')

        for ovs_service in os.listdir("/etc/init"):
            if ovs_service.startswith("ovs-"):
                process_name = ovs_service.split(".conf", 1)[0].strip()
                if Helper.check_status_of_service(process_name):
                    logger.success("Service '{0}' is running!".format(process_name),
                                   'process_{0}'.format(process_name))
                else:
                    logger.failure("Service '{0}' is NOT running, please check this... ".format(process_name),
                                   'process_{0}'.format(process_name))

    @staticmethod
    @timeout_decorator.timeout(7)
    def _check_celery():
        """
        Preliminary/Simple check for Celery and RabbitMQ component
        """

        # try if celery works smoothly
        try:
            guid = OpenvStorageHealthCheck.MACHINE_DETAILS.guid
            machine_id = OpenvStorageHealthCheck.MACHINE_DETAILS.machine_id
            obj = StorageRouterController.get_support_info.s(guid).apply_async(
                  routing_key='sr.{0}'.format(machine_id)).get()
        except TimeoutError as ex:
            raise TimeoutError("{0}: Process is taking to long!".format(ex.value))

        if obj:
            return True
        else:
            return False

    @staticmethod 
    def _extended_check_celery():
        """
        Extended check for Celery and RabbitMQ component
        """

        return False

    @staticmethod
    @ExposeToCli('ovs', 'ovs-workers-test')
    def check_ovs_workers(logger):
        """
        Extended check of the Open vStorage workers; When the simple check fails, it will execute a full/deep check.

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking if OVS-WORKERS are running smoothly: ", 'process_celery')

        # checking celery
        try:
            # basic celery check
            OpenvStorageHealthCheck._check_celery()
            logger.success("The OVS-WORKERS are working smoothly!", 'process_celery')
        except TimeoutError:

            # apparently the basic check failed, so we are going crazy
            logger.failure("Error during check of celery! Is RabbitMQ and/or ovs-workers running?", 'process_celery')

    @staticmethod
    @ExposeToCli('ovs', 'directories-test')
    def check_required_dirs(logger):
        """
        Checks the directories their rights and owners for mistakes

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking if OWNERS are set correctly on certain maps: ", 'checkRequiredMaps_owners')
        for dirname, owner_settings in Helper.owners_files.iteritems():
            # check if directory/file exists
            if os.path.exists(dirname):
                if owner_settings.get('user') == OpenvStorageHealthCheck._get_owner_of_file(dirname) and owner_settings.get(
                        'group') == OpenvStorageHealthCheck._get_group_of_file(dirname):
                    logger.success("Directory '{0}' has correct owners!".format(dirname), 'dir_{0}'.format(dirname))
                else:
                    logger.failure(
                        "Directory '{0}' has INCORRECT owners! It must be OWNED by USER={1} and GROUP={2}"
                        .format(dirname, owner_settings.get('user'), owner_settings.get('group')),
                        'dir_{0}'.format(dirname))
            else:
                logger.skip("Directory '{0}' does not exists!".format(dirname), 'dir_{0}'.format(dirname))

        logger.info("Checking if Rights are set correctly on certain maps: ", 'checkRequiredMaps_rights')
        for dirname, rights in Helper.rights_dirs.iteritems():
            # check if directory/file exists
            if os.path.exists(dirname):
                if OpenvStorageHealthCheck._check_rights_of_file(dirname, rights):
                    logger.success("Directory '{0}' has correct rights!".format(dirname),
                                   'dir_{0}'.format(dirname))
                else:
                    logger.failure("Directory '{0}' has INCORRECT rights! It must be CHMOD={1} "
                                   .format(dirname, rights), 'dir_{0}'.format(dirname))
            else:
                logger.skip("Directory '{0}' does not exists!".format(dirname), 'dir_{0}'.format(dirname))

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
    @ExposeToCli('ovs', 'dns-test')
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

        logger.info("Checking DNS resolving: ", 'titleDnsResolving')
        try:
            socket.gethostbyname(fqdn)
            logger.success("DNS resolving works!", 'dns_resolving')
            return True
        except Exception:
            logger.failure("DNS resolving doesn't work, please check /etc/resolv.conf or add correct",
                           "DNS server and make it immutable: 'sudo chattr +i /etc/resolv.conf'!",
                           'dns_resolving')
            return False

    @staticmethod
    @ExposeToCli('ovs', 'zombie-processes-test')
    def get_zombied_and_dead_processes(logger):
        """
        Finds zombied or dead processes on a local machine

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        zombie_processes = []
        dead_processes = []

        logger.info("Checking for zombie/dead processes: ", 'checkForZombieProcesses')

        # check for zombie'd and dead processes
        for proc in psutil.process_iter():
            try:
                pinfo = proc.as_dict(attrs=['pid', 'name', 'status'])
            except psutil.NoSuchProcess:
                pass
            else:
                if pinfo.get('status') == psutil.STATUS_ZOMBIE:
                    zombie_processes.append("{0}({1})".format(pinfo.get('name'), pinfo.get('pid')))

                if pinfo.get('status') == psutil.STATUS_DEAD:
                    dead_processes.append("{0}({1})".format(pinfo.get('name'), pinfo.get('pid')))

        # check if there zombie processes
        if len(zombie_processes) == 0:
            logger.success("There are NO zombie processes on this node!", 'process_zombies')
        else:
            logger.warning("We DETECTED zombie processes on this node: {0}".format(', '.join(zombie_processes)),
                           'process_zombies')

        # check if there dead processes
        if len(dead_processes) == 0:
            logger.success("There are NO dead processes on this node!", 'process_dead')
        else:
            logger.failure("We DETECTED dead processes on this node: {0}".format(', '.join(dead_processes)),
                           'process_dead')

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
    def _check_filedriver_remove(vp_name, test_name):
        """
        Async method to checks if a FILEDRIVER `remove` works on a vpool
        Always try to check if the file exists after performing this method

        :param vp_name: name of the vpool
        :type vp_name: str
        :param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)
        :type test_name: str
        :return: True if succeeded, False if failed
        :rtype: bool
        """

        return subprocess.check_output("rm -f /mnt/{0}/{1}.xml".format(vp_name, test_name),
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
                name = "ovs-healthcheck-test-{0}".format(OpenvStorageHealthCheck.MACHINE_ID)
                if vp.guid in OpenvStorageHealthCheck.MACHINE_DETAILS.vpools_guids:
                    try:
                        OpenvStorageHealthCheck._check_filedriver(vp.name, name)
                        if os.path.exists("/mnt/{0}/{1}.xml".format(vp.name, name)):
                            # working
                            OpenvStorageHealthCheck._check_filedriver_remove(vp.name, name)
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
    @ExposeToCli('ovs', 'model-test')
    def check_model_consistency(logger):
        """
        Checks if the model consistency of OVSDB vs. VOLUMEDRIVER and does a preliminary check on RABBITMQ

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking model consistency: ", 'check_model_consistency')

        # RabbitMQ check: cluster verification
        logger.info("Precheck: verification of RabbitMQ cluster: ", 'checkRabbitMQcluster')
        if Helper.get_ovs_type() == "MASTER":
            cluster_status = commands.getoutput("rabbitmqctl cluster_status").split("\n")
            if "Error" not in cluster_status[1]:

                partition_status = ''
                for status in cluster_status:
                    if re.match('^.*\{partitions,\[.*$', status):
                        partition_status = status

                # check parition status
                if '@' in partition_status:
                    logger.failure(
                        "Seems like the RabbitMQ cluster has 'partition' problems, please check this...",
                        'process_rabbitmq')
                else:
                    logger.success("RabbitMQ does not seem to have 'partition' problems",
                                   'process_rabbitmq')
            else:
                logger.failure("Seems like the RabbitMQ cluster has errors, maybe it is offline?",
                               'process_rabbitmq')
        else:
            logger.skip("RabbitMQ is not running/active on this server!",
                        'process_rabbitmq')

        #
        # Checking consistency of volumedriver vs. ovsdb and backwards
        #

        for vp in VPoolHelper.get_vpools():
            if vp.guid in OpenvStorageHealthCheck.MACHINE_DETAILS.vpools_guids:
                logger.info("Checking consistency of volumedriver vs. ovsdb for vPool '{0}': ".format(vp.name))

                # list of vdisks that are in model but are not in volumedriver
                missing_in_volumedriver = []

                # list of volumes that are in volumedriver but are not in model
                missing_in_model = []

                # fetch configfile of vpool for the volumedriver
                config_file = ConfigurationManager.get_config_file_path(product=ConfigurationProduct.VPOOL,
                                                                        vpool_guid=vp.guid,
                                                                        vpool_name=vp.name,
                                                                        node_id=OpenvStorageHealthCheck.MACHINE_ID)
                voldrv_client = src.LocalStorageRouterClient(config_file)

                # collect data from volumedriver
                try:
                    voldrv_volume_list = voldrv_client.list_volumes()
                except ClusterNotReachableException:
                    logger.failure("Seems like the volumedriver '{0}' is not running.".format(vp.name),
                                   'discrepancies_ovsdb_{0}'.format(vp.name))
                    continue

                vdisk_volume_ids = [vdisk.volume_id for vdisk in vp.vdisks]

                # crossreference model vs. volumedriver
                for vdisk in vp.vdisks:
                    if vdisk.volume_id not in voldrv_volume_list:
                        missing_in_volumedriver.append(vdisk.guid)

                # crossreference volumedriver vs. model
                for voldrv_id in voldrv_volume_list:
                    if voldrv_id not in vdisk_volume_ids:
                        missing_in_model.append(voldrv_id)

                # display discrepancies for vPool
                if len(missing_in_volumedriver) != 0:
                    logger.warning("Detected volumes that are MISSING in volumedriver but ARE in ovsdb in vPool (a known cause is a faulty preset) "
                                   "vpool name: {0} - vdisk guid(s):{1} ".format(vp.name, ' '.join(missing_in_volumedriver)),
                                    'discrepancies_ovsdb_{0}'.format(vp.name))

                else:
                    logger.success("NO discrepancies found for ovsdb in vPool '{0}'".format(vp.name),
                                   'discrepancies_ovsdb_{0}'.format(vp.name))

                if len(missing_in_model) != 0:
                    logger.warning("Detected volumes that are AVAILABLE in volumedriver "
                                   "but ARE NOT in ovsdb in vPool "
                                   "vpool name: {0} - vdisk volume id(s):{1}".format(vp.name, ' '.join(missing_in_model)),
                                   'discrepancies_voldrv_{0}'.format(vp.name))
                else:
                    logger.success("NO discrepancies found for voldrv in vPool '{0}'".format(vp.name),
                                   'discrepancies_voldrv_{0}'.format(vp.name))
            else:
                logger.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                            'discrepancies_voldrv_{0}'.format(vp.name))

    @staticmethod
    @ExposeToCli('ovs', 'halted-volumes-test')
    def check_for_halted_volumes(logger):
        """
        Checks for halted volumes on a single or multiple vPools

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking for halted volumes: ", 'checkHaltedVolumes')

        vpools = VPoolHelper.get_vpools()

        if len(vpools) != 0:

            for vp in vpools:
                
                if vp.guid in OpenvStorageHealthCheck.MACHINE_DETAILS.vpools_guids:

                    haltedvolumes = []

                    logger.info("Checking vPool '{0}': ".format(vp.name), 'halted_title')

                    config_file = ConfigurationManager.get_config_file_path(product=ConfigurationProduct.VPOOL,
                                                                            vpool_guid=vp.guid,
                                                                            vpool_name=vp.name,
                                                                            node_id=OpenvStorageHealthCheck.MACHINE_ID)
                    voldrv_client = src.LocalStorageRouterClient(config_file)

                    try:
                        voldrv_volume_list = voldrv_client.list_volumes()
                    except ClusterNotReachableException:
                        logger.failure("Seems like the Volumedriver {0} is not running.".format(vp.name),
                                       'halted_{0}'.format(vp.name))
                        continue

                    for volume in voldrv_volume_list:
                        # check if volume is halted, returns: 0 or 1
                        try:
                            if int(OpenvStorageHealthCheck._info_volume(voldrv_client, volume).halted):
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

                    # print all results
                    if len(haltedvolumes) > 0:
                        logger.failure("Detected volumes that are HALTED in vPool '{0}': {1}"
                                       .format(vp.name, ', '.join(haltedvolumes)), 'halted_{0}'.format(vp.name))
                    else:
                        logger.success("No halted volumes detected in vPool '{0}'"
                                       .format(vp.name), 'halted_{0}'.format(vp.name))
                else:
                    logger.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                'halted_{0}'.format(vp.name))

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
    @ExposeToCli('ovs', 'test')
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
        OpenvStorageHealthCheck.check_for_halted_volumes(logger)
        OpenvStorageHealthCheck.check_filedrivers(logger)
