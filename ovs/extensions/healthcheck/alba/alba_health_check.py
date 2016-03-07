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
Alba Health Check Module
"""

import subprocess
import hashlib
import time
import uuid
import json
import os

from ovs.extensions.healthcheck.utils.extension import Utils
from ovs.dal.lists.albabackendlist import AlbaBackendList
from ovs.log.healthcheck_logHandler import HCLogHandler
from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.dal.lists.servicelist import ServiceList
from ovs.extensions.generic.system import System


class AlbaHealthCheck:
    """
    A healthcheck for Alba storage layer
    """

    def __init__(self, logging=HCLogHandler(False)):
        """
        Init method for Alba health check module

        @param logging: ovs.log.healthcheck_logHandler

        @type logging: Class
        """

        self.module = "alba"
        self.utility = Utils()
        self.LOGGER = logging
        self.show_disks_in_monitoring = False
        self.machine_details = System.get_my_storagerouter()
        self.machine_id = System.get_my_machine_id()
        self.temp_file_loc = "/tmp/ovs-hc.xml"  # to be put in alba file
        self.temp_file_fetched_loc = "/tmp/ovs-hc-fetched.xml"  # fetched (from alba) file location
        self.temp_file_size = 1048576  # bytes

    def _fetchAvailableAlbaBackends(self):
        """
        Fetches the available alba backends

        @return: information about each alba backend

        @rtype: list that consists of dicts
        """

        result = []
        for abl in AlbaBackendList.get_albabackends():

            # check if backend would be available for vpool
            for preset in abl.presets:
                available = False
                if preset.get('is_available'):
                    available = True
                elif len(abl.presets) == abl.presets.index(preset) + 1:
                    available = False

            # collect asd's connected to a backend
            disks = []
            for asd in abl.all_disks:
                if abl.guid == asd.get('alba_backend_guid'):
                    disks.append(asd)

            # create result
            result.append({
                    'name': abl.name,
                    'alba_id': abl.alba_id,
                    'is_available_for_vpool': available,
                    'guid': abl.guid,
                    'backend_guid': abl.backend_guid,
                    'all_disks': disks
                })

        return result

    def _checkIfProxyWorks(self):
        """
        Checks if all Alba Proxies work on a local machine, it creates a namespace and tries to put and object
        """

        amount_of_presets_not_working = []

        self.LOGGER.logger("Checking seperate proxies to see if they work ...",self.module, 3, 'checkAlba', False)

        # ignore possible subprocess output
        FNULL = open(os.devnull, 'w')

        # try put/get/verify on all available proxies on the local node
        for sr in ServiceList.get_services():
            if sr.storagerouter_guid == self.machine_details.guid:
                if 'albaproxy_' in sr.name:
                    # determine what to what backend the proxy is connected
                    abm_name = subprocess.check_output(['alba', 'proxy-client-cfg', '-h', '127.0.0.1', '-p',
                                                        str(sr.ports[0])]).split()[3]
                    abm_config = self.utility.fetchConfigFilePath(abm_name, self.machine_id, 0)

                    # determine presets / backend
                    presets_results = subprocess.Popen(['alba', 'list-presets', '--config', abm_config, '--to-json'],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    presets = json.loads(presets_results.communicate()[0])

                    for preset in presets['result']:
                        # based on preset, always put in same namespace
                        namespace_key = 'ovs-healthcheck-ns-{0}'.format(preset.get('name'))
                        object_key = 'ovs-healthcheck-obj-{0}'.format(str(uuid.uuid4()))

                        # try put namespace
                        subprocess.call(['alba', 'proxy-create-namespace', '-h', '127.0.0.1', '-p', str(sr.ports[0]),
                                        str(namespace_key), str(preset.get('name'))], stdout=FNULL,
                                        stderr=subprocess.STDOUT)

                        # try get namespace
                        get_nam_results = subprocess.Popen(['alba', 'show-namespace', str(namespace_key),'--config',
                                                    str(abm_config), '--to-json'], stdout=subprocess.PIPE,
                                                    stderr=subprocess.PIPE)
                        get_nam = get_nam_results.communicate()[0]

                        try:
                            # try to convert it to json, because of OVS-4135
                            json_nam = json.loads(get_nam)

                            # check if put/get_namespace was successfully executed
                            if json_nam['success']:

                                # get & put is successfully executed
                                self.LOGGER.logger("Namespace successfully created or already existed "
                                                    "via proxy '{0}' ""with preset '{1}'!".format(sr.name,
                                                                                                  preset.get('name')),
                                                    self.module, 1, '{0}_preset_{1}_create_namespace'
                                                    .format(sr.name, preset.get('name')))

                                # put test object to given dir
                                with open(self.temp_file_loc, 'wb') as fout:
                                    fout.write(os.urandom(self.temp_file_size))

                                # try to put object
                                subprocess.call(['alba', 'proxy-upload-object', '-h', '127.0.0.1', '-p',
                                                 str(sr.ports[0]), str(namespace_key), str(self.temp_file_loc),
                                                 str(object_key)], stdout=FNULL, stderr=subprocess.STDOUT)

                                # download object
                                subprocess.call(['alba', 'download-object', str(namespace_key), str(object_key),
                                                str(self.temp_file_fetched_loc), '--config', str(abm_config)],
                                                stdout=FNULL, stderr=subprocess.STDOUT)

                                # check if file exists (if not then location does not exists)
                                if os.path.isfile(self.temp_file_fetched_loc):
                                    hash_original = hashlib.md5(open(self.temp_file_loc, 'rb')
                                                                .read()).hexdigest()
                                    hash_fetched = hashlib.md5(open(self.temp_file_fetched_loc, 'rb')
                                                               .read()).hexdigest()

                                    if hash_original == hash_fetched:
                                        self.LOGGER.logger("Creation of a object in namespace '{0}' on proxy '{1}' "
                                                            "with"" preset '{2}' succeeded!".format(namespace_key,
                                                                                                    sr.name,
                                                                                                    preset.get('name')),
                                                            self.module, 1, '{0}_preset_{1}_create_object'
                                                            .format(sr.name, preset.get('name')))
                                    else:
                                        self.LOGGER.logger("Creation of a object '{0}' in namespace '{1}' on proxy"
                                                            " '{2}' with preset '{3}' failed!".format(object_key,
                                                                                                      namespace_key,
                                                                                                      sr.name,
                                                                                                      preset.get('name')
                                                                                                      ),
                                                            self.module, 0, '{0}_preset_{1}_create_object'
                                                            .format(sr.name, preset.get('name')))

                                else:
                                    # creation of object failed
                                    raise ValueError

                            else:
                                # creation of namespace failed
                                raise ValueError

                        except ValueError:
                            amount_of_presets_not_working.append(preset.get('name'))

                            if 'not found' in get_nam:
                                # put was not successfully executed, so get return success = False
                                self.LOGGER.logger("Creating/fetching namespace '{0}' with preset '{1}' on proxy '{2}'"
                                                    " failed! ".format(namespace_key, preset.get('name'), sr.name),
                                                    self.module, 0, '{0}_preset_{1}_create_namespace'
                                                    .format(sr.name, preset.get('name')))

                                # for unattended install
                                self.LOGGER.logger("Failed to put object because namespace failed to be"
                                                    " created/fetched on proxy '{0}'! ".format(sr.name), self.module,
                                                    0, '{0}_preset_{1}_create_object'.format(sr.name, preset.get('name')))
                            else:
                                # for unattended install
                                self.LOGGER.logger("Failed to put object on namespace '{0}' failed on proxy"
                                                    " '{0}'! ".format(sr.name), self.module, 0,
                                                    '{0}_preset_{1}_create_object'.format(sr.name, preset.get('name')))

                        except Exception as e:
                            amount_of_presets_not_working.append(preset.get('name'))

                            self.LOGGER.logger("Something unexpected went wrong during the check of the alba"
                                                " proxies: {0}".format(e), self.module, 4,
                                                '{0}_preset_{1}_create_object'.format(sr.name, preset.get('name')))

                        # clean-up procedure for created object(s) & temp. files
                        subprocess.call(['alba', 'delete-object', '--config', str(abm_config),
                                        str(namespace_key), str(object_key)],
                                        stdout=FNULL, stderr=subprocess.STDOUT)
                        subprocess.call(['rm', str(self.temp_file_loc)])
                        subprocess.call(['rm', str(self.temp_file_fetched_loc)])

        # for unattended
        return amount_of_presets_not_working

    def _checkIfBackendASDSWorks(self, disks):
        """
        Checks if Alba ASD's work

        @param disks: list of alba ASD's

        @type disks: list

        @return: returns a tuple that consists of lists: (workingDisks, defectiveDisks)

        @rtype: tuple that consists of lists
        """

        workingDisks = []
        defectiveDisks = []

        self.LOGGER.logger("Checking seperate ASD's to see if they work ...",self.module, 3, 'checkAsds', False)

        # check if disks are working
        if len(disks) != 0:
            for disk in disks:
                key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
                value = str(time.time())
                ip_address = AlbaNodeList.get_albanode_by_node_id(disk.get('node_id')).ip

                try:
                    # check if disk is missing
                    if disk.get('port') != None:
                        # put object but ignore crap for a moment
                        FNULL = open(os.devnull, 'w')
                        subprocess.call(['alba', 'asd-set', '--long-id', disk.get('asd_id'), '-p', str(disk.get('port')), '-h', ip_address, key, value], stdout=FNULL, stderr=subprocess.STDOUT)

                        # get object
                        g = subprocess.check_output(['alba', 'asd-multi-get', '--long-id', disk.get('asd_id'), '-p', str(disk.get('port')), '-h', ip_address, key])

                        # check if put/get is successfull
                        if 'None' in g:
                            # test failed!
                            raise Exception(g)
                        else:
                            # test successfull!
                            self.LOGGER.logger("ASD test with DISK_ID '{0}' succeeded!".format(disk.get('asd_id')),
                                                self.module, 1, 'alba_asd_{0}'.format(disk.get('asd_id')),
                                                self.show_disks_in_monitoring)

                            workingDisks.append(disk.get('asd_id'))

                        # delete object
                        subprocess.check_output(['alba', 'asd-delete', '--long-id', disk.get('asd_id'), '-p',
                                                 str(disk.get('port')), '-h', ip_address, key])
                    else:
                        # disk is missing
                        raise Exception

                except Exception as e:
                    defectiveDisks.append(disk.get('asd_id'))
                    self.LOGGER.logger("ASD test with DISK_ID '{0}' failed on NODE '{1}' ..."
                                        .format(disk.get('asd_id'), ip_address), self.module, 0,
                                        'alba_asd_{0}'.format(disk.get('asd_id')), self.show_disks_in_monitoring)

        return workingDisks, defectiveDisks

    def checkAlba(self):
        """
        Checks Alba as a whole
        """

        self.LOGGER.logger("Fetching all Available ALBA backends ...", self.module, 3, 'checkAlba', False)
        try:
            alba_backends = self._fetchAvailableAlbaBackends()

            if len(alba_backends) != 0:
                self.LOGGER.logger("We found {0} backend(s)!".format(len(alba_backends)),self.module, 1,
                                    'alba_backends_found'.format(len(alba_backends)))
                for backend in alba_backends:

                    # check proxies, and recap for unattended
                    result_proxies = self._checkIfProxyWorks()
                    if len(result_proxies) == 0:
                        # all proxies work
                        self.LOGGER.logger("All Alba proxies should be fine!", self.module, 1, 'alba_proxy')
                    else:
                        # not all proxies work
                        self.LOGGER.logger("Some alba proxies are NOT working: {0}".format(', '.join(result_proxies)),
                                            self.module, 0, 'alba_proxy')

                    # check disks
                    result_disks = self._checkIfBackendASDSWorks(backend.get('all_disks'))
                    workingDisks = result_disks[0]
                    defectiveDisks = result_disks[1]

                    # check if backend is available for vPOOL attachment / use
                    if backend.get('is_available_for_vpool'):
                        if len(defectiveDisks) == 0:
                            self.LOGGER.logger("Alba backend '{0}' should be AVAILABLE FOR vPOOL USE,"
                                                " ALL disks are working fine!".format(backend.get('name')),
                                                self.module, 1, 'alba_backend_{0}'.format(backend.get('name')))
                        else:
                            self.LOGGER.logger("Alba backend '{0}' should be AVAILABLE FOR vPOOL USE with {1} disks,"
                                                " BUT there are {2} defective disks: {3}".format(backend.get('name'),
                                                                                                 len(workingDisks),
                                                                                                 len(defectiveDisks),
                                                                                                 ', '.join(defectiveDisks)),
                                                self.module, 2, 'alba_backend_{0}'.format(backend.get('name'),
                                                                                          len(defectiveDisks)))
                    else:
                        if len(workingDisks) == 0 and len(defectiveDisks) == 0:
                            self.LOGGER.logger("Alba backend '{0}' is NOT available for vPool use, there are no"
                                                " disks assigned to this backend!".format(backend.get('name')),
                                                self.module, 5, 'alba_backend_{0}'.format(backend.get('name')))
                        else:
                            self.LOGGER.logger("Alba backend '{0}' is NOT available for vPool use, preset"
                                                " requirements NOT SATISFIED! There are {1} working disks AND {2}"
                                                " defective disks!".format(backend.get('name'), len(workingDisks),
                                                                           len(defectiveDisks)), self.module, 0,
                                                'alba_backend_{0}'.format(backend.get('name')))

            else:
                self.LOGGER.logger("No backends found ...",self.module, 5, 'alba_backends_found')
            return None
        except Exception as e:
            self.LOGGER.logger("One ore more Arakoon clusters cannot be reached due to error: {0}".format(e),
                                self.module, 0, 'arakoon_connected', False)