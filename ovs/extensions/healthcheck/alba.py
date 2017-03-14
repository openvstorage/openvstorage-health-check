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
import uuid
import time
import hashlib
import subprocess
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration, NotFoundException
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLIRunner
from ovs.extensions.healthcheck.helpers.albacli import AlbaCLI
from ovs.extensions.healthcheck.helpers.backend import BackendHelper
from ovs.extensions.healthcheck.decorators import cluster_check
from ovs.extensions.healthcheck.helpers.exceptions import AlbaException, ConfigNotMatchedException, ConnectionFailedException, DiskNotFoundException, ObjectNotFoundException
from ovs.extensions.healthcheck.helpers.network import NetworkHelper
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.services.service import ServiceManager
from ovs.lib.helpers.toolbox import Toolbox


class AlbaHealthCheck(object):
    """
    A healthcheck for Alba storage layer
    """
    MODULE = 'alba'
    TEMP_FILE_SIZE = 1024 ** 2
    LOCAL_SR = System.get_my_storagerouter()
    LOCAL_ID = System.get_my_machine_id()
    TEMP_FILE_LOC = '/tmp/ovs-hc.xml'  # to be put in alba file
    TEMP_FILE_FETCHED_LOC = '/tmp/ovs-hc-fetched.xml'  # fetched (from alba) file location
    NAMESPACE_TIMEOUT = 30  # in seconds

    @staticmethod
    def _check_backend_asds(result_handler, asds, backend_name, config):
        """
        Checks if Alba ASDs work
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param asds: list of alba ASDs
        :type asds: list[dict]
        :param backend_name: name of a existing backend
        :type backend_name: str
        :param config: path of the configuration file for the abm
        :type config: str
        :return: returns a dict that consists of lists with working disks and defective disks
        :rtype: dict
        """
        working_disks = []
        broken_disks = []
        result = {"working": working_disks, "broken": broken_disks}

        result_handler.info('Checking separate ASDs for backend {0}:'.format(backend_name), add_to_result=False)

        # check if asds are working
        if len(asds) == 0:
            return result
        # Map long id to ip
        osd_mapping = {}
        try:
            for osd in AlbaCLI.run(command='list-osds', config=config):
                if len(osd.get('ips')) > 0:
                    osd_mapping[osd.get('long_id')] = osd.get('ips')[0]
                    continue
                # @todo check with other ops for this logging
                result_handler.warning('The osd is not bound to any ip! Please validate your asd-manager install!')
        except AlbaException as ex:
            result_handler.failure('Could not fetch osd list from Alba. Got {0}'.format(str(ex)))
            raise
        for asd in asds:
            key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
            disk_asd_id = asd['asd_id']
            value = str(time.time())
            if asd['status'] == 'error':
                broken_disks.append(disk_asd_id)
                # @todo check with other ops for this logging. Perhaps filter on status_details
                result_handler.warning('ASD test with DISK_ID {0} failed because: {1}'.format(disk_asd_id, asd['status_detail']))
                continue
            # Fetch ip of the asd with list-asds
            ip_address = osd_mapping.get(disk_asd_id)
            try:
                # check if disk is missing
                if not asd.get('port'):
                    raise DiskNotFoundException('Disk is missing')
                # put object
                AlbaCLI.run(command='asd-set',
                            named_params={'host': ip_address, 'port': str(asd.get('port')),
                                          'long-id': disk_asd_id},
                            extra_params=[key, value])
                # get object
                fetched_object = AlbaCLI.run(command='asd-multi-get',
                                             named_params={'host': ip_address, 'port': str(asd.get('port')), 'long-id': disk_asd_id},
                                             extra_params=[key],
                                             to_json=False)
                # check if put/get is successful
                if 'None' in fetched_object:
                    # test failed!
                    raise ObjectNotFoundException(fetched_object)
                # test successful!
                result_handler.success('ASD test with DISK_ID {0} succeeded!'.format(disk_asd_id))
                working_disks.append(disk_asd_id)

                # delete object
                AlbaCLI.run(command='asd-delete',
                            named_params={'host': ip_address, 'port': str(asd.get('port')), 'long-id': disk_asd_id},
                            extra_params=[key])
            except ObjectNotFoundException:
                broken_disks.append(disk_asd_id)
                # @todo validate with other ops. #asds is important
                result_handler.warning('ASD test with disk-id {0} failed on node {1}!'.format(disk_asd_id, ip_address))
            except (AlbaException, DiskNotFoundException) as ex:
                # @todo validate with other ops. #asds is important
                broken_disks.append(disk_asd_id)
                result_handler.warning('ASD test with DISK_ID {0} failed  on node {1} with {2}'.format(disk_asd_id, ip_address, str(ex)))
        return result

    @staticmethod
    @expose_to_cli(MODULE, 'proxy-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_if_proxies_work(result_handler):
        """
        Checks if all Alba Proxies work on a local machine, it creates a namespace and tries to put and object
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        namespace_params = {'bucket_count': (list, None),
                            'logical': (int, None),
                            'storage': (int, None),
                            'storage_per_osd': (list, None)}

        result_handler.info('Checking the ALBA proxies.', add_to_result=False)

        amount_of_presets_not_working = []
        # ignore possible subprocess output
        fnull = open(os.devnull, 'w')
        # try put/get/verify on all available proxies on the local node
        local_proxies = ServiceHelper.get_local_proxy_services()
        if len(local_proxies) == 0:
            result_handler.info('Found no proxies.', add_to_result=False)
            return amount_of_presets_not_working
        for service in local_proxies:
            try:
                result_handler.info('Checking ALBA proxy {0}.'.format(service.name), add_to_result=False)
                ip = service.alba_proxy.storagedriver.storage_ip
                # Encapsulating try to determine test output
                try:
                    # Determine what to what backend the proxy is connected
                    proxy_client_cfg = AlbaCLI.run(command='proxy-client-cfg', named_params={'host': ip, 'port': service.ports[0]})
                except AlbaException:
                    result_handler.failure('Fetching proxy info has failed. Please verify if {0}:{1} is the correct address for the proxy.'.format(ip, service.ports[0]))
                    continue
                # Fetch arakoon information
                abm_name = proxy_client_cfg.get('cluster_id')
                # Check if proxy config is correctly setup
                if abm_name is None:
                    raise ConfigNotMatchedException('Proxy config does not have the correct format on node {0} with port {1}.'.format(ip, service.ports[0]))
                abm_config = Configuration.get_configuration_path('/ovs/arakoon/{0}-abm/config' .format(service.alba_proxy.storagedriver.vpool.metadata['backend']['backend_info']['name']))

                # Determine presets / backend
                try:
                    presets = AlbaCLI.run(command='list-presets', config=abm_config)
                except AlbaException:
                    result_handler.failure('Listing the presets has failed. Please check the arakoon config path. We used {0}'.format(abm_config))
                    continue

                for preset in presets:
                    # If preset is not in use, test will fail so add a skip
                    if preset['in_use'] is False:
                        result_handler.skip('Preset {0} is not in use and will not be checked'.format(preset['name']))
                        continue
                    preset_name = preset['name']
                    # Encapsulation try for cleanup
                    try:
                        # Generate new namespace name using the preset
                        namespace_key_prefix = 'ovs-healthcheck-ns-{0}-{1}'.format(preset_name, AlbaHealthCheck.LOCAL_ID)
                        namespace_key = '{0}_{1}'.format(namespace_key_prefix, uuid.uuid4())
                        object_key = 'ovs-healthcheck-obj-{0}'.format(str(uuid.uuid4()))
                        # Create namespace
                        AlbaCLI.run(command='proxy-create-namespace',
                                    named_params={'host': ip, 'port': service.ports[0]},
                                    extra_params=[namespace_key, preset_name])
                        # Wai until fully created
                        namespace_start_time = time.time()
                        for index in xrange(2):
                            # Running twice because the first one could give a false positive as the osds will alert the nsm
                            # and the nsm would respond with got messages but these were not the ones we are after
                            AlbaCLI.run(command='deliver-messages', config=abm_config)
                        while True:
                            if time.time() - namespace_start_time > AlbaHealthCheck.NAMESPACE_TIMEOUT:
                                raise RuntimeError('Creation namespace has timed out after {0}s'.format(time.time() - namespace_start_time))
                            output = AlbaCLI.run(command='list-ns-osds', config=abm_config, extra_params=[namespace_key], to_json=False)
                            # @todo https://github.com/openvstorage/alba/issues/634 -- replace with tojson instead of output processing
                            search = 'Albamgr_protocol.Protocol.Osd.NamespaceLink'
                            namespace_ready = True
                            for line in output.splitlines():
                                if line.strip():
                                    state = [i for i in line.split(' ') if search in i][0].split(')')[0].rsplit('.', 1)[1]
                                    if state == 'Adding':
                                        namespace_ready = False
                            if namespace_ready is True:
                                break
                        result_handler.success('Namespace successfully created on proxy {0} with preset {1}!'.format(service.name, preset_name))
                        namespace_info = AlbaCLI.run(command='show-namespace', config=abm_config, extra_params=[namespace_key])
                        Toolbox.verify_required_params(required_params=namespace_params, actual_params=namespace_info)
                        result_handler.success('Namespace successfully fetched on proxy {0} with preset {1}!'.format(service.name, preset_name))

                        # Put test object to given dir
                        with open(AlbaHealthCheck.TEMP_FILE_LOC, 'wb') as output_file:
                            output_file.write(os.urandom(AlbaHealthCheck.TEMP_FILE_SIZE))
                        AlbaCLI.run(command='proxy-upload-object',
                                    named_params={'host': ip, 'port': service.ports[0]},
                                    extra_params=[namespace_key, AlbaHealthCheck.TEMP_FILE_LOC, object_key])
                        result_handler.success('Successfully uploaded the object to namespace {0}'.format(namespace_key))
                        # download object
                        AlbaCLI.run(command='proxy-download-object',
                                    named_params={'host': ip, 'port': service.ports[0]},
                                    extra_params=[namespace_key, object_key, AlbaHealthCheck.TEMP_FILE_FETCHED_LOC])
                        result_handler.success('Successfully downloaded the object to namespace {0}'.format(namespace_key))
                        # check if files exists - issue #57
                        if not(os.path.isfile(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC) and os.path.isfile(AlbaHealthCheck.TEMP_FILE_LOC)):
                            # creation of object failed
                            raise ObjectNotFoundException(ValueError('Creation of object has failed'))
                        hash_original = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_LOC, 'rb').read()).hexdigest()
                        hash_fetched = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC, 'rb').read()).hexdigest()

                        if hash_original == hash_fetched:
                            result_handler.success('Fetched object {0} from namespace {1} on proxy {2} with preset {3} matches the created object!'.format(object_key, namespace_key, service.name, preset_name))
                        else:
                            result_handler.failure('Fetched object {0} from namespace {1} on proxy {2} with preset {3} does not match the created object!'.format(object_key, namespace_key, service.name, preset_name))

                    except ObjectNotFoundException as ex:
                        amount_of_presets_not_working.append(preset_name)
                        result_handler.failure('Failed to put object on namespace {0} failed on proxy {1}with preset {2} With error {3}'.format(namespace_key, service.name, preset_name, ex))
                    except AlbaException as ex:
                        if ex.alba_command == 'proxy-create-namespace':
                            result_handler.failure('Create namespace has failed with {0} on namespace {1} with proxy {2} with preset {3}'.format(str(ex), namespace_key, service.name, preset_name))
                        elif ex.alba_command == 'show-namespace':
                            result_handler.failure('Show namespace has failed with {0} on namespace {1} with proxy {2} with preset {3}'.format(str(ex), namespace_key, service.name, preset_name))
                        elif ex.alba_command == 'proxy-upload-object':
                            result_handler.failure('Uploading the object has failed with {0} on namespace {1} with proxy {2} with preset {3}'.format(str(ex), namespace_key, service.name, preset_name))
                        elif ex.alba_command == 'proxy-download-object':
                            result_handler.failure('Downloading the object has failed with {0} on namespace {1} with proxy {2} with preset {3}'.format(str(ex), namespace_key, service.name, preset_name))
                    finally:
                        # Delete the created namespace and preset
                        try:
                            subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_LOC)], stdout=fnull, stderr=subprocess.STDOUT)
                            subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC)], stdout=fnull, stderr=subprocess.STDOUT)
                            namespaces = AlbaCLI.run(command='list-namespaces', config=abm_config)
                            namespaces_to_remove = []
                            for namespace in namespaces:
                                if namespace['name'].startswith(namespace_key_prefix):
                                    namespaces_to_remove.append(namespace['name'])
                            for namespace_name in namespaces_to_remove:
                                if namespace_name == namespace_key:
                                    result_handler.info('Deleting namespace {0}.'.format(namespace_name))
                                else:
                                    result_handler.warning('Deleting namespace {0} which was leftover from a previous run.'.format(namespace_name))
                                AlbaCLI.run(command='proxy-delete-namespace', named_params={'host': ip, 'port': service.ports[0]}, extra_params=[namespace_name])
                                namespace_delete_start = time.time()
                                while True:
                                    try:
                                        AlbaCLI.run(command='show-namespace', config=abm_config, extra_params=[namespace_name])  # Will fail if the namespace does not exist
                                    except AlbaException:
                                        result_handler.success('Namespace {0} successfully removed.'.format(namespace_name))
                                        break
                                    if time.time() - namespace_delete_start > AlbaHealthCheck.NAMESPACE_TIMEOUT:
                                        raise RuntimeError('Delete namespace has timed out after {0}s'.format(time.time() - namespace_start_time))
                        except subprocess.CalledProcessError:
                            raise
                        except AlbaException:
                            raise
            except subprocess.CalledProcessError as ex:
                # this should stay for the deletion of the remaining files
                amount_of_presets_not_working.append(service.name)
                result_handler.failure('Proxy {0} has some problems. Got {1} as error'.format(service.name, ex))

            except ConfigNotMatchedException as ex:
                amount_of_presets_not_working.append(service.name)
                result_handler.failure('Proxy {0} has some problems. Got {1} as error'.format(service.name, ex))

    @staticmethod
    def _get_all_responding_backends(result_handler):
        """
        Fetches the responding alba backends. Logs when certain backends don't respond
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: information about each alba backend
        :rtype: list[dict]
        """
        result = []
        for alba_backend in BackendHelper.get_albabackends():
            # check if backend would be available for vpool
            try:
                available = False
                for preset in alba_backend.presets:
                    if preset.get('is_available'):
                        available = True

                # collect ASDs connected to a backend
                asds = []
                for stack in alba_backend.local_stack.values():
                    for osds in stack.values():
                        for asd in osds['asds'].values():
                            if alba_backend.guid != asd.get('alba_backend_guid'):
                                continue
                            asd_id = asd['asd_id']
                            arakoon_path = '/ovs/alba/asds/{0}/config|port'.format(asd_id)
                            try:
                                asd['port'] = Configuration.get(arakoon_path)
                            except NotFoundException as ex:
                                result_handler.failure('Could not find {0} in Arakoon. Got {1}'.format(arakoon_path, str(ex)))
                                raise
                            except Exception as ex:
                                result_handler.failure('Could not connect to the Arakoon due to an uncaught exception: {0}.'.format(str(ex)))
                                raise ConnectionFailedException(str(ex))
                            else:
                                asds.append(asd)
                # create result
                result.append({
                    'name': alba_backend.name,
                    'alba_id': alba_backend.alba_id,
                    'is_available_for_vpool': available,
                    'guid': alba_backend.guid,
                    'backend_guid': alba_backend.backend_guid,
                    'disks': asds,
                    'type': alba_backend.scaling
                })
            except RuntimeError as ex:
                result_handler.warning('Error occurred while unpacking alba backend {0}. Got {1}.'.format(alba_backend.name, str(ex)))
        return result

    @staticmethod
    @cluster_check
    @expose_to_cli(MODULE, 'backend-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_backends(result_handler):
        """
        Checks Alba as a whole
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking available ALBA backends.', add_to_result=False)
        try:
            alba_backends = AlbaHealthCheck._get_all_responding_backends(result_handler)
            if len(alba_backends) == 0:
                return result_handler.skip('No backends found.')

            result_handler.success('We found {0} backend(s)!'.format(len(alba_backends)))

            result_handler.info('Checking the ALBA ASDs.', add_to_result=False)
            for backend in alba_backends:
                backend_name = backend['name']
                # check disks of backend, ignore global backends
                if backend['type'] != 'LOCAL':
                    result_handler.skip('Alba backend {0} is a global backend.'.format(backend_name), add_to_result=False)
                    continue

                config = Configuration.get_configuration_path('/ovs/arakoon/{0}-abm/config'.format(backend_name))
                try:
                    result_disks = AlbaHealthCheck._check_backend_asds(result_handler, backend['disks'], backend_name, config)
                except Exception:
                    result_handler.warning('Could not fetch the asd information for alba backend {0}'.format(backend_name))
                    continue
                working_disks = result_disks['working']
                defective_disks = result_disks['broken']
                # check if backend is available for vPOOL attachment / use
                if backend['is_available_for_vpool']:
                    if len(defective_disks) == 0:
                        result_handler.success('Alba backend {0} should be available for VPool use. All asds are working fine!'.format(backend_name))
                    else:
                        result_handler.warning('Alba backend {0} should be available for VPool use with {1} asds, but there are {2} defective asds: {3}'
                                               .format(backend_name, len(working_disks), len(defective_disks), ', '.join(defective_disks)))
                else:
                    if len(working_disks) == 0 and len(defective_disks) == 0:
                        result_handler.skip('Alba backend {0} is not available for vPool use, there are no asds assigned to this backend!'.format(backend_name))
                    else:
                        result_handler.failure('Alba backend {0} is not available for vPool use, preset requirements not satisfied! There are {1} working asds AND {2} '
                                               'defective asds!'.format(backend_name, len(working_disks), len(defective_disks)))
        except NotFoundException as ex:
            result_handler.failure('Failed to fetch the object with exception: {0}'.format(ex))
        except ConnectionFailedException as ex:
            result_handler.failure('Failed to connect to configuration master with exception: {0}'.format(ex))
        except (ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult) as e:
            result_handler.failure('Seems like a arakoon has some problems: {0}'.format(e))

    @staticmethod
    @cluster_check
    @expose_to_cli(MODULE, 'disk-safety-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_disk_safety(result_handler):
        """
        Check safety of every namespace in every backend
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        results = AlbaHealthCheck.get_disk_safety(result_handler)
        for backend_name, policies in results.iteritems():
            result_handler.info('Checking disk safety on backend: {0}'.format(backend_name), add_to_result=False)
            for policy_prefix, policy_details in policies.iteritems():
                # '1,2' is policy_prefix and value is policy_details
                # {'1,2': {'max_disk_safety': 2, 'current_disk_safety': {<namespaces in safety buckets>} }
                result_handler.info('Checking policy {0} with max. disk safety {1}'.format(policy_prefix, policy_details['max_disk_safety']), add_to_result=False)
                if len(policy_details['current_disk_safety'].values()) == 0:
                    result_handler.skip('No data/namespaces found on backend {0}.'.format(backend_name))
                    continue
                # if there is only 1 bucket category that is equal to the max_disk_safety, all your data is safe
                if len(policy_details['current_disk_safety']) == 1 and policy_details['max_disk_safety'] in policy_details['current_disk_safety']:
                    # all data is safe!
                    result_handler.success('All data is safe on backend {0} with {1} namespace(s)'.format(backend_name, len(policy_details['current_disk_safety'][policy_details['max_disk_safety']])))
                else:
                    # some data is not or less safe!
                    for disk_safety, namespaces in policy_details['current_disk_safety'].iteritems():
                        if disk_safety == policy_details['max_disk_safety']:
                            result_handler.success('The disk safety of {0} namespace(s) is/are totally safe!'.format(len(namespaces)))
                        elif disk_safety != 0:
                            # avoid failure override
                            output = ',\n'.join(['{0} with {1}% of its objects'.format(ns['namespace'], str(ns['amount_in_bucket'])) for ns in namespaces])
                            result_handler.warning('The disk safety of {0} namespace(s) is {1}, max. disk safety is {2}: \n{3}'
                                                   .format(len(namespaces), disk_safety, policy_details['max_disk_safety'], output))
                        else:
                            # @TODO: after x amount of hours in disk safety 0 put in error, else put in warning
                            output = ',\n'.join(['{0} with {1}% of its objects'.format(ns['namespace'], str(ns['amount_in_bucket'])) for ns in namespaces])
                            result_handler.failure('The disk safety of {0} namespace(s) is/are ZERO: \n{1}'.format(len(namespaces), output))

    @staticmethod
    def get_disk_safety(result_handler):
        """
        Fetch safety of every namespace in every backend
        - amount_in_bucket is in %
        - max_disk_safety is the max. key that should be available in current_disk_safety
        Output example: {'mybackend02': {'1,2': {'max_disk_safety': 2, 'current_disk_safety':
        {2: {'namespace': u'b4eef27e-ef54-4fe8-8658-cdfbda7ceae4_000000065', 'amount_in_bucket': 100}}}}, 'mybackend':
        {'1,2': {'max_disk_safety': 2, 'current_disk_safety':
        {2: {'namespace': u'b4eef27e-ef54-4fe8-8658-cdfbda7ceae4_000000065', 'amount_in_bucket': 100}}}},
        'mybackend-global': {'1,2': {'max_disk_safety': 2, 'current_disk_safety':
        {1: {'namespace': u'e88c88c9-632c-4975-b39f-e9993e352560', 'amount_in_bucket': 100}}}}}
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: Safety of every namespace in every backend
        :rtype: dict
        """
        disk_safety_overview = {}
        for alba_backend in BackendHelper.get_albabackends():
            disk_safety_overview[alba_backend.name] = {}
            config = Configuration.get_configuration_path('ovs/arakoon/{0}-abm/config'.format(alba_backend.name))
            # Fetch alba info
            try:
                # @TODO add this to extra_params to include corrupt asds. Currently there is a bug with it
                # Ticket: https://github.com/openvstorage/alba/issues/441
                # extra_params=['--include-errored-as-dead']
                namespaces = AlbaCLI.run(command='get-disk-safety', config=config)
                cache_eviction_prefix_preset_pairs = AlbaCLI.run(command='get-maintenance-config', config=config)['cache_eviction_prefix_preset_pairs']
                presets = AlbaCLI.run(command='list-presets', config=config)
            except AlbaException as ex:
                result_handler.exception('Could not fetch alba information for backend {0} Message: {1}'.format(alba_backend.name, ex))
                # Do not execute further
                continue

            # collect in_use presets & their policies
            for preset in presets:
                if not preset['in_use']:
                    continue
                for policy in preset['policies']:
                    disk_safety_overview[alba_backend.name]['{0},{1}'.format(str(policy[0]), str(policy[1]))] = {'current_disk_safety': {}, 'max_disk_safety': policy[1]}

            # collect namespaces
            test_worthy_namespaces = (item for item in namespaces if not item['namespace'].startswith(tuple(cache_eviction_prefix_preset_pairs.keys())))
            for namespace in test_worthy_namespaces:
                # calc total objects in namespace
                total_count = 0
                for bucket_safety in namespace['bucket_safety']:
                    total_count += bucket_safety['count']

                for bucket_safety in namespace['bucket_safety']:
                    # calc safety bucket
                    calculated_disk_safety = bucket_safety['remaining_safety']
                    safety = '{0},{1}'.format(str(bucket_safety['bucket'][0]), str(bucket_safety['bucket'][1]))
                    current_disk_safety = disk_safety_overview[alba_backend.name][safety]['current_disk_safety']
                    to_be_added_namespace = \
                        {'namespace': namespace['namespace'],
                         'amount_in_bucket': "%.5f" % (float(bucket_safety['count'])/float(total_count)*100)}
                    if calculated_disk_safety in current_disk_safety:
                        current_disk_safety[calculated_disk_safety].append(to_be_added_namespace)
                    else:
                        current_disk_safety[calculated_disk_safety] = [to_be_added_namespace]
        return disk_safety_overview

    # @todo: incorporate asd-manager code to check the service
    @staticmethod
    @expose_to_cli(MODULE, 'processes-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_alba_processes(result_handler):
        """
        Checks the availability of processes for Alba
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking LOCAL ALBA services: ', add_to_result=False)
        client = SSHClient(AlbaHealthCheck.LOCAL_SR)
        services = [service for service in ServiceManager.list_services(client=client) if service.startswith(AlbaHealthCheck.MODULE)]
        if len(services) == 0:
            result_handler.skip('Found no LOCAL ALBA services.')
            return
        for service_name in services:
            if ServiceManager.get_service_status(service_name, client)[0] is True:
                result_handler.success('Service {0} is running!'.format(service_name))
            else:
                result_handler.failure('Service {0} is NOT running! '.format(service_name))

    @staticmethod
    @expose_to_cli(MODULE, 'proxy-port-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_alba_proxy_ports(result_handler):
        """
        Checks if all proxies are listening on their ports
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        for service in ServiceHelper.get_local_proxy_services():
            for port in service.ports:
                ip = service.alba_proxy.storagedriver.storage_ip
                result = NetworkHelper.check_port_connection(port, ip)
                if result:
                    result_handler.success('Connection successfully established to service {0} on {1}:{2}'.format(service.name, ip, port))
                else:
                    result_handler.failure('Connection FAILED to service {0} on {1}:{2}'.format(service.name, ip, port))
