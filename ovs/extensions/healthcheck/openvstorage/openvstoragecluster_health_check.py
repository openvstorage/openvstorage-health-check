#!/usr/bin/python

# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Open vStorage Health Check module
"""

import os
import grp
import stat
import glob
import time
import psutil
import signal
import socket
import threading
import subprocess
from pwd import getpwuid
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.system import System
from ovs.dal.lists.servicelist import ServiceList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.lib.storagerouter import StorageRouterController
from ovs.extensions.healthcheck.utils.extension import Utils
from ovs.log.healthcheck_logHandler import HCLogHandler
import volumedriver.storagerouter.storagerouterclient as src


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

        self.module = 'openvstorage'
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
                                             "swiftstack-node"
                                             ]
        # 1. key -> service name (string)
        #
        # 2. value -> ports (list)
        self.req_side_ports = {'nginx': ['80', '443'], 'memcached': ['11211']}

        # 1. key -> absolute directory name (string)
        #
        # 2. value -> rights in linux style format (string)
        self.req_map_rights = {'/tmp': '777', '/var/tmp': '777'}

        # 1. key -> absolute directory or log name (string)
        #
        # 2. value -> required user and group (dict)
        self.req_map_owners = {'/var/log/syslog': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/auth.log': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/kern.log': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/wtmp': {'user': 'root', 'group': 'utmp'},
                               '/var/log/btmp': {'user': 'root', 'group': 'utmp'},
                               '/etc/gshadow': {'user': 'root', 'group': 'shadow'},
                               '/var/cache/man': {'user': 'man', 'group': 'root'},
                               '/etc/shadow': {'user': 'root', 'group': 'shadow'}
                               }

        # 1. for dir required options: AS key -> prefix (string)
        #    AS value -> list, substring of prefix (string) , type -> string (dir)
        #    contains_nested -> Boolean (contains nested dirs and files)
        #
        # 2. for file required options: type -> string (file)
        self.logging = {'/var/log/upstart': {'prefix': ['ovs', 'asd'], 'type': 'dir', 'contains_nested': False},
                        '/var/log/ovs': {'prefix': None, 'type': 'dir', 'contains_nested': True},
                        '/var/log/gunicorn': {'prefix': None, 'type': 'dir', 'contains_nested': False},
                        '/var/log/rabbitmq': {'prefix': None, 'type': 'dir', 'contains_nested': False},
                        '/var/log/nginx': {'prefix': None, 'type': 'dir', 'contains_nested': False},
                        '/var/log/arakoon': {'prefix': None, 'type': 'dir', 'contains_nested': True},
                        '/var/log/memcached.log': {'type': 'file'}
                        }

    def get_local_settings(self):
        """
        Fetch settings of the local Open vStorage node
        """

        self.LOGGER.logger("Fetching LOCAL information of node: ", self.module, 3, 'local_info', False)
        self.LOGGER.logger("Cluster ID: {0}".format(self.utility.cluster_id), self.module, 1, 'lc2', False)
        self.LOGGER.logger("Storagerouter ID: {0}".format(self.machine_id), self.module, 1, 'lc2', False)
        self.LOGGER.logger("Environment TYPE: {0}".format(self.machine_details.node_type), self.module, 1, 'lc3', False)
        self.LOGGER.logger("Environment VERSION: {0}".format(self.utility.ovs_version), self.module, 1, 'lc4', False)

    def check_size_of_log_files(self):
        """
        Checks the size of the initialized log files
        """

        collection = []
        good_size = []
        to_big = []

        self.LOGGER.logger("Checking if logfiles their size is not bigger than {0} MB: ".format(self.max_logsize),
                           self.module, 3, 'checkLogfilesSize', False)

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
                self.LOGGER.logger("Logfile '{0}' has a GOOD size!".format(c_files), self.module, 1,
                                   'log_{0}'.format(c_files), False)
            else:
                to_big.append(c_files)
                self.LOGGER.logger("Logfile '{0}' is a big ass logfile!".format(c_files), self.module, 0,
                                   'log_{0}'.format(c_files), False)

        # end for unattended_install
        if self.LOGGER.unattended_mode:
            if len(to_big) != 0:
                self.LOGGER.logger("Some logfiles are too big, please check this!".format(c_files),
                                   self.module, 0, 'log_size')
            else:
                self.LOGGER.logger("ALL log files are ok!".format(c_files), self.module, 1, 'log_size')

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

    def check_hypervisor_management_information(self):
        """
        Check if Open vStorage is connected to a certain Hypervisor management center (e.g. VMware vCenter or Openstack)
        """

        self.LOGGER.logger("Checking if OVS is connected to any OpenStack or VMWare Management centers ...",
                           self.module, 3, 'checkHypervisorManagementInformation', False)
        management_centers = MgmtCenterList().get_mgmtcenters()

        # get available openstack/vmware management centers
        if len(management_centers) != 0:
            for center in management_centers:

                # get general management center information
                self.LOGGER.logger("OVS is connected to: {0}".format(center.type), self.module, 1,
                                   'manc_ovs_connected'.format(center.type), False)
                self.LOGGER.logger("Name: {0}".format(center.name), self.module, 1, 'manc_name_{0}'
                                   .format(center.name), False)
                self.LOGGER.logger("IP-address: {0}:{1}".format(center.ip, center.port), self.module, 1,
                                   'manc_ip_{0}_{1}'.format(center.ip, center.port), False)
                self.LOGGER.logger("user: {0}".format(center.username), self.module, 1, 'manc_user_{0}'
                                   .format(center.username), False)

        else:
            self.LOGGER.logger("No OpenStack/VMWare management center connected!", self.module, 5,
                               'manc_ovs_connected')

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

        self.LOGGER.logger("Checking port {0} of service {1} ...".format(port, process_name), self.module, 3,
                           '_is_port_listening', False)
        if self._check_port_connection(port):
            self.LOGGER.logger("Connection successfully established!", self.module, 1, 'port_{0}_{1}'
                               .format(process_name, port))
        else:
            self.LOGGER.logger("Connection FAILED to service '{1}' on port {0}".format(port, process_name),
                               self.module, 0, 'port_{0}_{1}'.format(process_name, port))

    def check_required_ports(self):
        """
        Checks all ports of Open vStorage components (framework, memcached, nginx, rabbitMQ and celery)
        """

        self.LOGGER.logger("Checking PORT CONNECTIONS of several services ...", self.module, 3,
                           'check_required_ports', False)

        # check ports for OVS services
        self.LOGGER.logger("Checking OVS services ...", self.module, 3, 'checkOvsServicesPorts', False)
        for sr in ServiceList.get_services():
            if sr.storagerouter_guid == self.machine_details.guid:
                for port in sr.ports:
                    self._is_port_listening(sr.name, port)

        # check NGINX and memcached
        self.LOGGER.logger("Checking NGINX and Memcached ...", self.module, 3, 'checkNginxAndMemcached', False)

        for process, ports in self.req_side_ports.iteritems():
            for port in ports:
                self._is_port_listening(process, port)

        # Check Celery and RabbitMQ
        self.LOGGER.logger("Checking RabbitMQ/Celery ...", self.module, 3, 'checkRabbitmqCelery', False)

        if self.utility.node_type == "MASTER":
            pcommand = "celery inspect ping -b amqp://ovs:0penv5tor4ge@{0}//".format(self.machine_details.ip)
            pcel = self.utility.execute_bash_command(pcommand.format(process))
            if len(pcel) != 1 and 'pong' in pcel[1].strip():
                self.LOGGER.logger("Connection successfully established!", self.module, 1, 'port_celery')
            else:
                self.LOGGER.logger("Connection FAILED to service Celery, please check 'RabbitMQ' and 'ovs-workers'?",
                                   self.module, 0, 'port_celery')
        else:
            self.LOGGER.logger("RabbitMQ is not running/active on this server!", self.module, 5, 'port_celery')

    def check_ovs_packages(self):
        """
        Checks the availability of packages for Open vStorage
        """

        self.LOGGER.logger("Checking OVS packages: ", self.module, 3, 'check_ovs_packages', False)

        for package in self.openvstorageTotalPackageList:
            result = self.utility.execute_bash_command("apt-cache policy %s" % package)
            if len(result) != 1:
                self.LOGGER.logger(
                    "Package '%s' is present, with version '%s'" % (package, result[2].split(':')[1].strip()),
                    self.module, 1, 'package_{0}'.format(package))
            else:
                self.LOGGER.logger("Package '{0}' is NOT present ...".format(package), self.module, 5,
                                   'package_{0}'.format(package))
        return None

    def check_ovs_processes(self):
        """
        Checks the availability of processes for Open vStorage
        """

        self.LOGGER.logger("Checking LOCAL OVS services: ", self.module, 3, 'check_ovs_processes', False)

        if self.service_manager:
            for ovs_service in os.listdir("/etc/init"):
                if ovs_service.startswith("ovs-"):
                    process_name = ovs_service.split(".conf", 1)[0].strip()
                    if self.utility.check_status_of_service(process_name):
                        self.LOGGER.logger("Service '{0}' is running!".format(process_name), self.module, 1,
                                           'process_{0}'.format(process_name))
                    else:
                        self.LOGGER.logger("Service '{0}' is NOT running, please check this... ".format(process_name),
                                           self.module, 0, 'process_{0}'.format(process_name))
        else:
            self.LOGGER.logger("Other service managers than 'init' are not yet supported!", self.module, 4,
                               'hc_process_supported', False)

    def _method_handler(self, signum, frame):
        """
        Method handler for python signals, specifically used to time-out when a call to a process is taking too long.
        Use in combination with: `signal.signal(signal.SIGALRM, self._method_handler)`

        @raises Exception
        """

        warning = "SPOTTED a PROCESS who is taking to long! Signum: {0} ; Frame {1}".format(signum, frame)
        self.LOGGER.logger(warning, self.module, 3, 'spotted_idle_process', False)
        raise Exception(warning)

    def _check_celery(self):
        """
        Preliminary/Simple check for Celery and RabbitMQ component
        """

        # try if celery works smoothly
        guid = self.machine_details.guid
        machine_id = self.machine_details.machine_id
        obj = StorageRouterController.get_support_info.s(guid).apply_async(
              routing_key='sr.{0}'.format(machine_id)).get()

        # reset possible alarm
        signal.alarm(0)

        if obj:
            return True
        else:
            return False

    def _extended_check_celery(self):
        """
        Extended check for Celery and RabbitMQ component
        """

        rlogs = "'/var/log/rabbitmq/startup_*' or '/var/log/rabbitmq/shutdown_*'"

        self.LOGGER.logger("Commencing deep check for celery/RabbitMQ", self.module, 2, '_extended_check_celery', False)

        # check ovs-workers
        if not self.utility.check_status_of_service('ovs-workers'):
            self.LOGGER.logger("Seems like ovs-workers are down, maybe due to RabbitMQ?", self.module, 0,
                               'process_ovs-workers', False)
            # check rabbitMQ status
            if self.utility.check_status_of_service('rabbitmq-server'):
                # RabbitMQ seems to be DOWN
                self.LOGGER.logger("RabbitMQ seems to be DOWN, please check logs in {0}".format(rlogs), self.module,
                                   0, 'RabbitIsDown', False)
                return False
            else:
                # RabbitMQ is showing it's up but lets check some more stuff
                list_status = self.utility.execute_bash_command('rabbitmqctl list_queues')[1]
                if "Error" in list_status:
                    self.LOGGER.logger(
                        "RabbitMQ seems to be UP but it is not functioning as it should! Maybe it has been"
                        " shutdown through 'stop_app'? Please check logs in {0}".format(
                         rlogs), self.module, 0, 'RabbitSeemsUpButNotFunctioning', False)
                    return False
                elif "Error: {aborted" in list_status:
                    self.LOGGER.logger(
                        "RabbitMQ seems to be DOWN but it is not functioning as it should! Please check logs in {0}"
                        .format(rlogs), self.module, 0, 'RabbitSeemsDown', False)
                    return False
                else:
                    self.LOGGER.logger("RabbitMQ process is running as it should, start checking the queues... ",
                                       self.module, 1, 'checkQueuesButRabbitIsWorking', False)
        else:
            self.LOGGER.logger("OVS workers are UP! Maybe it is stuck? Start checking the queues...", self.module, 0,
                               'checkQueuesButOvsWorkersAreUp', False)

        # fetch remaining tasks on node
        self.LOGGER.logger("Starting deep check for RabbitMQ!", self.module, 3, 'DeepCheckRabbit', False)

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
                    self.LOGGER.logger(
                        "Seems like queue '{0}' is building up! Please verify this with 'rabbitmqctl list_queues "
                        "| grep ovs_'".format(output_02.index(j)), self.module, 2, 'process_celery_queue_{0}'
                        .format(output_02.index(j)), False)
                    lost_queues.append(output_02.index(j))
                elif int(i) > int(j):
                    # queue is decreasing
                    self.LOGGER.logger("Seems like queue '{0}' is working fine!".format(output_02.index(j)),
                                       self.module, 1, 'process_celery_queue_{0}'.format(output_02.index(j)), False)
            # post-check
            if len(lost_queues) > 0:
                return False
            else:
                return True
        else:
            self.LOGGER.logger(
                "Seems like all Celery queues are stuck, you should check: 'rabbitmqctl list_queues' and 'ovs-workers'",
                self.module, 0, 'process_celery_all_queues', False)
            return False

    def check_ovs_workers(self):
        """
        Extended check of the Open vStorage workers; When the simple check fails, it will execute a full/deep check.
        """

        self.LOGGER.logger("Checking if OVS-WORKERS are running smoothly: ", self.module, 3, 'check_ovs_workers', False)

        # init timout for x amount of sec for celery
        signal.signal(signal.SIGALRM, self._method_handler)
        signal.alarm(7)

        # checking celery
        try:
            # basic celery check
            self._check_celery()
            self.LOGGER.logger("The OVS-WORKERS are working smoothly!", self.module, 1, 'process_celery')
        except Exception, ex:
            # kill alarm
            signal.alarm(0)

            # apparently the basic check failed, so we are going crazy
            self.LOGGER.logger(
                "Unexpected exception received during check of celery! Are RabbitMQ and/or ovs-workers running?"
                " Traceback: {0}".format(ex), self.module, 0, 'process_celery')

            # commencing deep check
            if not self._extended_check_celery():
                self.LOGGER.logger("Please verify the integrety of 'RabbitMQ' and 'ovs-workers'", self.module, 0,
                                   'CheckIntegrityOfWorkers', False)
                return False
            else:
                self.LOGGER.logger("Deep check finished successfully but did not find anything... :(", self.module, 1,
                                   'DeepCheckDidNotFindAnything', False)
                return True

    def check_required_dirs(self):
        """
        Checks the directories their rights and owners for mistakes
        """

        self.LOGGER.logger("Checking if OWNERS are set correctly on certain maps: ", self.module, 3,
                           'checkRequiredMaps_owners', False)
        for dirname, owner_settings in self.req_map_owners.iteritems():
            if owner_settings.get('user') == self._get_owner_of_file(dirname) and owner_settings.get(
                    'group') == self._get_group_of_file(dirname):
                self.LOGGER.logger("Directory '{0}' has correct owners!".format(dirname), self.module, 1,
                                   'dir_{0}'.format(dirname))
            else:
                self.LOGGER.logger(
                    "Directory '{0}' has INCORRECT owners! It must be OWNED by USER={1} and GROUP={2}"
                    .format(dirname, owner_settings.get('user'), owner_settings.get('group')),
                    self.module, 0, 'dir_{0}'.format(dirname))

        self.LOGGER.logger("Checking if Rights are set correctly on certain maps: ", self.module, 3,
                           'checkRequiredMaps_rights', False)
        for dirname, rights in self.req_map_rights.iteritems():
            if self._check_rights_of_file(dirname, rights):
                self.LOGGER.logger("Directory '{0}' has correct rights!".format(dirname), self.module, 1,
                                   'dir_{0}'.format(dirname))
            else:
                self.LOGGER.logger("Directory '{0}' has INCORRECT rights! It must be CHMOD={1} "
                                   .format(dirname, rights), self.module, 0, 'dir_{0}'.format(dirname))

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

        self.LOGGER.logger("Checking DNS resolving: ", self.module, 3, 'titleDnsResolving', False)
        try:
            socket.gethostbyname(fqdn)
            self.LOGGER.logger("DNS resolving works!", self.module, 1, 'dns_resolving')
            return True
        except Exception:
            self.LOGGER.logger("DNS resolving doesn't work, please check /etc/resolv.conf or add correct"
                               " DNS server and make it immutable: 'sudo chattr +i /etc/resolv.conf'!",
                               self.module, 0, 'dns_resolving')
            return False

    def get_zombied_and_dead_processes(self):
        """
        Finds zombied or dead processes on a local machine
        """

        zombie_processes = []
        dead_processes = []

        self.LOGGER.logger("Checking for zombie/dead processes: ", self.module, 3, 'checkForZombieProcesses', False)

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
            self.LOGGER.logger("There are NO zombie processes on this node!", self.module, 1, 'process_zombies')
        else:
            self.LOGGER.logger("We DETECTED zombie processes on this node: {0}".format(', '.join(zombie_processes)),
                               self.module, 2, 'process_zombies')

        # check if there dead processes
        if len(dead_processes) == 0:
            self.LOGGER.logger("There are NO dead processes on this node!", self.module, 1, 'process_dead')
        else:
            self.LOGGER.logger("We DETECTED dead processes on this node: {0}".format(', '.join(dead_processes)),
                               self.module, 0, 'process_dead')

    def _check_filedriver(self, args1, vp_name, test_name):
        """
        Async method to checks if a FILEDRIVER works on a vpool
        Always try to check if the file exists after performing this method

        @param args1: thread ID; use like this
        `t = threading.Thread(target=self._check_filedriver, args=(1, vp.name, name))`
        @param vp_name: name of the vpool
        @param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)

        @type args1: int
        @type vp_name: str
        @type test_name: str

        @return: True if succeeded, False if failed

        @rtype: bool
        """

        # this method is not meant to be executed in serial, it is meant to be executed in parallel as a thread
        try:
            self.utility.execute_bash_command("touch /mnt/{0}/{1}.xml".format(vp_name, test_name))
            return True
        except Exception as e:
            self.LOGGER.logger("Filedriver_check on vPool '{0}' got exception: {1}".format(vp_name, e), self.module, 6,
                               'check_filedriver_{0}_thread_exception'.format(vp_name))
            return False

    def _check_volumedriver(self, args1, vp_name, test_name):
        """
        Async method to checks if a VOLUMEDRIVER works on a vpool
        Always try to check if the file exists after performing this method

        @param args1: thread ID; use like this
        `t = threading.Thread(target=self._check_volumedriver, args=(1, vp.name, name))`
        @param vp_name: name of the vpool
        @param test_name: name of the test file (e.g. `ovs-healthcheck-MACHINE_ID`)

        @type args1: int
        @type vp_name: str
        @type test_name: str

        @return: True if succeeded, False if failed

        @rtype: bool
        """

        # this method is not meant to be executed in serial, it is meant to be executed in parallel as a thread
        try:
            subprocess.check_output("truncate -s 10GB /mnt/{0}/{1}.raw".format(vp_name, test_name),
                                    stderr=subprocess.STDOUT, shell=True)
            return True
        except Exception as e:
            self.LOGGER.logger("Volumedriver_check on vPool '{0}' got exception: {1}".format(vp_name, e),
                               self.module, 6, 'check_volumedriver_{0}_thread_exception'.format(vp_name))
            return False

    def check_filedrivers(self):
        """
        Checks if the FILEDRIVERS work on a local machine (compatible with multiple vPools)
        """

        filedriversnotworking = []
        name = "ovs-healthcheck-test-{0}".format(self.machine_id)

        self.LOGGER.logger("Checking filedrivers: ", self.module, 3, 'check_filedriver', False)

        vpools = VPoolList.get_vpools()

        # perform tests
        if len(vpools) != 0:

            for vp in vpools:

                # check filedriver
                t = threading.Thread(target=self._check_filedriver, args=(1, vp.name, name))
                t.daemon = True
                t.start()

                time.sleep(5)

                # if thread is still alive after x seconds or got exception, something is wrong
                if t.isAlive() or not os.path.exists("/mnt/{0}/{1}.xml".format(vp.name, name)):
                    filedriversnotworking.append(vp.name)

                # clean-up
                if len(filedriversnotworking) == 0:
                    self.utility.execute_bash_command("rm -f /mnt/{0}/{1}.xml".format(vp.name, name))

            # check if filedrivers are OK!
            if len(filedriversnotworking) == 0:
                self.LOGGER.logger("All filedrivers seem to be working fine!", self.module, 1, 'filedrivers')
            else:
                self.LOGGER.logger("Some filedrivers seem to have some problems: {0}"
                                   .format(', '.join(filedriversnotworking)), self.module, 0, 'filedrivers')

        else:
            self.LOGGER.logger("No vPools found!", self.module, 5, 'filedrivers')

    def check_volumedrivers(self):
        """
        Checks if the VOLUMEDRIVERS work on a local machine (compatible with multiple vPools)
        """

        volumedriversnotworking = []
        name = "ovs-healthcheck-test-{0}".format(self.machine_id)

        self.LOGGER.logger("Checking volumedrivers: ", self.module, 3, 'check_volumedrivers', False)

        vpools = VPoolList.get_vpools()

        if len(vpools) != 0:
            # perform tests
            for vp in vpools:

                # check volumedrivers
                t = threading.Thread(target=self._check_volumedriver, args=(1, vp.name, name))
                t.daemon = True
                t.start()

                time.sleep(5)

                # if thread is still alive after x seconds or got exception, something is wrong
                if t.isAlive() or not os.path.exists("/mnt/{0}/{1}.raw".format(vp.name, name)):
                    volumedriversnotworking.append(vp.name)

                # clean-up
                if len(volumedriversnotworking) == 0:
                    self.utility.execute_bash_command("rm -f /mnt/{0}/{1}.raw".format(vp.name, name))

            # check if filedrivers are OK!
            if len(volumedriversnotworking) == 0:
                self.LOGGER.logger("All volumedrivers seem to be working fine!", self.module, 1, 'volumedrivers')
            else:
                self.LOGGER.logger("Some volumedrivers seem to have some problems: {0}"
                                   .format(', '.join(volumedriversnotworking)), self.module, 0, 'volumedrivers')

        else:
            self.LOGGER.logger("No vPools found!", self.module, 5, 'volumedrivers')

    def check_model_consistency(self):
        """
        Checks if the model consistency of OVSDB vs. VOLUMEDRIVER and does a preliminary check on RABBITMQ
        """

        self.LOGGER.logger("Checking model consistency: ", self.module, 3, 'check_model_consistency', False)

        #
        # RabbitMQ check: cluster verification
        #

        self.LOGGER.logger("Precheck: verification of RabbitMQ cluster: ", self.module, 3,
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
                    self.LOGGER.logger("Seems like the RabbitMQ cluster has 'partition' problems, please check this...",
                                       self.module, 0, 'process_rabbitmq', False)
                else:
                    self.LOGGER.logger("RabbitMQ does not seem to have 'partition' problems :D", self.module, 1,
                                       'process_rabbitmq', False)
            else:
                self.LOGGER.logger("Seems like the RabbitMQ cluster has errors, maybe it is offline?", self.module, 0,
                                   'process_rabbitmq', False)

        else:
            self.LOGGER.logger("RabbitMQ is not running/active on this server!", self.module, 5,
                               'process_rabbitmq', False)

        #
        # Checking consistency of volumedriver vs. ovsdb and backwards
        #

        for vp in VPoolList.get_vpools():

            self.LOGGER.logger("Checking consistency of volumedriver vs. ovsdb for vPool '{0}': ".format(vp.name),
                               self.module, 3, 'checkDiscrepanciesVoldrvOvsdb', False)

            # list of vdisks that are in model but are not in volumedriver
            missinginvolumedriver = []

            # list of volumes that are in volumedriver but are not in model
            missinginmodel = []

            # fetch configfile of vpool for the volumedriver
            config_file = self.utility.get_config_file_path(vp.name, self.machine_id, 1, vp.guid)
            voldrv_client = src.LocalStorageRouterClient(config_file)

            # collect data from volumedriver
            voldrv_volume_list = voldrv_client.list_volumes()

            # collect data from model
            model_vdisk_list = vp.vdisks

            # crossreference model vs. volumedriver
            for vdisk in model_vdisk_list:
                if not vdisk.volume_id in voldrv_volume_list:
                    missinginvolumedriver.append(vdisk.volume_id)

            # crossreference volumedriver vs. model
            # (This can be a performance bottleneck on heavy env. due to nested for loops)
            for volume in voldrv_volume_list:
                for vdisk in model_vdisk_list:
                    if str(volume) != vdisk.volume_id and len(model_vdisk_list) == (model_vdisk_list.index(vdisk)+1):
                        missinginmodel.append(volume)

            # display discrepancies for vPool
            if len(missinginvolumedriver) != 0:
                self.LOGGER.logger("Detected volumes that are MISSING in volumedriver but ARE in ovsdb in vPool "
                                   "'{0}': {1}".format(vp.name, ', '.join(missinginvolumedriver)), self.module, 0,
                                   'discrepancies_ovsdb_{0}'.format(vp.name))
            else:
                self.LOGGER.logger("NO discrepancies found for ovsdb in vPool '{0}'".format(vp.name), self.module, 1,
                                   'discrepancies_ovsdb_{0}'.format(vp.name))

            if len(missinginmodel) != 0:
                self.LOGGER.logger("Detected volumes that are AVAILABLE in volumedriver but ARE NOT in ovsdb in vPool "
                                   "'{0}': {1}".format(vp.name, ', '.join(missinginmodel)), self.module, 0,
                                   'discrepancies_voldrv_{0}'.format(vp.name))
            else:
                self.LOGGER.logger("NO discrepancies found for voldrv in vPool '{0}'".format(vp.name), self.module, 1,
                                   'discrepancies_voldrv_{0}'.format(vp.name))

    def check_for_halted_volumes(self):
        """
        Checks for halted volumes on a single or multiple vPools
        """

        self.LOGGER.logger("Checking for halted volumes: ", self.module, 3, 'checkHaltedVolumes', False)

        vpools = VPoolList.get_vpools()

        if len(vpools) != 0:

            for vp in vpools:

                haltedvolumes = []

                self.LOGGER.logger("Checking vPool '{0}': ".format(vp.name), self.module, 3,
                                   'checkVPOOL_{0}'.format(vp.name), False)

                config_file = self.utility.get_config_file_path(vp.name, self.machine_id, 1, vp.guid)
                voldrv_client = src.LocalStorageRouterClient(config_file)

                for volume in voldrv_client.list_volumes():
                    # check if volume is halted, returns: 0 or 1
                    if int(self.utility.convert_xml_to_json(voldrv_client.info_volume(volume))["boost_serialization"]
                           ["XMLRPCVolumeInfo"]["halted"]):
                        haltedvolumes.append(volume)

                # print all results
                if len(haltedvolumes) > 0:
                    self.LOGGER.logger("Detected volumes that are HALTED in volumedriver in vPool '{0}': {1}"
                                       .format(vp.name, ', '.join(haltedvolumes)), self.module, 0,
                                       'halted')
                else:
                    self.LOGGER.logger("No halted volumes detected in vPool '{0}'"
                                       .format(vp.name), self.module, 1,
                                       'halted')

        else:
            self.LOGGER.logger("No vPools found!".format(len(vpools)), self.module, 5, 'halted')
