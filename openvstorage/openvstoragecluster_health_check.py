#!/usr/bin/python

"""
Title: Open vStorage Health Check
Description: Checks the OVS health 
Maintainer: Jonas Libbrecht
"""

"""
Section: Import package(s)
"""

# general packages
import os
import grp
import sys
import stat
import glob
import time
import socket
import signal
import psutil
import commands
import threading
import subprocess
from pwd import getpwuid

# ovs packages
sys.path.append('/opt/OpenvStorage')
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.generic.system import System
from ovs.dal.lists.servicelist import ServiceList
from ovs.dal.lists.pmachinelist import PMachineList
from ovs.dal.lists.mgmtcenterlist import MgmtCenterList
from ovs.lib.storagerouter import StorageRouterController
import volumedriver.storagerouter.storagerouterclient as src

# import health check utilities
sys.path.append('../utils')
from utils import Utils

"""
Section: Classes
"""


class OpenvStorageHealthCheck:
    def __init__(self, utility=Utils(False)):
        self.module = 'openvstorage'
        self.utility = utility
        self.service_manager = self.utility.detectServiceManager()
        self.machine_details = System.get_my_storagerouter()
        self.machine_id = System.get_my_machine_id()
        self.max_logsize = 500  # in MB
        self.openvstorageTotalPackageList = ["openvstorage", "openvstorage-backend", "openvstorage-backend-core",
                                             "openvstorage-backend-webapps", "openvstorage-core", "openvstorage-hc",
                                             "openvstorage-sdm", "openvstorage-webapps", "openvstorage-unittests",
                                             "alba", "volumedriver-base", "volumedriver-server", "nginx", "memcached",
                                             "rabbitmq-server", "qemu-kvm", "virtinst", "openvpn", "ntp"
                                             ]
        self.req_side_ports = {'nginx': ['80', '443'], 'memcached': ['11211']}
        self.req_map_rights = {'/tmp': '777', '/var/tmp': '777'}
        self.req_map_owners = {'/var/log/syslog': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/auth.log': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/kern.log': {'user': 'syslog', 'group': 'adm'},
                               '/var/log/wtmp': {'user': 'root', 'group': 'utmp'},
                               '/var/log/btmp': {'user': 'root', 'group': 'utmp'},
                               '/etc/gshadow': {'user': 'root', 'group': 'shadow'},
                               '/var/cache/man': {'user': 'man', 'group': 'root'},
                               '/etc/shadow': {'user': 'root', 'group': 'shadow'}
                               }
        # 1. for dir required options: prefix -> list (via grep), type -> string (dir),
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

    def checkSizeOfLogFiles(self):
        collection = []
        good_size = []
        to_big = []

        self.utility.logger("Checking if logfiles their size is not bigger than {0} MB: ".format(self.max_logsize), self.module, 3, 'checkLogfilesSize', False)

        # collect log files
        for log, settings in self.logging.iteritems():
            if settings.get('type') == 'dir':
                # check if dir contains files
                files = self._listLogsInDirectory(log)
                # check if given dir has files
                if len(files) != 0:
                    # check size of log files
                    for file in files:
                        if settings.get('prefix') != None:
                            for prefix in list(settings.get('prefix')):
                                if prefix in file:
                                    collection.append(file)
                        else:
                            collection.append(file)

                # check if has nested_dirs and nested_files
                if settings.get('contains_nested'):
                    nested_dirs = self._listDirsInDirectory(log)
                    for dir in nested_dirs:
                        nested_files = self._listLogsInDirectory(log+"/"+dir)
                        if len(nested_files) != 0:
                            # check size of log files
                            for nested_file in nested_files:
                                if settings.get('prefix') != None:
                                    for prefix in list(settings.get('prefix')):
                                        if prefix in file:
                                            collection.append(nested_file)
                                else:
                                    collection.append(nested_file)
            else:
                # file
                collection.append(log)

        # process log files
        for c_files in collection:
            # check if logfile is larger than max_size
            if os.stat(c_files).st_size < 1024000 * self.max_logsize:
                good_size.append(c_files)
                self.utility.logger("Logfile '{0}' has a GOOD size!".format(c_files), self.module, 1, 'log_{0}'.format(c_files), False)
            else:
                to_big.append(c_files)
                self.utility.logger("Logfile '{0}' is a big ass logfile!".format(c_files), self.module, 0, 'log_{0}'.format(c_files), False)

        # end for unattended_install
        if self.utility.unattended_mode:
            if len(to_big) != 0:
                self.utility.logger("Some logfiles are too big, please check this!".format(c_files), self.module, 0, 'log_size')
            else:
                self.utility.logger("ALL log files are ok!".format(c_files), self.module, 1, 'log_size')

    def _listLogsInDirectory(self, pwd):
        return glob.glob("{0}/*.log".format(pwd))

    def _listDirsInDirectory(self, pwd):
        return next(os.walk(pwd))[1]

    def checkHypervisorManagementInformation(self):
        self.utility.logger("Checking if OVS is connected to any OpenStack or VMWare Management centers ...",
                             self.module, 3, 'checkHypervisorManagementInformation', False)
        management_centers = MgmtCenterList().get_mgmtcenters()

        # get available openstack/vmware management centers
        if len(management_centers) != 0:
            for center in management_centers:

                # get general management center information
                self.utility.logger("OVS is connected to: {0}".format(center.type), self.module, 1, 'manc_ovs_connected'.format(center.type), False)
                self.utility.logger("Name: {0}".format(center.name), self.module, 1, 'manc_name_{0}'.format(center.name), False)
                self.utility.logger("IP-address: {0}:{1}".format(center.ip, center.port), self.module, 1, 'manc_ip_{0}_{1}'.format(center.ip, center.port), False)
                self.utility.logger("user: {0}".format(center.username), self.module, 1, 'manc_user_{0}'.format(center.username), False)

        else:
            self.utility.logger("No OpenStack/VMWare management center connected!", self.module, 5, 'manc_ovs_connected')

    def _fetchComputeNodeDetailByIp(self, node_ip):
        return PMachineList().get_by_ip(str(node_ip))

    def _fetchComputeNodesPerCenterByIp(self, management_ip):
        return MgmtCenterList().get_by_ip(str(management_ip)).hosts

    def _checkPortConnection(self, port_number):
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

    def _isPortListening(self, process_name, port):
        self.utility.logger("Checking port {0} of service {1} ...".format(port, process_name), self.module, 3, '_isPortListening', False)
        if self._checkPortConnection(port):
            self.utility.logger("Connection successfully established!", self.module, 1, 'port_{0}_{1}'.format(process_name, port))
        else:
            self.utility.logger("Connection FAILED to service '{1}' on port {0}".format(port, process_name),
                                 self.module, 0, 'port_{0}_{1}'.format(process_name, port))

    def checkRequiredPorts(self):
        self.utility.logger("Checking PORT CONNECTIONS of several services ...", self.module, 3, 'checkRequiredPorts', False)

        # check ports for OVS services
        self.utility.logger("Checking OVS services ...", self.module, 3, 'checkOvsServicesPorts', False)
        for sr in ServiceList.get_services():
            if sr.storagerouter_guid == self.machine_details.guid:
                for port in sr.ports:
                    self._isPortListening(sr.name, port)

        # check NGINX and memcached
        self.utility.logger("Checking NGINX and Memcached ...", self.module, 3, 'checkNginxAndMemcached', False)

        for process, ports in self.req_side_ports.iteritems():
            for port in ports:
                self._isPortListening(process, port)

        # Check Celery and RabbitMQ
        self.utility.logger("Checking RabbitMQ/Celery ...", self.module, 3, 'checkRabbitmqCelery', False)
        PCOMMAND = "celery inspect ping -b amqp://ovs:0penv5tor4ge@{0}//".format(self.machine_details.ip)
        pcel = self.utility.executeBashCommand(PCOMMAND.format(process))
        if len(pcel) != 1 and 'pong' in pcel[1].strip():
            self.utility.logger("Connection successfully established!", self.module, 1, 'port_celery')
        else:
            self.utility.logger("Connection FAILED to service Celery, please check 'RabbitMQ' and 'ovs-workers'?",
                                 self.module, 0, 'port_celery')
        return None

    def checkSSHConnectionToOtherNodes(self):
        return True

    def checkOvsPackages(self):
        self.utility.logger("Checking OVS packages: ", self.module, 3, 'checkOvsPackages', False)

        for package in self.openvstorageTotalPackageList:
            result = self.utility.executeBashCommand("apt-cache policy %s" % package)
            if len(result) != 1:
                self.utility.logger(
                    "Package '%s' is present, with version '%s'" % (package, result[2].split(':')[1].strip()),
                    self.module, 1, 'package_{0}'.format(package))
            else:
                self.utility.logger("Package '%s' is NOT present ..." % (package), self.module, 5, 'package_{0}'.format(package))
        return None

    def checkOvsProcesses(self):
        self.utility.logger("Checking LOCAL OVS services: ", self.module, 3, 'checkOVSProcesses', False)

        if self.service_manager:
            for ovs_service in os.listdir("/etc/init"):
                if ovs_service.startswith("ovs-"):
                    process_name = ovs_service.split(".conf", 1)[0].strip()
                    if self._checkStatusOfProcess(process_name):
                        self.utility.logger("Service '%s' is running!" % (process_name), self.module, 1, 'process_{0}'.format(process_name))
                    else:
                        self.utility.logger("Service '%s' is NOT running, please check this... " % (process_name),
                                             self.module, 0, 'process_{0}'.format(process_name))
            return None
        else:
            self.utility.logger("Other service managers than 'init' are not yet supported!", self.module, 4, 'hc_process_supported')

    def _checkStatusOfProcess(self, process_name, upstart=True):

        if self.service_manager:
            if upstart:
                result = self.utility.executeBashCommand("status {0}".format(process_name))
                if result[0].split()[1] == "start/running,":
                    return True
                elif result[0].split()[1] == "stop/waiting":
                    return False
                elif result[0].split()[1] == "start/pre-start,":
                    return False
                else:
                    #wrong process name
                    self.utility.logger("No matching UPSTART process with name {0} found, please check the process_name for errors or try to use 'upstart=False'".format(process_name), self.module, 4, 'process_{0}'.format(process_name), False)
            else:
                result = self.utility.executeBashCommand("service {0} status".format(process_name))
                if result[0].split()[1] == "start/running,":
                    return True
                elif result[0].split()[1] == "stop/waiting":
                    return False
                elif result[0].split()[1] == "start/pre-start,":
                    return False
                else:
                    # wrong process name or unhandled result
                    self.utility.logger("No matching process with name {0} found, please check the process_name for errors or try to use 'upstart=False'".format(process_name), self.module, 4, 'process_{0}'.format(process_name))
        else:
            self.utility.logger("Other service managers than 'init' are not yet supported!", self.module, 4, 'hc_process_supported', False)
            raise Exception("Unsupported service manager used")

    def _methodHandler(self, signum, frame):
        WARNING = "SPOTTED a PROCESS who is taking to long! The process that you are trying to reach is probably stuck!"
        self.utility.logger(WARNING, self.module, 3, 'spotted_idle_process', False)
        raise Exception(WARNING)

    def _checkCelery(self):
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

    def _extendedCheckCelery(self):
        RLOGS = "'/var/log/rabbitmq/startup_*' or '/var/log/rabbitmq/shutdown_*'"

        self.utility.logger("Commencing deep check for celery/RabbitMQ", self.module, 2, '_extendedCheckCelery', False)

        # check ovs-workers
        if not self._checkStatusOfProcess('ovs-workers'):
            self.utility.logger("Seems like ovs-workers are down, maybe due to RabbitMQ?", self.module, 0, 'process_ovs-workers', False)
            # check rabbitMQ status
            if "nodedown" in self.utility.executeBashCommand('service rabbitmq-server status')[1]:
                # RabbitMQ seems to be DOWN
                self.utility.logger("RabbitMQ seems to be DOWN, please check logs in {0}".format(RLOGS), self.module,
                                     0, 'RabbitIsDown', False)
                return False
            else:
                # RabbitMQ is showing it's up but lets check some more stuff
                if "Error" in self.utility.executeBashCommand('rabbitmqctl list_queues')[1]:
                    self.utility.logger(
                        "RabbitMQ seems to be UP but it is not functioning as it should! Maybe it has been shutdown through 'stop_app'? Please check logs in {0}".format(
                            RLOGS), self.module, 0, 'RabbitSeemsUpButNotFunctioning', False)
                    return False
                else:
                    self.utility.logger("RabbitMQ process is running as it should, start checking the queues... ",
                                         self.module, 1, 'checkQueuesButRabbitIsWorking', False)
        else:
            self.utility.logger("OVS workers are UP! Maybe it is stuck? Start checking the queues...", self.module, 0, 'checkQueuesButOvsWorkersAreUp', False)

        # fetch remaining tasks on node
        self.utility.logger("Starting deep check for RabbitMQ!", self.module, 3, 'DeepCheckRabbit', False)

        #
        # Rabbitmq check: queue verification
        #
        RCOMMAND = "rabbitmqctl list_queues | grep ovs_ | sed -e 's/[[:space:]]\+/ /g' | cut -d ' ' -f 2"
        output_01 = self.utility.executeBashCommand(RCOMMAND)
        time.sleep(15)
        output_02 = self.utility.executeBashCommand(RCOMMAND)

        # check diff/results and continue
        lost_queues = []
        if set(output_01) - set(output_02):
            # found some changed queue's!
            for i, j in zip(output_01, output_02):
                if int(i) < int(j):
                    # queue is building up
                    self.utility.logger(
                        "Seems like queue '{0}' is building up! Please verify this with 'rabbitmqctl list_queues | grep ovs_'".format(
                            output_02.index(j)), self.module, 2, 'process_celery_queue_{0}'.format(output_02.index(j)), False)
                    lost_queues.append(output_02.index(j))
                elif int(i) > int(j):
                    # queue is decreasing
                    self.utility.logger("Seems like queue '{0}' is working fine!".format(output_02.index(j)),
                                         self.module, 1, 'process_celery_queue_{0}'.format(output_02.index(j)), False)
            # post-check
            if len(lost_queues) > 0:
                return False
            else:
                return True
        else:
            self.utility.logger(
                "Seems like all Celery queues are stuck, you should check: 'rabbitmqctl list_queues' and 'ovs-workers'",
                self.module, 0, 'process_celery_all_queues', False)
            return False

    def checkOvsWorkers(self):
        self.utility.logger("Checking if OVS-WORKERS are running smoothly: ", self.module, 3, 'checkOvsWorkers', False)

        # init timout for x amount of sec for celery
        signal.signal(signal.SIGALRM, self._methodHandler)
        signal.alarm(7)

        # checking celery
        try:
            # basic celery check
            self._checkCelery()
            self.utility.logger("The OVS-WORKERS are working smoothly!", self.module, 1, 'process_celery')
        except Exception, ex:
            # kill alarm
            signal.alarm(0)

            # apparently the basic check failed, so we are going crazy
            self.utility.logger(
                "Unexpected exception received during check of celery! Are RabbitMQ and/or ovs-workers running? Traceback: {0}".format(
                    ex), self.module, 0, 'process_celery')

            # commencing deep check
            if not self._extendedCheckCelery():
                self.utility.logger("Please verify the integrety of 'RabbitMQ' and 'ovs-workers'", self.module, 0, 'CheckIntegrityOfWorkers', False)
                return False
            else:
                self.utility.logger("Deep check finished successfully but did not find anything... :(", self.module, 1, 'DeepCheckDidNotFindAnything', False)
                return True

    def checkRequiredDirs(self):

        self.utility.logger("Checking if OWNERS are set correctly on certain maps: ", self.module, 3, 'checkRequiredMaps_owners', False)
        for map, owner_settings in self.req_map_owners.iteritems():
            if owner_settings.get('user') == self._findOwnerOfFile(map) and owner_settings.get(
                    'group') == self._findGroupOfFile(map):
                self.utility.logger("Directory '{0}' has correct owners!".format(map), self.module, 1, 'dir_{0}'.format(map))
            else:
                self.utility.logger(
                    "Directory '{0}' has INCORRECT owners! It must be OWNED by USER={1} and GROUP={2}".format(map,
                                                                                                              owner_settings.get(
                                                                                                                  'user'),
                                                                                                              owner_settings.get(
                                                                                                                  'group')),
                    self.module, 0, 'dir_{0}'.format(map))

        self.utility.logger("Checking if Rights are set correctly on certain maps: ", self.module, 3, 'checkRequiredMaps_rights', False)
        for map, rights in self.req_map_rights.iteritems():
            if self._checkRightsOfFile(map, rights):
                self.utility.logger("Directory '{0}' has correct rights!".format(map), self.module, 1, 'dir_{0}'.format(map))
            else:
                self.utility.logger("Directory '{0}' has INCORRECT rights! It must be CHMOD={1} ".format(map, rights),
                                     self.module, 0, 'dir_{0}'.format(map))

        return True

    def _findOwnerOfFile(self, filename):
        return getpwuid(os.stat(filename).st_uid).pw_name

    def _findGroupOfFile(self, filename):
        return grp.getgrgid(os.stat(filename).st_gid).gr_name

    def _checkRightsOfFile(self, filename, rights):
        # convert default rights to octal
        oct_rights = int(str(rights), 8)

        # fetch file to start compare
        octal_rights_file = stat.S_IMODE(os.stat(filename).st_mode)

        #determine if rights are correct
        if oct_rights == octal_rights_file:
            return True
        else:
            return False

    def checkIfDNSResolves(self, fqdn="google.com"):
        self.utility.logger("Checking DNS resolving: ", self.module, 3, 'titleDnsResolving', False)
        try:
            socket.gethostbyname(fqdn)
            self.utility.logger("DNS resolving works!", self.module, 1, 'dns_resolving')
            return True
        except Exception:
            self.utility.logger("DNS resolving doesn't work, please check /etc/resolv.conf or add correct DNS server and make it immutable: 'sudo chattr +i /etc/resolv.conf'!", self.module, 0, 'dns_resolving')
            return False

    def findZombieAndDeadProcesses(self):
        zombie_processes = []
        dead_processes = []

        self.utility.logger("Checking for zombie/dead processes: ", self.module, 3, 'checkForZombieProcesses', False)

        #check for zombie'd and dead processes
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

        #check if there zombie processes
        if len(zombie_processes) == 0:
            self.utility.logger("There are NO zombie processes on this node!", self.module, 1, 'process_zombies')
        else:
            self.utility.logger("We DETECTED zombie processes on this node: {0}".format(', '.join(zombie_processes)), self.module, 2, 'process_zombies')

        #check if there dead processes
        if len(dead_processes) == 0:
            self.utility.logger("There are NO dead processes on this node!", self.module, 1, 'process_dead')
        else:
            self.utility.logger("We DETECTED dead processes on this node: {0}".format(', '.join(dead_processes)), self.module, 0, 'process_dead')

    def _checkFiledriver(self, args1, vp_name, test_name):
        # this method is not meant to be executed in serial, it is meant to be executed in parallel as a thread
        filedriver = self.utility.executeBashCommand("touch /mnt/{0}/{1}.xml".format(vp_name, test_name))
        return filedriver

    def _checkVolumedriver(self, args1, vp_name, test_name):
        # this method is not meant to be executed in serial, it is meant to be executed in parallel as a thread
        volumedriver = subprocess.check_output("truncate -s 10GB /mnt/{0}/{1}.raw".format(vp_name, test_name), stderr=subprocess.STDOUT, shell=True)
        return volumedriver

    def checkFileDriver(self):
        filedriversNotWorking = []
        name = "ovs-healthcheck-test"

        self.utility.logger("Checking filedrivers: ", self.module, 3, 'checkFileDrivers', False)

        # perform tests
        for vp in VPoolList.get_vpools():

            # check filedriver
            t = threading.Thread(target=self._checkFiledriver, args=(1, vp.name, name))
            t.daemon = True
            t.start()

            time.sleep(5)

            # if thread is still alive after x seconds, something is wrong
            if t.isAlive():
                filedriversNotWorking.append(vp.name)

            # clean-up
            if len(filedriversNotWorking) == 0:
                self.utility.executeBashCommand("rm -f /mnt/{0}/{1}.xml".format(vp.name, name))

        # check if filedrivers are OK!
        if len(filedriversNotWorking) == 0:
            self.utility.logger("All filedrivers seem to be working fine!", self.module, 1, 'filedrivers')
        else:
            self.utility.logger("Some filedrivers seem to have some problems: {0}".format(', '.join(filedriversNotWorking)), self.module, 0, 'filedrivers')

    def checkVolumeDriver(self):
        volumedriversNotWorking = []
        name = "ovs-healthcheck-test"

        self.utility.logger("Checking volumedrivers: ", self.module, 3, 'checkVolumeDrivers', False)

        # perform tests
        for vp in VPoolList.get_vpools():

            # check volumedrivers
            t = threading.Thread(target=self._checkVolumedriver, args=(1, vp.name, name))
            t.daemon = True
            t.start()

            time.sleep(5)

            # if thread is still alive after x seconds, something is wrong
            if t.isAlive():
                volumedriversNotWorking.append(vp.name)

            # clean-up
            if len(volumedriversNotWorking) == 0:
                self.utility.executeBashCommand("rm -f /mnt/{0}/{1}.raw".format(vp.name, name))

        # check if filedrivers are OK!
        if len(volumedriversNotWorking) == 0:
            self.utility.logger("All volumedrivers seem to be working fine!", self.module, 1, 'volumedrivers')
        else:
            self.utility.logger("Some volumedrivers seem to have some problems: {0}"
                                .format(', '.join(volumedriversNotWorking)), self.module, 0, 'volumedrivers')

    def checkModelConsistency(self):

        self.utility.logger("Checking model consistency: ", self.module, 3, 'checkModelConsistency', False)

        #
        # RabbitMQ check: cluster verification
        #

        self.utility.logger("Precheck: verification of RabbitMQ cluster: ", self.module, 3, 'checkRabbitMQcluster', False)

        cluster_status = self.utility.executeBashCommand("rabbitmqctl cluster_status")

        if "Error" not in cluster_status[1]:
            partition_status = cluster_status[3]
            if '@' in partition_status:
                self.utility.logger("Seems like the RabbitMQ cluster has 'partition' problems, please check this...", self.module, 0, 'process_rabbitmq', False)
            else:
                self.utility.logger("RabbitMQ does not seem to have 'partition' problems :D", self.module, 1, 'process_rabbitmq', False)
        else:
            self.utility.logger("Seems like the RabbitMQ cluster has errors, maybe it is offline?", self.module, 0, 'process_rabbitmq', False)

        #
        # Checking consistency of volumedriver vs. ovsdb and backwards
        #

        for vp in VPoolList.get_vpools():

            self.utility.logger("Checking consistency of volumedriver vs. ovsdb for vPool '{0}': ".format(vp.name), self.module, 3, 'checkDiscrepanciesVoldrvOvsdb', False)

            # list of vdisks that are in model but are not in volumedriver
            missingInVolumedriver = []

            # list of volumes that are in volumedriver but are not in model
            missingInModel = []

            # fetch configfile of vpool for the volumedriver
            config_file = self.utility.fetchConfigFilePath(vp.name+self.machine_id, 1, vp.guid)
            voldrv_client = src.LocalStorageRouterClient(config_file)

            # collect data from volumedriver
            voldrv_volume_list = voldrv_client.list_volumes()

            # collect data from model
            model_vdisk_list = vp.vdisks

            # crossreference model vs. volumedriver
            for vdisk in model_vdisk_list:
                if not vdisk.volume_id in voldrv_volume_list:
                    missingInVolumedriver.append(vdisk.volume_id)

            # crossreference volumedriver vs. model
            # (This can be a performance bottleneck on heavy env. due to nested for loops)
            for volume in voldrv_volume_list:
                for vdisk in model_vdisk_list:
                    if str(volume) != vdisk.volume_id and len(model_vdisk_list) == (model_vdisk_list.index(vdisk)+1):
                        missingInModel.append(volume)

            # display discrepancies for vPool
            if len(missingInVolumedriver) != 0:
                self.utility.logger("Detected volumes that are MISSING in volumedriver but ARE in ovsdb in vPool "
                                    "'{0}': {1}".format(vp.name, ', '.join(missingInVolumedriver)), self.module, 0,
                                    'discrepancies_ovsdb_{0}'.format(vp.name))
            else:
                self.utility.logger("NO discrepancies found for ovsdb in vPool '{0}'".format(vp.name), self.module, 1,
                                    'discrepancies_ovsdb_{0}'.format(vp.name))

            if len(missingInModel) != 0:
                self.utility.logger("Detected volumes that are AVAILABLE in volumedriver but ARE NOT in ovsdb in vPool "
                                    "'{0}': {1}".format(vp.name, ', '.join(missingInModel)), self.module, 0,
                                    'discrepancies_voldrv_{0}'.format(vp.name))
            else:
                self.utility.logger("NO discrepancies found for voldrv in vPool '{0}'".format(vp.name), self.module, 1,
                                    'discrepancies_voldrv_{0}'.format(vp.name))

    def checkForHaltedVolumes(self):

        self.utility.logger("Checking for halted volumes: ", self.module, 3, 'checkHaltedVolumes', False)

        for vp in VPoolList.get_vpools():

            haltedVolumes = []

            self.utility.logger("Checking vPool {0}: ".format(vp.name), self.module, 3,
                                'checkVPOOL_{0}'.format(vp.name), False)

            config_file = self.utility.fetchConfigFilePath(vp.name+self.machine_id, 1, vp.guid)
            voldrv_client = src.LocalStorageRouterClient(config_file)

            for volume in voldrv_client.list_volumes():
                # check if volume is halted, returns: 0 or 1
                if int(self.utility.parseXMLtoJSON(voldrv_client.info_volume(volume))
                           ["boost_serialization"]["XMLRPCVolumeInfo"]["halted"]):
                    haltedVolumes.append(volume)

            # print all results
            if len(haltedVolumes) > 0:
                self.utility.logger("Detected volumes that are HALTED in volumedriver in vPool '{0}': {1}"
                                    .format(vp.name, ', '.join(haltedVolumes)), self.module, 0,
                                    'halted_{0}'.format(vp.name))
            else:
                self.utility.logger("No halted volumes detected in vPool '{0}'"
                                    .format(vp.name), self.module, 1,
                                    'halted_{0}'.format(vp.name))

"""
Section: Main
"""
