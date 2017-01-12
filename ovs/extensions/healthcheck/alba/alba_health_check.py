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
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.dal.lists.albabackendlist import AlbaBackendList
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration, NotFoundException
from ovs.extensions.generic.system import System
from ovs.extensions.generic.volatilemutex import volatile_mutex
from ovs.extensions.healthcheck.helpers.cache import CacheHelper
from ovs.extensions.healthcheck.decorators import expose_to_cli
from ovs.extensions.healthcheck.helpers.albacli import AlbaCLI
from ovs.extensions.healthcheck.helpers.backend import BackendHelper
from ovs.extensions.healthcheck.helpers.configuration import ConfigurationManager, ConfigurationProduct
from ovs.extensions.healthcheck.helpers.exceptions import ObjectNotFoundException, ConnectionFailedException, DiskNotFoundException, ConfigNotMatchedException, AlbaException
from ovs.extensions.healthcheck.helpers.helper import Helper
from ovs.extensions.healthcheck.helpers.init_manager import InitManager
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.storagedriver import StoragedriverHelper


class AlbaHealthCheck(object):
    """
    A healthcheck for Alba storage layer
    """

    MODULE = "alba"
    TEMP_FILE_SIZE = 1048576
    SHOW_DISKS_IN_MONITORING = False
    MACHINE_DETAILS = System.get_my_storagerouter()
    MACHINE_ID = System.get_my_machine_id()
    # to be put in alba file
    TEMP_FILE_LOC = "/tmp/ovs-hc.xml"
    # fetched (from alba) file location
    TEMP_FILE_FETCHED_LOC = "/tmp/ovs-hc-fetched.xml"

    @staticmethod
    def _fetch_available_backends(logger):
        """
        Fetches the available alba backends

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :return: information about each alba backend
        :rtype: list that consists of dicts
        """

        result = []
        errors_found = 0
        for abl in BackendHelper.get_albabackends():
            # check if backend would be available for vpool
            try:
                available = False
                for preset in abl.presets:
                    available = False
                    if preset.get('is_available'):
                        available = True
                        break
                    elif len(abl.presets) == abl.presets.index(preset) + 1:
                        available = False

                # collect ASDs connected to a backend
                disks = []
                for stack in abl.local_stack.values():
                    for osds in stack.values():
                        node_id = osds.get('node_id')
                        for asd in osds.get('asds').values():
                            if abl.guid == asd.get('alba_backend_guid'):
                                asd['node_id'] = node_id
                                asd_id = asd.get('asd_id')
                                try:
                                    asd['port'] = Configuration.get('/ovs/alba/asds/{0}/config|port'.format(asd_id))
                                    disks.append(asd)
                                except NotFoundException as ex:
                                    logger.failure("Could not find {0} in Arakoon. Got {1}"
                                                   .format('/ovs/alba/asds/{0}/config|port'.format(asd_id), str(ex)))
                                    raise
                                except Exception as ex:
                                    logger.failure("Could not connect to the Arakoon.")
                                    raise ConnectionFailedException(str(ex))
                # create result
                result.append({
                        'name': abl.name,
                        'alba_id': abl.alba_id,
                        'is_available_for_vpool': available,
                        'guid': abl.guid,
                        'backend_guid': abl.backend_guid,
                        'all_disks': disks,
                        'type': abl.scaling
                    })
            except RuntimeError as e:
                errors_found += 1
                logger.failure("Error during fetch of alba backend '{0}': {1}".format(abl.name, e))
            # give a pre-check result for fetching the backend data
            if errors_found == 0:
                logger.success("No problems occurred when fetching alba backends!", 'fetch_alba_backends')
            else:
                logger.failure("Error during fetch of alba backend '{0}'".format(abl.name), 'fetch_alba_backends')

        return result

    @staticmethod
    @expose_to_cli('alba', 'proxy-test')
    def check_if_proxies_work(logger):
        """
        Checks if all Alba Proxies work on a local machine, it creates a namespace and tries to put and object

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        logger.info("Checking the ALBA proxies ...", 'check_alba_proxies')

        amount_of_presets_not_working = []

        # ignore possible subprocess output
        fnull = open(os.devnull, 'w')
        proxies_tested = 0
        # try put/get/verify on all available proxies on the local node
        for service in ServiceHelper.get_services():
            try:
                if not(service.storagerouter_guid == AlbaHealthCheck.MACHINE_DETAILS.guid and service.type.name == ServiceType.SERVICE_TYPES.ALBA_PROXY):
                    continue
                proxies_tested += 1
                logger.info("Checking ALBA proxy '{0}': ".format(service.name), 'check_alba')
                storagedriver_id = "{0}{1}".format(service.name.split('_')[1], AlbaHealthCheck.MACHINE_ID)
                ip = StoragedriverHelper.get_by_storagedriver_id(storagedriver_id).storage_ip

                # Encapsulating try to determine test output
                try:
                    # Determine what to what backend the proxy is connected
                    proxy_client_cfg = AlbaCLI.run(command="proxy-client-cfg",
                                                   named_params={'host': ip, 'port': service.ports[0]})
                except AlbaException:
                    logger.failure(
                        "Fetching proxy info has failed. Please verify if {0}:{1} is the correct address for the proxy.".format(ip, service.ports[0]))
                    continue
                # Fetch arakoon information
                abm_name = proxy_client_cfg.get("cluster_id", None)
                abm_config = ConfigurationManager.get_config_file_path(arakoon_name=abm_name,
                                                                       product=ConfigurationProduct.ARAKOON)

                # Check if proxy config is correctly setup
                if abm_name is None:
                    raise ConfigNotMatchedException('Proxy config does not have the correct format on node {0} with port {1}.'.format(ip, service.ports[0]))

                # Determine presets / backend
                try:
                    presets = AlbaCLI.run(command="list-presets", config=abm_config)
                except AlbaException:
                    logger.failure(
                        "Listing the presets has failed. Please check the arakoon config path. We used {0}".format(abm_config))
                    continue

                for preset in presets:
                    # If preset is not in use, test will fail so add a skip
                    if preset['in_use'] is False:
                        logger.skip("Preset '{0}' is not in use and will not be checked".format(preset['name']),
                                    "proxy_{0}_preset_{1}".format(service.name, preset.get("name")))
                        continue
                    # Encapsulation try for cleanup
                    try:
                        # Generate new namespace name using the preset
                        namespace_key = 'ovs-healthcheck-ns-{0}'.format(preset.get('name'))
                        object_key = 'ovs-healthcheck-obj-{0}'.format(str(uuid.uuid4()))
                        with volatile_mutex('ovs-healthcheck_proxy-test'):
                            try:
                                # Create namespace
                                AlbaCLI.run(command="proxy-create-namespace",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, preset['name']])
                            except AlbaException as ex:
                                # @TODO remove check when the issue has been that blocks uploads
                                # after namespaces are created
                                # linked ticket: https://github.com/openvstorage/alba/issues/427
                                if "Proxy exception: Proxy_protocol.Protocol.Error.NamespaceAlreadyExists" in str(ex):
                                    logger.skip("Namespace {0} already exists.".format(namespace_key))
                                else:
                                    raise
                            AlbaCLI.run(command="show-namespace", config=abm_config,
                                        extra_params=[namespace_key])
                            logger.success("Namespace successfully fetched on proxy '{0}' "
                                           "with preset '{1}'!".format(service.name, preset.get('name')),
                                           '{0}_preset_{1}_create_namespace'
                                           .format(service.name, preset.get('name')))

                            # Put test object to given dir
                            with open(AlbaHealthCheck.TEMP_FILE_LOC, 'wb') as output_file:
                                output_file.write(os.urandom(AlbaHealthCheck.TEMP_FILE_SIZE))
                            AlbaCLI.run(command="proxy-upload-object",
                                        named_params={'host': ip, 'port': service.ports[0]},
                                        extra_params=[namespace_key, AlbaHealthCheck.TEMP_FILE_LOC,
                                                      object_key])
                            logger.success("Successfully uploaded the object to namespace {0}".format(namespace_key),
                                           "{0}_preset_{1}_upload_object".format(service.name, preset.get('name')))
                            # download object
                            AlbaCLI.run(command="proxy-download-object",
                                        named_params={'host': ip, 'port': service.ports[0]},
                                        extra_params=[namespace_key, object_key,
                                                      AlbaHealthCheck.TEMP_FILE_FETCHED_LOC])
                            logger.success("Successfully downloaded the object to namespace {0}".format(namespace_key),
                                           "{0}_preset_{1}_download_object".format(service.name, preset.get('name')))
                            # check if files exists - issue #57
                            if not(os.path.isfile(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC) and os.path.isfile(AlbaHealthCheck.TEMP_FILE_LOC)):
                                # creation of object failed
                                raise ObjectNotFoundException(ValueError('Creation of object has failed'))
                            hash_original = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_LOC, 'rb').read()).hexdigest()
                            hash_fetched = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC, 'rb')
                                                       .read()).hexdigest()

                            if hash_original == hash_fetched:
                                logger.success("Creation of a object in namespace '{0}' on proxy '{1}' "
                                               "with preset '{2}' succeeded!"
                                               .format(namespace_key, service.name, preset.get('name')),
                                               '{0}_preset_{1}_compare_object'
                                               .format(service.name, preset.get('name')))
                            else:
                                logger.failure("Creation of a object '{0}' in namespace '{1}' on proxy"
                                               " '{2}' with preset '{3}' failed!"
                                               .format(object_key, namespace_key, service.name,
                                                       preset.get('name')),
                                               '{0}_preset_{1}_compare_object'
                                               .format(service.name, preset.get('name')))

                    except ObjectNotFoundException as ex:
                        amount_of_presets_not_working.append(preset.get('name'))
                        logger.failure("Failed to put object on namespace '{0}' failed on proxy '{1}' "
                                       "with preset '{2}' With error {3}".format(namespace_key, service.name,
                                                                                 preset.get('name'), ex),
                                       '{0}_preset_{1}_create_object'.format(service.name, preset.get('name')))
                    except AlbaException as ex:
                        if ex.alba_command == "proxy-create-namespace":
                            # @TODO uncomment when the issue has been that blocks uploads
                            # after namespaces are created
                            # linked ticket: https://github.com/openvstorage/alba/issues/427
                            # Should fail as we do not cleanup
                            logger.warning("Create namespace has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                           .format(str(ex), namespace_key, service.name, preset.get('name')),
                                           '{0}_preset_{1}_create_namespace'.format(service.name, preset.get('name')))
                        elif ex.alba_command == "show-namespace":
                            logger.failure("Show namespace has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                           .format(str(ex), namespace_key, service.name, preset.get('name')),
                                           '{0}_preset_{1}_show_namespace'.format(service.name, preset.get('name')))
                        elif ex.alba_command == "proxy-upload-object":
                            logger.failure("Uploading the object has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                           .format(str(ex), namespace_key, service.name, preset.get('name')),
                                           "{0}_preset_{1}_create_object".format(service.name, preset.get('name')))
                        elif ex.alba_command == "proxy-download-object":
                            logger.failure("Downloading the object has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                           .format(str(ex), namespace_key, service.name, preset.get('name')),
                                           "{0}_preset_{1}_download_object".format(service.name, preset.get('name')))
                    finally:
                        # Delete the created namespace and preset
                        try:
                            # Remove object first
                            logger.info("Deleting created object '{0}' on '{1}'.".format(object_key,
                                                                                         namespace_key))
                            try:
                                AlbaCLI.run(command="proxy-delete-object",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, object_key])
                            except AlbaException as ex:
                                # Ignore object not found
                                if "Proxy exception: Proxy_protocol.Protocol.Error.ObjectDoesNotExist" \
                                        in str(ex):
                                    pass
                                else:
                                    raise
                            subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_LOC)], stdout=fnull,
                                            stderr=subprocess.STDOUT)
                            subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC)], stdout=fnull,
                                            stderr=subprocess.STDOUT)

                            # @TODO uncomment when the issue has been that blocks uploads
                            # after namespaces are created
                            # linked ticket: https://github.com/openvstorage/alba/issues/427
                            # # Remove namespace afterwards
                            # logger.info("Deleting namespace '{0}'.".format(namespace_key))
                            #     AlbaCLI.run(command="proxy-delete-namespace",
                            #                 named_params={'host': ip, 'port': service.ports[0]},
                            #                 extra_params=[namespace_key])
                        except subprocess.CalledProcessError:
                            raise
                        except AlbaException:
                            raise
            except subprocess.CalledProcessError as ex:
                # this should stay for the deletion of the remaining files
                amount_of_presets_not_working.append(service.name)
                logger.failure("Proxy '{0}' has some problems. Got '{1}' as error".format(service.name, ex),
                               'proxy_{0}'.format(service.name))

            except ConfigNotMatchedException as ex:
                amount_of_presets_not_working.append(service.name)
                logger.failure("Proxy '{0}' has some problems. Got '{1}' as error".format(service.name, ex),
                               'proxy_{0}'.format(service.name))

        if proxies_tested == 0:
            logger.info("Found no proxies.")
        # for unattended
        return amount_of_presets_not_working

    @staticmethod
    def check_backend_asds(logger, disks, backend_name, config):
        """
        Checks if Alba ASDs work
        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler.HCLogHandler
        :param disks: list of alba ASDs
        :type disks: list[dict]
        :param backend_name: name of a existing backend
        :type backend_name: str
        :param config: path of the configuration file for the abm
        :type config: str
        :return: returns a tuple that consists of lists with working disks and defective disks
        :rtype: tuple(list)
        """

        workingdisks = []
        defectivedisks = []

        logger.info("Checking separate ASDs for backend '{0}':".format(backend_name), 'check_asds')

        # check if disks are working
        if len(disks) == 0:
            return workingdisks, defectivedisks
        # Map long id to ip
        osd_mapping = {}
        try:
            for osd in AlbaCLI.run(command='list-osds', config=config):
                osd_mapping[osd.get('long_id')] = osd.get('ips')[0]
        except AlbaException as ex:
            logger.failure("Could not fetch osd list from Alba. Got {0}".format(str(ex)))
            return None
        for disk in disks:
            key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
            disk_asd_id = disk['asd_id']
            disk_status_detail = disk['status_detail']
            disk_status = disk['status']
            value = str(time.time())
            if disk_status == 'error':
                defectivedisks.append(disk_asd_id)
                logger.failure("ASD test with DISK_ID '{0}' failed because: {1}".format(disk_asd_id, disk_status_detail),
                               'alba_asd_{0}'.format(disk_asd_id))
                continue
            # Fetch ip of the asd with list-asds
            ip_address = osd_mapping.get(disk_asd_id)
            try:
                # check if disk is missing
                if not disk.get('port'):
                    raise DiskNotFoundException('Disk is missing')
                # put object
                AlbaCLI.run(command="asd-set",
                            named_params={'host': ip_address, 'port': str(disk.get('port')),
                                          'long-id': disk_asd_id},
                            extra_params=[key, value])
                # get object
                fetched_object = AlbaCLI.run(command="asd-multi-get",
                                             named_params={'host': ip_address, 'port': str(disk.get('port')), 'long-id': disk_asd_id},
                                             extra_params=[key],
                                             to_json=False)
                # check if put/get is successful
                if 'None' in fetched_object:
                    # test failed!
                    raise ObjectNotFoundException(fetched_object)
                else:
                    # test successful!
                    logger.success("ASD test with DISK_ID '{0}' succeeded!".format(disk_asd_id),
                                   'alba_asd_{0}'.format(disk_asd_id))

                    workingdisks.append(disk_asd_id)

                # delete object
                AlbaCLI.run(command="asd-delete",
                            named_params={'host': ip_address, 'port': str(disk.get('port')),
                                          'long-id': disk_asd_id},
                            extra_params=[key])
            except ObjectNotFoundException:
                defectivedisks.append(disk_asd_id)
                logger.failure("ASD test with DISK_ID '{0}' failed on NODE '{1}'!"
                               .format(disk_asd_id, ip_address),
                               'alba_asd_{0}'.format(disk_asd_id))
            except (AlbaException, DiskNotFoundException) as e:
                defectivedisks.append(disk_asd_id)
                logger.failure("ASD test with DISK_ID '{0}' failed because: {1}"
                               .format(disk_asd_id, str(e)),
                               'alba_asd_{0}'.format(disk_asd_id))
        return workingdisks, defectivedisks

    @staticmethod
    @expose_to_cli('alba', 'backend-test')
    def check_backends(logger):
        """
        Checks Alba as a whole

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler.HCLogHandler
        """

        logger.info("Checking available ALBA backends ...")
        try:
            alba_backends = AlbaHealthCheck._fetch_available_backends(logger)
            if len(alba_backends) == 0:
                return logger.skip("No backends found ...", 'alba_backends_found')

            logger.success("We found {0} backend(s)!".format(len(alba_backends)),
                           'alba_backends_found'.format(len(alba_backends)))

            logger.info("Checking the ALBA ASDs ...")
            for backend in alba_backends:
                # check disks of backend, ignore global backends
                if backend.get('type') != 'LOCAL':
                    logger.skip("ALBA backend '{0}' is a 'global' backend ...".format(backend.get('name')), 'alba_backend_{0}'.format(backend.get('name')))
                    continue

                config = Configuration.get_configuration_path('/ovs/arakoon/{0}-abm/config'.format(backend.get('name')))
                result_disks = AlbaHealthCheck.check_backend_asds(logger, backend.get('all_disks'),
                                                                  backend.get('name'), config)
                if result_disks is None:
                    logger.failure('Could not fetch the asd information for alba backend {0}'.format(backend.get('name')), 'alba_backend_{0}'.format(backend.get('name')))
                    continue
                working_disks = result_disks[0]
                defective_disks = result_disks[1]

                # check if backend is available for vPOOL attachment / use
                if backend.get('is_available_for_vpool'):
                    if len(defective_disks) == 0:
                        logger.success("Alba backend '{0}' should be AVAILABLE FOR vPOOL USE,"
                                       " ALL asds are working fine!".format(backend.get('name')),
                                       'alba_backend_{0}'.format(backend.get('name')))
                    else:
                        logger.warning("Alba backend '{0}' should be "
                                       "AVAILABLE FOR vPOOL USE with {1} asds,"
                                       " BUT there are {2} defective asds: {3}"
                                       .format(backend.get('name'), len(working_disks), len(defective_disks),
                                               ', '.join(defective_disks)),
                                       'alba_backend_{0}'.format(backend.get('name'), len(defective_disks)))
                else:
                    if len(working_disks) == 0 and len(defective_disks) == 0:
                        logger.skip("Alba backend '{0}' is NOT available for vPool use, there are no"
                                    " asds assigned to this backend!".format(backend.get('name')),
                                    'alba_backend_{0}'.format(backend.get('name')))
                    else:
                        logger.failure("Alba backend '{0}' is NOT available for vPool use, preset"
                                       " requirements NOT SATISFIED! There are {1} working asds AND {2}"
                                       " defective asds!".format(backend.get('name'), len(working_disks),
                                                                 len(defective_disks)),
                                       'alba_backend_{0}'.format(backend.get('name')))
        except NotFoundException as ex:
            logger.failure("Failed to fetch the object with exception: {0}".format(ex))
        except ConnectionFailedException as ex:
            logger.failure("Failed to connect to configuration master with exception: {0}".format(ex),
                           'configuration_master')
        except (ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult) as e:
            logger.failure("Seems like a arakoon has some problems: {0}".format(e),
                           'arakoon_connected')

    @staticmethod
    @expose_to_cli('alba', 'disk-safety')
    def get_disk_safety(logger):
        """
        Check safety of every namespace in every backend

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler.HCLogHandler
        """

        test_name = 'disk-safety'
        max_hours_zero_disk_safety = Helper.max_hours_zero_disk_safety

        results = AlbaHealthCheck.get_disk_safety_buckets(logger=logger)
        for backend_name, policies in results.iteritems():
            logger.info('Checking disk safety on backend: {0}'.format(backend_name))
            for policy_prefix, policy_details in policies.iteritems():
                # '1,2' is policy_prefix and value is policy_details
                # {'1,2': {'max_disk_safety': 2, 'current_disk_safety': {<namespaces in safety buckets>} }
                logger.info('Checking policy `{0}` with max. disk safety `{1}`'
                            .format(policy_prefix, policy_details['max_disk_safety']))
                # if there is only 1 bucket category that is equal to the max_disk_safety, all your data is safe
                if len(policy_details['current_disk_safety'].keys()) == 1 \
                        and policy_details['current_disk_safety'].iterkeys().next() == policy_details['max_disk_safety']:
                    # all data is safe!
                    logger.success('All data is safe on backend `{0}` with `{1}` namespace(s)'
                                   .format(backend_name, len(policy_details['current_disk_safety'].itervalues()
                                                             .next())), test_name+'-'+backend_name)
                else:
                    # some data is not or less safe!
                    unattended_status = logger.success
                    for disk_safety, namespaces in policy_details['current_disk_safety'].iteritems():
                        if disk_safety == policy_details['max_disk_safety']:
                            logger.success('The disk safety of `{0}` namespace(s) is/are totally safe!'
                                           .format(len(namespaces)))
                        elif disk_safety != 0:
                            unattended_status = logger.warning
                            output = ',\n'.join([ns['namespace']+' with '+str(ns['amount_in_bucket'])+'% of its objects'
                                                 for ns in namespaces])
                            logger.warning('The disk safety of `{0}` namespace(s) is '
                                           '`{1}`, max. disk safety is `{2}`: \n{3}'
                                           .format(len(namespaces), disk_safety, policy_details['max_disk_safety'],
                                                   output))
                        else:
                            # @TODO: after x amount of hours in disk safety 0 put in error, else put in warning
                            unattended_status = logger.failure
                            output = ',\n'.join([ns['namespace']+' with '+str(ns['amount_in_bucket'])+'% of its objects'
                                                 for ns in namespaces])
                            logger.failure('The disk safety of `{0}` namespace(s) is/are ZERO: \n{1}'
                                           .format(len(namespaces), output))

                    # for unattended run
                    if not logger.print_progress:
                        unattended_status("", test_name+'-'+backend_name)

    @staticmethod
    def get_disk_safety_buckets(logger):
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

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler.HCLogHandler
        :return: Safety of every namespace in every backend
        :rtype: dict
        """

        test_name = 'disk-safety'

        disk_safety_overview = {}
        for alba_backend in AlbaBackendList.get_albabackends():
            disk_safety_overview[alba_backend.name] = {}
            config = Configuration.get_configuration_path('ovs/arakoon/{0}-abm/config'.format(alba_backend.name))
            # Fetch alba info
            try:
                # @TODO add this to extra_params to include corrupt asds. Currently there is a bug with it
                # Ticket: https://github.com/openvstorage/alba/issues/441
                # extra_params=['--include-errored-as-dead']
                namespaces = AlbaCLI.run(command='get-disk-safety', config=config)
                presets = AlbaCLI.run(command='list-presets', config=config)
            except AlbaException as ex:
                logger.exception('Could not fetch alba information for backend `{0}` Message: {1}'
                                 .format(alba_backend.name, ex), test_name)
                # Do not execute further
                continue

            # collect in_use presets & their policies
            for preset in presets:
                if preset['in_use']:
                    for policy in preset['policies']:
                        disk_safety_overview[alba_backend.name][str(policy[0])+','+str(policy[1])] = \
                            {'current_disk_safety': {}, 'max_disk_safety': policy[1]}

            # collect namespaces
            for namespace in namespaces:
                for bucket_safety in namespace['bucket_safety']:
                    # calc safety bucket
                    bucket = bucket_safety['bucket']
                    min_disk_safety = bucket[0]
                    max_disk_safety = bucket[1]
                    current_disk_safety = bucket[2]
                    calculated_disk_safety = \
                        current_disk_safety + bucket_safety['applicable_dead_osds'] + \
                        (min_disk_safety - max_disk_safety)
                    to_be_added_namespace = {'namespace': namespace['namespace'], 'amount_in_bucket':
                                                                                  (bucket_safety['count'] /
                                                                                   namespace['safety_count'])*100}
                    if calculated_disk_safety in disk_safety_overview[alba_backend.name][str(min_disk_safety)+','+str(max_disk_safety)]['current_disk_safety']:
                        disk_safety_overview[alba_backend.name][str(min_disk_safety) + ',' + str(max_disk_safety)][
                            'current_disk_safety'][calculated_disk_safety].append(to_be_added_namespace)
                    else:
                        disk_safety_overview[alba_backend.name][str(min_disk_safety) + ',' + str(max_disk_safety)][
                            'current_disk_safety'][calculated_disk_safety] = [to_be_added_namespace]

        return disk_safety_overview

    @staticmethod
    @expose_to_cli('alba', 'processes-test')
    def check_alba_processes(logger):
        """
        Checks the availability of processes for Alba

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler.HCLogHandler
        """
        test_name = 'check_alba_processes'
        logger.info("Checking LOCAL ALBA services: ", test_name)
        services = InitManager.get_local_services(prefix='alba', ip=AlbaHealthCheck.MACHINE_DETAILS.ip)
        if len(services) > 0:
            for service_name in services:
                if InitManager.service_running(service_name=service_name, ip=AlbaHealthCheck.MACHINE_DETAILS.ip):
                    logger.success("Service '{0}' is running!".format(service_name),
                                   'process_{0}'.format(service_name))
                else:
                    logger.failure("Service '{0}' is NOT running, please check this... ".format(service_name),
                                   'process_{0}'.format(service_name))
        else:
            logger.skip("Found no LOCAL ALBA services.", test_name)

    @staticmethod
    @expose_to_cli('alba', 'test')
    def run(logger):
        AlbaHealthCheck.check_backends(logger)
        AlbaHealthCheck.check_if_proxies_work(logger)
        AlbaHealthCheck.get_disk_safety(logger)
        AlbaHealthCheck.check_alba_processes(logger)
