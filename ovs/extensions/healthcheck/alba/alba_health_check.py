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
Alba Health Check Module
"""

import os
import json
import uuid
import time
import hashlib
import subprocess
from ovs.extensions.generic.system import System
from ovs.dal.lists.servicelist import ServiceList
from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.log.healthcheck_logHandler import HCLogHandler
from ovs.dal.lists.albabackendlist import AlbaBackendList
from ovs.extensions.healthcheck.utils.extension import Utils
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from etcd import EtcdConnectionFailed, EtcdKeyNotFound, EtcdException
from ovs.extensions.healthcheck.utils.exceptions import ObjectNotFoundException, CommandException
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult


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

    @staticmethod
    def _fetch_available_backends():
        """
        Fetches the available alba backends

        @return: information about each alba backend

        @rtype: list that consists of dicts
        """

        result = []
        for abl in AlbaBackendList.get_albabackends():

            # check if backend would be available for vpool
            available = False
            for preset in abl.presets:
                available = False
                if preset.get('is_available'):
                    available = True
                elif len(abl.presets) == abl.presets.index(preset) + 1:
                    available = False

            # collect asd's connected to a backend
            disks = []
            for stack in abl.local_stack.values():
                for osds in stack.values():
                    node_id = osds.get('node_id')
                    for asd in osds.get('asds').values():
                        if abl.guid == asd.get('alba_backend_guid'):
                            asd['node_id'] = node_id
                            asd_id = asd.get('asd_id')
                            try:
                                asd['port'] = EtcdConfiguration.get('/ovs/alba/asds/{0}/config|port'
                                                                    .format(asd_id))
                                disks.append(asd)
                            except (EtcdConnectionFailed, EtcdException, EtcdKeyNotFound) as ex:
                                raise EtcdConnectionFailed(ex)
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

    def _check_if_proxies_work(self):
        """
        Checks if all Alba Proxies work on a local machine, it creates a namespace and tries to put and object
        """
        amount_of_presets_not_working = []
        ip = self.machine_details.ip

        # ignore possible subprocess output
        fnull = open(os.devnull, 'w')

        # try put/get/verify on all available proxies on the local node
        for sr in ServiceList.get_services():
            if sr.storagerouter_guid == self.machine_details.guid:
                if 'albaproxy_' in sr.name:
                    self.LOGGER.info("Checking ALBA proxy '{0}': ".format(sr.name), 'check_alba', False)
                    try:
                        # determine what to what backend the proxy is connected
                        with open(os.devnull, 'w') as devnull:
                            abm_name = subprocess.check_output(['alba', 'proxy-client-cfg', '-h', ip, '-p', str(sr.ports[0])], stderr=devnull).split()[3]

                        abm_config = self.utility.get_config_file_path(abm_name, self.machine_id, 0)

                        # determine presets / backend
                        presets_results = subprocess.Popen(['alba', 'list-presets', '--config', abm_config,
                                                            '--to-json'], stdout=subprocess.PIPE,
                                                           stderr=subprocess.PIPE)
                        presets = json.loads(presets_results.communicate()[0])

                        for preset in presets['result']:
                            # based on preset, always put in same namespace
                            namespace_key = 'ovs-healthcheck-ns-{0}'.format(preset.get('name'))
                            object_key = 'ovs-healthcheck-obj-{0}'.format(str(uuid.uuid4()))

                            # try put namespace
                            subprocess.call(['alba', 'proxy-create-namespace', '-h', ip, '-p', str(sr.ports[0]),
                                            str(namespace_key), str(preset.get('name'))], stdout=fnull,
                                            stderr=subprocess.STDOUT)

                            # try get namespace
                            get_nam_results = subprocess.Popen(['alba', 'show-namespace', str(namespace_key), '--config',
                                                                str(abm_config), '--to-json'], stdout=subprocess.PIPE,
                                                               stderr=subprocess.PIPE)
                            get_nam = get_nam_results.communicate()[0]

                            try:
                                # try to convert it to json, because of OVS-4135
                                json_nam = json.loads(get_nam)

                                # check if put/get_namespace was successfully executed
                                if json_nam['success']:

                                    # get & put is successfully executed
                                    self.LOGGER.success("Namespace successfully created or already existed "
                                                        "via proxy '{0}' with preset '{1}'!".format(sr.name,
                                                                                                    preset.get('name')),
                                                        '{0}_preset_{1}_create_namespace'
                                                        .format(sr.name, preset.get('name')))

                                    # put test object to given dir
                                    with open(self.temp_file_loc, 'wb') as fout:
                                        fout.write(os.urandom(self.temp_file_size))

                                    # try to put object
                                    subprocess.call(['alba', 'proxy-upload-object', '-h', ip, '-p',
                                                     str(sr.ports[0]), str(namespace_key), str(self.temp_file_loc),
                                                     str(object_key)], stdout=fnull, stderr=subprocess.STDOUT)

                                    # download object
                                    subprocess.call(['alba', 'download-object', str(namespace_key), str(object_key),
                                                    str(self.temp_file_fetched_loc), '--config', str(abm_config)],
                                                    stdout=fnull, stderr=subprocess.STDOUT)

                                    # check if file exists (if not then location does not exists)
                                    if os.path.isfile(self.temp_file_fetched_loc):
                                        hash_original = hashlib.md5(open(self.temp_file_loc, 'rb')
                                                                    .read()).hexdigest()
                                        hash_fetched = hashlib.md5(open(self.temp_file_fetched_loc, 'rb')
                                                                   .read()).hexdigest()

                                        if hash_original == hash_fetched:
                                            self.LOGGER.success("Creation of a object in namespace '{0}' on proxy '{1}' "
                                                                "with preset '{2}' succeeded!".format(namespace_key,
                                                                                                      sr.name,
                                                                                                      preset.get('name')),
                                                                '{0}_preset_{1}_create_object'
                                                                .format(sr.name, preset.get('name')))
                                        else:
                                            self.LOGGER.failure("Creation of a object '{0}' in namespace '{1}' on proxy"
                                                                " '{2}' with preset '{3}' failed!".format(object_key,
                                                                                                          namespace_key,
                                                                                                          sr.name,
                                                                                                          preset.get('name')
                                                                                                          ),
                                                                '{0}_preset_{1}_create_object'
                                                                .format(sr.name, preset.get('name')))
                                    else:
                                        # creation of object failed
                                        raise ObjectNotFoundException(ValueError)
                                else:
                                    # creation of namespace failed
                                    raise ObjectNotFoundException(ValueError)
                            except ObjectNotFoundException:
                                amount_of_presets_not_working.append(preset.get('name'))

                                if 'not found' in get_nam:
                                    # put was not successfully executed, so get return success = False
                                    self.LOGGER.failure("Creating/fetching namespace "
                                                        "'{0}' with preset '{1}' on proxy '{2}'"
                                                        " failed! ".format(namespace_key, preset.get('name'), sr.name),
                                                        '{0}_preset_{1}_create_namespace'
                                                        .format(sr.name, preset.get('name')))

                                    # for unattended install
                                    self.LOGGER.failure("Failed to put object because namespace failed to be "
                                                        "created/fetched on proxy '{0}'! ".format(sr.name),
                                                        '{0}_preset_{1}_create_object'
                                                        .format(sr.name, preset.get('name')))
                                else:
                                    # for unattended install
                                    self.LOGGER.failure("Failed to put object on namespace '{0}' failed on proxy"
                                                        "'{0}'! ".format(sr.name), '{0}_preset_{1}_create_object'
                                                        .format(sr.name, preset.get('name')))

                            # clean-up procedure for created object(s) & temp. files
                            subprocess.call(['alba', 'delete-object', '--config', str(abm_config),
                                            str(namespace_key), str(object_key)],
                                            stdout=fnull, stderr=subprocess.STDOUT)
                            subprocess.call(['rm', str(self.temp_file_loc)])
                            subprocess.call(['rm', str(self.temp_file_fetched_loc)])
                    except subprocess.CalledProcessError as e:
                        self.LOGGER.failure("Proxy '{0}' has some problems: {1}"
                                            .format(sr.name, e), 'proxy_{0}'.format(sr.name))

        # for unattended
        return amount_of_presets_not_working

    def _check_backend_asds(self, disks, backend_name):
        """
        Checks if Alba ASD's work

        @param disks: list of alba ASD's

        @type disks: list

        @return: returns a tuple that consists of lists: (workingdisks, defectivedisks)

        @rtype: tuple that consists of lists
        """

        workingdisks = []
        defectivedisks = []

        self.LOGGER.info("Checking seperate ASD's for backend '{0}':".format(backend_name), 'check_asds', False)

        # check if disks are working
        if len(disks) != 0:
            for disk in disks:
                key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
                value = str(time.time())
                ip_address = AlbaNodeList.get_albanode_by_node_id(disk.get('node_id')).ip

                try:
                    # check if disk is missing
                    if disk.get('port'):
                        # put object but ignore crap for a moment
                        fnull = open(os.devnull, 'w')
                        subprocess.call(['alba', 'asd-set', '--long-id', disk.get('asd_id'), '-p',
                                         str(disk.get('port')), '-h', ip_address, key, value], stdout=fnull,
                                        stderr=subprocess.STDOUT)

                        # get object
                        try:
                            g = subprocess.check_output(['alba', 'asd-multi-get', '--long-id', disk.get('asd_id'), '-p',
                                                        str(disk.get('port')), '-h', ip_address, key])
                        except Exception:
                            raise CommandException(Exception('Connection failed to disk ...'))

                        # check if put/get is successfull
                        if 'None' in g:
                            # test failed!
                            raise ObjectNotFoundException(Exception(g))
                        else:
                            # test successfull!
                            self.LOGGER.success("ASD test with DISK_ID '{0}' succeeded!".format(disk.get('asd_id')),
                                                'alba_asd_{0}'.format(disk.get('asd_id')),
                                                self.show_disks_in_monitoring)

                            workingdisks.append(disk.get('asd_id'))

                        # delete object
                        subprocess.check_output(['alba', 'asd-delete', '--long-id', disk.get('asd_id'), '-p',
                                                 str(disk.get('port')), '-h', ip_address, key])
                    else:
                        # disk is missing
                        raise ObjectNotFoundException(Exception('Disk is missing'))

                except ObjectNotFoundException as e:
                    defectivedisks.append(disk.get('asd_id'))
                    self.LOGGER.failure("ASD test with DISK_ID '{0}' failed on NODE '{1}' with exception: {2}"
                                        .format(disk.get('asd_id'), ip_address, e),
                                        'alba_asd_{0}'.format(disk.get('asd_id')), self.show_disks_in_monitoring)

        return workingdisks, defectivedisks

    def check_alba(self):
        """
        Checks Alba as a whole
        """

        self.LOGGER.info("Checking available ALBA backends ...", 'check_alba', False)
        try:
            alba_backends = self._fetch_available_backends()

            if len(alba_backends) != 0:
                self.LOGGER.success("We found {0} backend(s)!".format(len(alba_backends)),
                                    'alba_backends_found'.format(len(alba_backends)))
                for backend in alba_backends:

                    # check proxies, and recap for unattended
                    result_proxies = self._check_if_proxies_work()
                    if len(result_proxies) == 0:
                        # all proxies work
                        self.LOGGER.success("All Alba proxies should be fine!", 'alba_proxy')
                    else:
                        # not all proxies work
                        self.LOGGER.failure("Some alba proxies are NOT working: {0}".format(', '.join(result_proxies)),
                                            'alba_proxy')

                    # check disks
                    result_disks = self._check_backend_asds(backend.get('all_disks'), backend.get('name'))
                    workingdisks = result_disks[0]
                    defectivedisks = result_disks[1]

                    # check if backend is available for vPOOL attachment / use
                    if backend.get('is_available_for_vpool'):
                        if len(defectivedisks) == 0:
                            self.LOGGER.success("Alba backend '{0}' should be AVAILABLE FOR vPOOL USE,"
                                                " ALL disks are working fine!".format(backend.get('name')),
                                                'alba_backend_{0}'.format(backend.get('name')))
                        else:
                            self.LOGGER.warning("Alba backend '{0}' should be AVAILABLE FOR vPOOL USE with {1} disks,"
                                                " BUT there are {2} defective disks: {3}".format(backend.get('name'),
                                                                                                 len(workingdisks),
                                                                                                 len(defectivedisks),
                                                                                                 ', '.join(
                                                                                                     defectivedisks)),
                                                'alba_backend_{0}'.format(backend.get('name'), len(defectivedisks)))
                    else:
                        if len(workingdisks) == 0 and len(defectivedisks) == 0:
                            self.LOGGER.skip("Alba backend '{0}' is NOT available for vPool use, there are no"
                                             " disks assigned to this backend!".format(backend.get('name')),
                                             'alba_backend_{0}'.format(backend.get('name')))
                        else:
                            self.LOGGER.failure("Alba backend '{0}' is NOT available for vPool use, preset"
                                                " requirements NOT SATISFIED! There are {1} working disks AND {2}"
                                                " defective disks!".format(backend.get('name'), len(workingdisks),
                                                                           len(defectivedisks)),
                                                'alba_backend_{0}'.format(backend.get('name')))

            else:
                self.LOGGER.skip("No backends found ...", 'alba_backends_found')
        except (EtcdKeyNotFound, EtcdConnectionFailed, EtcdConnectionFailed) as e:
            self.LOGGER.failure("Failed to connect to ETCD: {0}".format(e), 'etcd_connection', False)
        except (ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult) as e:
            self.LOGGER.failure("Seems like a arakoon has some problems: {0}".format(e),
                                'arakoon_connected', False)