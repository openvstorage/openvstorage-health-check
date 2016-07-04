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
Open vStorage Health Check module
"""

import os
import grp
import glob
import time
import psutil
import socket
import threading
import timeout_decorator
import subprocess
from pwd import getpwuid
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.system import System
from ovs.dal.lists.servicelist import ServiceList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.exceptions import ObjectNotFoundException
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.lib.storagerouter import StorageRouterController
from ovs.extensions.healthcheck.utils.extension import Utils
from ovs.log.healthcheck_logHandler import HCLogHandler
from timeout_decorator.timeout_decorator import TimeoutError
import volumedriver.storagerouter.storagerouterclient as src
from volumedriver.storagerouter.storagerouterclient import ClusterNotReachableException, ObjectNotFoundException, \
    MaxRedirectsExceededException


class OpenvStorageHealthCheck:
    """
    A healthcheck for the Open vStorage framework
    """

    def __init__(self, logging=HCLogHandler(False)):
        """
        Init method for Open vStorage health check module

        @param logging: ovs.log.healthcheck_logHandler

        @type logging: Class
        """
        self.module = "openvstorage"
        self.LOGGER = logging
        self.utility = Utils()
        self.service_manager = self.utility.serviceManager
        self.machine_details = System.get_my_storagerouter()
        self.machine_id = self.machine_details.machine_id
        self.max_logsize = 500  # in MB

        # list of packages on your local system
        self.openvstorageTotalPackageList = ["openvstorage", "openvstorage-backend", "openvstorage-backend-core",
                                             "openvstorage-backend-webapps", "openvstorage-core", "openvstorage-hc",
                                             "openvstorage-sdm", "openvstorage-webapps", "openvstorage-test",
                                             "alba", "volumedriver-base", "volumedriver-server", "nginx", "memcached",
                                             "rabbitmq-server", "qemu-kvm", "virtinst", "openvpn", "ntp",
                                             "swiftstack-node", "volumedriver-no-dedup-server", "libvirt0",
                                             "python-libvirt", "omniorb-nameserver", "avahi-daemon", "avahi-utils",
                                             "libovsvolumedriver", "qemu", "libvirt-bin", "blktap-openvstorage-utils"]
        # 1. key -> service name (string)
        # 2. value -> ports (list)
        self.req_side_ports = {'nginx': ['80', '443'], 'memcached': ['11211']}

        # 1. key -> absolute directory name (string)
        # 2. value -> rights in linux style format (string)
        self.req_map_rights = {'/tmp': '777', '/var/tmp': '777'}

        # 1. key -> absolute directory or log name (string)
        # 2. value -> required user and group (dict)
        self.req_map_owners = {'/var/log/syslog': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/auth.log': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/kern.log': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/wtmp': {'user': 'root', 'group': 'utmp'},
                               '/var/log/btmp': {'user': 'root', 'group': 'utmp'},
                               '/etc/gshadow': {'user': 'root', 'group': 'shadow'},
                               '/var/cache/man': {'user': 'man', 'group': 'root'},
                               '/etc/shadow': {'user': 'root', 'group': 'shadow'}}

        # 1. for dir required options: AS key -> prefix (string)
        #    AS value -> list, substring of prefix (string) , type -> string (dir)
        #    contains_nested -> Boolean (contains nested dirs and files)
        # 2. for file required options: type -> string (file)
        self.logging = {'/var/log/upstart': {'prefix': ['ovs', 'asd'], 'type': 'dir', 'contains_nested': False},
                        '/var/log/ovs': {'prefix': None, 'type': 'dir', 'contains_nested': True},
                        '/var/log/gunicorn': {'prefix': None, 'type': 'dir', 'contains_nested': False},
                        '/var/log/rabbitmq': {'prefix': None, 'type': 'dir', 'contains_nested': False},
                        '/var/log/nginx': {'prefix': None, 'type': 'dir', 'contains_nested': False},
                        '/var/log/arakoon': {'prefix': None, 'type': 'dir', 'contains_nested': True},
                        '/var/log/memcached.log': {'type': 'file'}}

    def get_local_settings(self):
        """
        Fetch settings of the local Open vStorage node
        """

        self.LOGGER.info("Fetching LOCAL information of node: ", 'local_info', False)
        self.LOGGER.success("Cluster ID: {0}".format(self.utility.cluster_id), 'lc2', False)
        self.LOGGER.success("Storagerouter ID: {0}".format(self.machine_id), 'lc2', False)
        self.LOGGER.success("Environment TYPE: {0}".format(self.machine_details.node_type), 'lc3', False)
        self.LOGGER.success("Environment VERSION: {0}".format(self.utility.ovs_version), 'lc4', False)

    def check_size_of_log_files(self):
        """
        Checks the size of the initialized log files
        """

        collection = []
        good_size = []
        to_big = []

        self.LOGGER.info("Checking if logfiles their size is not bigger than {0} MB: ".format(self.max_logsize),
                         'checkLogfilesSize', False)

        # collect log files
        for log, settings in self.logging.iteritems():
            if settings.get('type') == 'dirname':
                # check if dirname exists
                if os.path.isdir(log):
                    # check if dirname contains files
                    files = self._list_logs_in_directory(log)
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
                        nested_dirs = self._list_dirs_in_directory(log)
                        for dirname in nested_dirs:
                            nested_files = self._list_logs_in_directory(log+"/"+dirname)
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
            if os.stat(c_files).st_size < 1024000 * self.max_logsize:
                good_size.append(c_files)
                self.LOGGER.success("Logfile '{0}' has a GOOD size!".format(c_files), 'log_{0}'.format(c_files),
                                    False)
            else:
                to_big.append(c_files)
                self.LOGGER.failure("Logfile '{0}' is a big ass logfile!".format(c_files), 'log_{0}'.format(c_files),
                                    False)

        # end for unattended_install
        if self.LOGGER.unattended_mode:
            if len(to_big) != 0:
                self.LOGGER.failure("Some logfiles are too big, please check this!".format(c_files),
                                    'log_size')
            else:
                self.LOGGER.success("ALL log files are ok!".format(c_files), 'log_size')

    @staticmethod
    def _list_logs_in_directory(pwd):
        """
        lists the log files in a certain directory

        @param pwd: absolute location of a directory (e.g. /var/log)

        @type pwd: str

        @return: list of files

        @rtype: list
        """

        return glob.glob("{0}/*.log".format(pwd))

    @staticmethod
    def _list_dirs_in_directory(pwd):
        """
        lists the directories in a certain directory

        @param pwd: absolute location of a directory (e.g. /var/log)

        @type pwd: str

        @return: list of directories

        @rtype: list
        """

        return next(os.walk(pwd))[1]

    @staticmethod
    def _fetch_compute_node_details_by_ip(node_ip):
        """
        Fetches details of a compute node connected to the OpenvStorage cluster

        @param node_ip: IP address of a node in the Open vStorage cluster

        @type node_ip: str

        @return: Compute node Object

        @rtype: Object
        """

        return PMachineList().get_by_ip(str(node_ip))

    @staticmethod
    def _fetch_compute_nodes_per_center_by_ip(management_ip):
        """
        Fetches the compute nodes connected to a Hypervisor Management Center

        @param management_ip: IP address of the hypervisor management center

        @type management_ip: str

        @return: list of compute nodes IP addresses

        @rtype: list
        """

        return MgmtCenterList().get_by_ip(str(management_ip)).hosts

    def _check_port_connection(self, port_number):
        """
        Checks the port connection on a IP address

        @param port_number: Port number of a service that is running on the local machine. (Public or loopback)

        @type port_number: int

        @return: True if the port is available; False if the port is NOT available

        @rtype: bool
        """

        # check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((self.machine_details.ip, int(port_number)))
        if result == 0:
            return True
        else:
            # double check because some services run on localhost
            result = sock.connect_ex(('127.0.0.1', int(port_number)))
            if result == 0:
                return True
            else:
                return False

    def _is_port_listening(self, process_name, port):
        """
        Checks the port connection of a process

        @param process_name: name of a certain process running on this local machine
        @param port: port where the service is running on

        @type process_name: str
        @type port: int
        """

        self.LOGGER.info("Checking port {0} of service {1} ...".format(port, process_name), '_is_port_listening', False)
        if self._check_port_connection(port):
            self.LOGGER.success("Connection successfully established!",
                                'port_{0}_{1}'.format(process_name, port))
        else:
            self.LOGGER.failure("Connection FAILED to service '{1}' on port {0}".format(port, process_name),
                                'port_{0}_{1}'.format(process_name, port))

    def check_required_ports(self):
        """
        Checks all ports of Open vStorage components (framework, memcached, nginx, rabbitMQ and celery)
        """

        self.LOGGER.info("Checking PORT CONNECTIONS of several services ...", 'check_required_ports', False)

        # check ports for OVS services
        self.LOGGER.info("Checking OVS services ...", 'checkOvsServicesPorts', False)
        for sr in ServiceList.get_services():
            if sr.storagerouter_guid == self.machine_details.guid:
                for port in sr.ports:
                    self._is_port_listening(sr.name, port)

        # check NGINX and memcached
        self.LOGGER.info("Checking NGINX and Memcached ...", 'checkNginxAndMemcached', False)

        for process, ports in self.req_side_ports.iteritems():
            for port in ports:
                self._is_port_listening(process, port)

        # Check Celery and RabbitMQ
        self.LOGGER.info("Checking RabbitMQ/Celery ...", 'checkRabbitmqCelery', False)

        if self.utility.node_type == "MASTER":
            pcommand = "celery inspect ping -b amqp://ovs:0penv5tor4ge@{0}//".format(self.machine_details.ip)
            pcel = self.utility.execute_bash_command(pcommand.format(process))
            if len(pcel) != 1 and 'pong' in pcel[1].strip():
                self.LOGGER.success("Connection successfully established!", 'port_celery')
            else:
                self.LOGGER.failure("Connection FAILED to service Celery, please check 'RabbitMQ' and 'ovs-workers'?",
                                    'port_celery')
        else:
            self.LOGGER.skip("RabbitMQ is not running/active on this server!", 'port_celery')

    def check_ovs_packages(self):
        """
        Checks the availability of packages for Open vStorage
        """

        self.LOGGER.info("Checking OVS packages: ", 'check_ovs_packages', False)

        for package in self.openvstorageTotalPackageList:
            result = self.utility.execute_bash_command("apt-cache policy %s" % package)
            if len(result) != 1:
                self.LOGGER.success(
                    "Package '%s' is present, with version '%s'" % (package, result[2].split(':')[1].strip()),
                    'package_{0}'.format(package))
            else:
                self.LOGGER.skip("Package '{0}' is NOT present ...".format(package),
                                 'package_{0}'.format(package))
        return None

    def check_ovs_processes(self):
        """
        Checks the availability of processes for Open vStorage
        """

        self.LOGGER.info("Checking LOCAL OVS services: ", 'check_ovs_processes', False)

        if self.service_manager:
            for ovs_service in os.listdir("/etc/init"):
                if ovs_service.startswith("ovs-"):
                    process_name = ovs_service.split(".conf", 1)[0].strip()
                    if self.utility.check_status_of_service(process_name):
                        self.LOGGER.success("Service '{0}' is running!".format(process_name),
                                            'process_{0}'.format(process_name))
                    else:
                        self.LOGGER.failure("Service '{0}' is NOT running, please check this... ".format(process_name),
                                            'process_{0}'.format(process_name))
        else:
            self.LOGGER.exception("Other service managers than 'init' are not yet supported!",
                                  'hc_process_supported', False)

    @timeout_decorator.timeout(7)
    def _check_celery(self):
        """
        Preliminary/Simple check for Celery and RabbitMQ component
        """

        # try if celery works smoothly
        try:
            guid = self.machine_details.guid
            machine_id = self.machine_details.machine_id
            obj = StorageRouterController.get_support_info.s(guid).apply_async(
                  routing_key='sr.{0}'.format(machine_id)).get()
        except TimeoutError as ex:
            raise TimeoutError("{0}: Process is taking to long!".format(ex.value))

        if obj:
            return True
        else:
            return False

    def _extended_check_celery(self):
        """
        Extended check for Celery and RabbitMQ component
        """

        rlogs = "'/var/log/rabbitmq/startup_*' or '/var/log/rabbitmq/shutdown_*'"

        self.LOGGER.warning("Commencing deep check for celery/RabbitMQ", '_extended_check_celery', False)

        # check ovs-workers
        if not self.utility.check_status_of_service('ovs-workers'):
            self.LOGGER.failure("Seems like ovs-workers are down, maybe due to RabbitMQ?",
                                'process_ovs-workers', False)
            # check rabbitMQ status
            if self.utility.check_status_of_service('rabbitmq-server'):
                # RabbitMQ seems to be DOWN
                self.LOGGER.failure("RabbitMQ seems to be DOWN, please check logs in {0}".format(rlogs),
                                    'RabbitIsDown', False)
                return False
            else:
                # RabbitMQ is showing it's up but lets check some more stuff
                list_status = self.utility.execute_bash_command('rabbitmqctl list_queues')[1]
                if "Error" in list_status:
                    self.LOGGER.failure(
                        "RabbitMQ seems to be UP but it is not functioning as it should! Maybe it has been"
                        " shutdown through 'stop_app'? Please check logs in {0}".format(
                         rlogs), 'RabbitSeemsUpButNotFunctioning', False)
                    return False
                elif "Error: {aborted" in list_status:
                    self.LOGGER.failure(
                        "RabbitMQ seems to be DOWN but it is not functioning as it should! Please check logs in {0}"
                        .format(rlogs), 'RabbitSeemsDown', False)
                    return False
                else:
                    self.LOGGER.success("RabbitMQ process is running as it should, start checking the queues... ",
                                        'checkQueuesButRabbitIsWorking', False)
        else:
            self.LOGGER.failure("OVS workers are UP! Maybe it is stuck? Start checking the queues...",
                                'checkQueuesButOvsWorkersAreUp', False)

        # fetch remaining tasks on node
        self.LOGGER.info("Starting deep check for RabbitMQ!", 'DeepCheckRabbit', False)

        #
        # Rabbitmq check: queue verification
        #
        rcommand = "rabbitmqctl list_queues | grep ovs_ | sed -e 's/[[:space:]]\+/ /g' | cut -d ' ' -f 2"
        output_01 = self.utility.execute_bash_command(rcommand)
        time.sleep(15)
        output_02 = self.utility.execute_bash_command(rcommand)

        # check diff/results and continue
        lost_queues = []
        if set(output_01) - set(output_02):
            # found some changed queue's!
            for i, j in zip(output_01, output_02):
                if int(i) < int(j):
                    # queue is building up
                    self.LOGGER.warning(
                        "Seems like queue '{0}' is building up! Please verify this with 'rabbitmqctl list_queues "
                        "| grep ovs_'".format(output_02.index(j)), 'process_celery_queue_{0}'
                        .format(output_02.index(j)), False)
                    lost_queues.append(output_02.index(j))
                elif int(i) > int(j):
                    # queue is decreasing
                    self.LOGGER.success("Seems like queue '{0}' is working fine!".format(output_02.index(j)),
                                        'process_celery_queue_{0}'.format(output_02.index(j)), False)
            # post-check
            if len(lost_queues) > 0:
                return False
            else:
                return True
        else:
            self.LOGGER.failure(
                "Seems like all Celery queues are stuck, you should check: 'rabbitmqctl list_queues' and 'ovs-workers'",
                'process_celery_all_queues', False)
            return False

    def check_ovs_workers(self):
        """
        Extended check of the Open vStorage workers; When the simple check fails, it will execute a full/deep check.
        """

        self.LOGGER.info("Checking if OVS-WORKERS are running smoothly: ", 'process_celery', False)

        # checking celery
        try:
            # basic celery check
            self._check_celery()
            self.LOGGER.success("The OVS-WORKERS are working smoothly!", 'process_celery')
        except TimeoutError as ex:

            # apparently the basic check failed, so we are going crazy
            self.LOGGER.failure(
                "Unexpected exception received during check of celery! Are RabbitMQ and/or ovs-workers running?"
                " Traceback: {0}".format(ex), 'process_celery')

            # commencing deep check
            if not self._extended_check_celery():
                self.LOGGER.failure("Please verify the integrety of 'RabbitMQ' and 'ovs-workers'",
                                    'process_celery', False)
                return False
            else:
                self.LOGGER.success("Deep check finished successfully and did not find anything",
                                    'process_celery', False)
                return True

    def check_required_dirs(self):
        """
        Checks the directories their rights and owners for mistakes
        """

        self.LOGGER.info("Checking if OWNERS are set correctly on certain maps: ",
                         'checkRequiredMaps_owners', False)
        for dirname, owner_settings in self.req_map_owners.iteritems():
            if owner_settings.get('user') == self._get_owner_of_file(dirname) and owner_settings.get(
                    'group') == self._get_group_of_file(dirname):
                self.LOGGER.success("Directory '{0}' has correct owners!".format(dirname),
                                    'dir_{0}'.format(dirname))
            else:
                self.LOGGER.failure(
                    "Directory '{0}' has INCORRECT owners! It must be OWNED by USER={1} and GROUP={2}"
                    .format(dirname, owner_settings.get('user'), owner_settings.get('group')),
                    'dir_{0}'.format(dirname))

        self.LOGGER.info("Checking if Rights are set correctly on certain maps: ",
                         'checkRequiredMaps_rights', False)
        for dirname, rights in self.req_map_rights.iteritems():
            if self._check_rights_of_file(dirname, rights):
                self.LOGGER.success("Directory '{0}' has correct rights!".format(dirname),
                                    'dir_{0}'.format(dirname))
            else:
                self.LOGGER.failure("Directory '{0}' has INCORRECT rights! It must be CHMOD={1} "
                                    .format(dirname, rights), 'dir_{0}'.format(dirname))

        return True

    @staticmethod
    def _get_owner_of_file(filename):
        """
        Gets the OWNER of a certain file

        @param filename: the absolute pathname of the file

        @type filename: str

        @return: owner name of a file

        @rtype: str
        """

        return getpwuid(os.stat(filename).st_uid).pw_name

    @staticmethod
    def _get_group_of_file(filename):
        """
        Gets the GROUP of a certain file

        @param filename: the absolute pathname of the file

        @type filename: str

        @return: group of a file

        @rtype: str
        """

        return grp.getgrgid(os.stat(filename).st_gid).gr_name

    @staticmethod
    def _check_rights_of_file(filename, rights):
        """
        Checks if there are RIGHTS mistakes in a certain file

        @param filename: the absolute pathname of the file
        @param rights: the correct rights that the file needs to have

        @type filename: str
        @type rights: str

        @return: True if the rights are correct; False if they are wrong

        @rtype: bool
        """

        # fetch file to start compare
        st = os.stat(filename)
        return oct(st.st_mode)[-3:] == str(rights)

    def check_if_dns_resolves(self, fqdn="google.com"):
        """
        Checks if DNS resolving works on a local machine

        @param fqdn: the absolute pathname of the file

        @type fqdn: str

        @return: True if the DNS resolving works; False it doesn't work

        @rtype: bool
        """

        self.LOGGER.info("Checking DNS resolving: ", 'titleDnsResolving', False)
        try:
            socket.gethostbyname(fqdn)
            self.LOGGER.success("DNS resolving works!", 'dns_resolving')
            return True
        except Exception:
            self.LOGGER.failure("DNS resolving doesn't work, please check /etc/resolv.conf or add correct",
                                "DNS server and make it immutable: 'sudo chattr +i /etc/resolv.conf'!",
                                'dns_resolving')
            return False

    def get_zombied_and_dead_processes(self):
        """
        Finds zombied or dead processes on a local machine
        """

        zombie_processes = []
        dead_processes = []

        self.LOGGER.info("Checking for zombie/dead processes: ", 'checkForZombieProcesses', False)

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
            self.LOGGER.success("There are NO zombie processes on this node!", 'process_zombies')
        else:
            self.LOGGER.warning("We DETECTED zombie processes on this node: {0}".format(', '.join(zombie_processes)),
                                'process_zombies')

        # check if there dead processes
        if len(dead_processes) == 0:
            self.LOGGER.success("There are NO dead processes on this node!", 'process_dead')
        else:
            self.LOGGER.failure("We DETECTED dead processes on this node: {0}".format(', '.join(dead_processes)),
                                'process_dead')

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_filedriver(vp_name, test_name):
        """
        Async method to checks if a FILEDRIVER works on a vpool
        Always try to check if the file exists after performing this method

        @param vp_name: name of the vpool
        @param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)

        @type vp_name: str
        @type test_name: str

        @return: True if succeeded, False if failed

        @rtype: bool
        """

        return subprocess.check_output("touch /mnt/{0}/{1}.xml".format(vp_name, test_name),
                                       stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    @timeout_decorator.timeout(5)
    def _check_volumedriver(vp_name, test_name):
        """
        Async method to checks if a VOLUMEDRIVER works on a vpool
        Always try to check if the file exists after performing this method

        @param vp_name: name of the vpool
        @param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)

        @type vp_name: str
        @type test_name: str

        @return: True if succeeded, False if failed

        @rtype: bool
        """

        return subprocess.check_output("truncate -s 10GB /mnt/{0}/{1}.raw".format(vp_name, test_name),
                                       stderr=subprocess.STDOUT, shell=True)

    def check_filedrivers(self):
        """
        Checks if the FILEDRIVERS work on a local machine (compatible with multiple vPools)
        """

        self.LOGGER.info("Checking filedrivers: ", 'filedriver', False)

        vpools = VPoolList.get_vpools()

        # perform tests
        if len(vpools) != 0:
            for vp in vpools:
                name = "ovs-healthcheck-test-{0}".format(self.machine_id)
                if vp.guid in self.machine_details.vpools_guids:
                    try:
                        self._check_filedriver(vp.name, name)
                        if os.path.exists("/mnt/{0}/{1}.xml".format(vp.name, name)):
                            # working
                            self.LOGGER.success("Filedriver for vPool '{0}' is working fine!".format(vp.name),
                                                'filedriver_{0}'.format(vp.name))
                            self.utility.execute_bash_command("rm -f /mnt/{0}/ovs-healthcheck-test-*.xml"
                                                              .format(vp.name, name))
                        else:
                            # not working
                            self.LOGGER.failure("Filedriver for vPool '{0}' seems to have problems!".format(vp.name),
                                                'filedriver_{0}'.format(vp.name))
                    except TimeoutError as e:
                        # timeout occured, action took too long
                        self.LOGGER.failure("Filedriver of vPool '{0}' seems to have problems: {0}"
                                            .format(vp.name, e), 'filedriver_{0}'.format(vp.name))
                    except subprocess.CalledProcessError as e:
                        # can be input/output error by filedriver
                        self.LOGGER.failure("Filedriver of vPool '{0}' seems to have problems: {0}"
                                            .format(vp.name, e), 'filedriver_{0}'.format(vp.name))
                else:
                    self.LOGGER.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                     'filedriver_{0}'.format(vp.name))
        else:
            self.LOGGER.skip("No vPools found!", 'filedrivers_nofound')

    def check_volumedrivers(self):
        """
        Checks if the VOLUMEDRIVERS work on a local machine (compatible with multiple vPools)
        """

        self.LOGGER.info("Checking volumedrivers: ", 'check_volumedrivers', False)

        vpools = VPoolList.get_vpools()

        if len(vpools) != 0:
            for vp in vpools:
                name = "ovs-healthcheck-test-{0}".format(self.machine_id)
                if vp.guid in self.machine_details.vpools_guids:
                    try:
                        self._check_volumedriver(vp.name, name)

                        if os.path.exists("/mnt/{0}/{1}.raw".format(vp.name, name)):
                            # working
                            self.LOGGER.success("Volumedriver of vPool '{0}' is working fine!".format(vp.name),
                                                'volumedriver_{0}'.format(vp.name))
                            self.utility.execute_bash_command("rm -f /mnt/{0}/ovs-healthcheck-test-*.raw"
                                                              .format(vp.name, name))
                        else:
                            # not working, file does not exists
                            self.LOGGER.failure("Volumedriver of vPool '{0}' seems to have problems"
                                                .format(vp.name), 'volumedriver_{0}'.format(vp.name))
                    except TimeoutError as e:
                        # timeout occured, action took too long
                        self.LOGGER.failure("Volumedriver of vPool '{0}' seems to have problems: {0}"
                                            .format(vp.name, e), 'volumedriver_{0}'.format(vp.name))
                    except subprocess.CalledProcessError as e:
                        # can be input/output error by volumedriver
                        self.LOGGER.failure("Volumedriver of vPool '{0}' seems to have problems: {0}"
                                            .format(vp.name, e), 'volumedriver_{0}'.format(vp.name))

                else:
                    self.LOGGER.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                     'volumedriver_{0}'.format(vp.name))
        else:
            self.LOGGER.skip("No vPools found!", 'volumedrivers_nofound')

    def check_model_consistency(self):
        """
        Checks if the model consistency of OVSDB vs. VOLUMEDRIVER and does a preliminary check on RABBITMQ
        """

        self.LOGGER.info("Checking model consistency: ", 'check_model_consistency', False)

        #
        # RabbitMQ check: cluster verification
        #

        self.LOGGER.info("Precheck: verification of RabbitMQ cluster: ",
                         'checkRabbitMQcluster', False)

        if self.utility.node_type == "MASTER":

            cluster_status = self.utility.execute_bash_command("rabbitmqctl cluster_status")

            if "Error" not in cluster_status[1]:

                # this can happen
                if len(cluster_status) <= 3:
                    partition_status = cluster_status[2]
                else:
                    partition_status = cluster_status[3]

                # check parition status
                if '@' in partition_status:
                    self.LOGGER.failure(
                        "Seems like the RabbitMQ cluster has 'partition' problems, please check this...",
                        'process_rabbitmq', False)
                else:
                    self.LOGGER.success("RabbitMQ does not seem to have 'partition' problems",
                                        'process_rabbitmq', False)
            else:
                self.LOGGER.failure("Seems like the RabbitMQ cluster has errors, maybe it is offline?",
                                    'process_rabbitmq', False)

        else:
            self.LOGGER.skip("RabbitMQ is not running/active on this server!",
                             'process_rabbitmq', False)

        #
        # Checking consistency of volumedriver vs. ovsdb and backwards
        #

        for vp in VPoolList.get_vpools():
            if vp.guid in self.machine_details.vpools_guids:
                self.LOGGER.info("Checking consistency of volumedriver vs. ovsdb for vPool '{0}': ".format(vp.name),
                                 'checkDiscrepanciesVoldrvOvsdb', False)
    
                # list of vdisks that are in model but are not in volumedriver
                missinginvolumedriver = []
    
                # list of volumes that are in volumedriver but are not in model
                missinginmodel = []
    
                # fetch configfile of vpool for the volumedriver
                config_file = self.utility.get_config_file_path(vp.name, self.machine_id, 1, vp.guid)
                voldrv_client = src.LocalStorageRouterClient(config_file)
    
                # collect data from volumedriver
                try:
                    voldrv_volume_list = voldrv_client.list_volumes()
                except ClusterNotReachableException:
                    self.LOGGER.failure("Seems like the volumedriver '{0}' is not running.".format(vp.name),
                                        'discrepancies_ovsdb_{0}'.format(vp.name))
                    continue
    
                vol_ids = [vdisk.volume_id for vdisk in vp.vdisks]
    
                # crossreference model vs. volumedriver
                for vdisk in vol_ids:
                    if vdisk not in voldrv_volume_list:
                        missinginvolumedriver.append(vdisk)
    
                # crossreference volumedriver vs. model
                for voldrv_id in voldrv_volume_list:
                    if voldrv_id not in vol_ids:
                        missinginmodel.append(voldrv_id)
    
                # display discrepancies for vPool
                if len(missinginvolumedriver) != 0:
                    self.LOGGER.warning("Detected volumes that are MISSING in volumedriver but ARE in ovsdb in vPool "
                                        "'{0}': {1}".format(vp.name, ', '.join(missinginvolumedriver)),
                                        'discrepancies_ovsdb_{0}'.format(vp.name))
                else:
                    self.LOGGER.success("NO discrepancies found for ovsdb in vPool '{0}'".format(vp.name),
                                        'discrepancies_ovsdb_{0}'.format(vp.name))
    
                if len(missinginmodel) != 0:
                    self.LOGGER.warning("Detected volumes that are AVAILABLE in volumedriver "
                                        "but ARE NOT in ovsdb in vPool "
                                        "'{0}': {1}".format(vp.name, ', '.join(missinginmodel)),
                                        'discrepancies_voldrv_{0}'.format(vp.name))
                else:
                    self.LOGGER.success("NO discrepancies found for voldrv in vPool '{0}'".format(vp.name),
                                        'discrepancies_voldrv_{0}'.format(vp.name))
            else:
                self.LOGGER.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                 'discrepancies_voldrv_{0}'.format(vp.name))

    def check_for_halted_volumes(self):
        """
        Checks for halted volumes on a single or multiple vPools
        """

        self.LOGGER.info("Checking for halted volumes: ", 'checkHaltedVolumes', False)

        vpools = VPoolList.get_vpools()

        if len(vpools) != 0:

            for vp in vpools:
                
                if vp.guid in self.machine_details.vpools_guids:

                    haltedvolumes = []

                    self.LOGGER.info("Checking vPool '{0}': ".format(vp.name),
                                     'halted_title', False)

                    config_file = self.utility.get_config_file_path(vp.name, self.machine_id, 1, vp.guid)
                    voldrv_client = src.LocalStorageRouterClient(config_file)

                    try:
                        voldrv_volume_list = voldrv_client.list_volumes()
                    except ClusterNotReachableException:
                        self.LOGGER.failure("Seems like the Volumedriver {0} is not running.".format(vp.name),
                                            'halted_{0}'.format(vp.name))
                        continue

                    for volume in voldrv_volume_list:
                        # check if volume is halted, returns: 0 or 1
                        try:
                            if int(voldrv_client.info_volume(volume).halted):
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

                    # print all results
                    if len(haltedvolumes) > 0:
                        self.LOGGER.failure("Detected volumes that are HALTED in vPool '{0}': {1}"
                                            .format(vp.name, ', '.join(haltedvolumes)), 'halted_{0}'
                                            .format(vp.name))
                    else:
                        self.LOGGER.success("No halted volumes detected in vPool '{0}'"
                                            .format(vp.name), 'halted_{0}'.format(vp.name))
                else:
                    self.LOGGER.skip("Skipping vPool '{0}' because it is not living here ...".format(vp.name),
                                     'halted_{0}'.format(vp.name))

        else:
            self.LOGGER.skip("No vPools found!".format(len(vpools)), 'halted_nofound')
