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
import re
import uuid
import time
import hashlib
import subprocess
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration, NotFoundException
from ovs.extensions.generic.system import System
from ovs.extensions.generic.volatilemutex import volatile_mutex
from ovs.extensions.healthcheck.helpers.cache import CacheHelper
from ovs.extensions.healthcheck.decorators import exposetocli
from ovs.extensions.healthcheck.helpers.albacli import AlbaCLI
from ovs.extensions.healthcheck.helpers.backend import BackendHelper
from ovs.extensions.healthcheck.helpers.configuration import ConfigurationManager, ConfigurationProduct
from ovs.extensions.healthcheck.helpers.exceptions import ObjectNotFoundException, ConnectionFailedException, \
    DiskNotFoundException, ConfigNotMatchedException, AlbaException
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
        :type logger: ovs.log.healthcheck_logHandler
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
            # give a precheck result for fetching the backend data
            if errors_found == 0:
                logger.success("No problems occured when fetching alba backends!", 'fetch_alba_backends')
            else:
                logger.failure("Error during fetch of alba backend '{0}'".format(abl.name), 'fetch_alba_backends')

        return result

    @staticmethod
    @exposetocli('alba', 'proxy-test')
    def check_if_proxies_work(logger):
        """
        Checks if all Alba Proxies work on a local machine, it creates a namespace and tries to put and object

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler
        """
        logger.info("Checking the ALBA proxies ...", 'check_alba_proxies')

        amount_of_presets_not_working = []

        # ignore possible subprocess output
        fnull = open(os.devnull, 'w')
        proxies_tested = 0
        # try put/get/verify on all available proxies on the local node
        for service in ServiceHelper.get_services():
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

                # Fetch arakoon information
                abm_name = proxy_client_cfg.get("cluster_id", None)
                abm_config = ConfigurationManager.get_config_file_path(arakoon_name=abm_name,
                                                                       product=ConfigurationProduct.ARAKOON)

                # Check if proxy config is correctly setup
                if abm_name is None:
                    raise ConfigNotMatchedException('Proxy config does not have the correct format on node {0} with port {1}.'.format(ip, service.ports[0]))

                # Determine presets / backend
                presets = AlbaCLI.run(command="list-presets", config=abm_config)

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
                            except RuntimeError as ex:
                                # @TODO remove check when the issue has been that blocks uploads
                                # after namespaces are created
                                # linked ticket: https://github.com/openvstorage/alba/issues/427
                                if "Proxy exception: Proxy_protocol.Protocol.Error.NamespaceAlreadyExists" in \
                                        str(ex):
                                    logger.skip("Namespace {0} already exists.".format(namespace_key))
                                else:
                                    # pass
                                    raise AlbaException("Create namespace has failed with {0} on namespace {1} "
                                                        "with proxy {2} with preset {3}"
                                                        .format(str(ex), namespace_key, service.name,
                                                                preset.get('name')), "proxy-create-namespace")
                            try:
                                # Fetch namespace
                                AlbaCLI.run(command="show-namespace", config=abm_config,
                                            extra_params=[namespace_key])
                                logger.success("Namespace successfully fetched on proxy '{0}' "
                                               "with preset '{1}'!".format(service.name, preset.get('name')),
                                               '{0}_preset_{1}_create_namespace'
                                               .format(service.name, preset.get('name')))
                            except RuntimeError as ex:
                                raise AlbaException("Show namespace has failed with {0} on namespace {1} "
                                                    "with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name,
                                                            preset.get('name')), "show-namespace")

                            # Put test object to given dir
                            with open(AlbaHealthCheck.TEMP_FILE_LOC, 'wb') as fout:
                                fout.write(os.urandom(AlbaHealthCheck.TEMP_FILE_SIZE))
                            try:
                                # try to put object
                                AlbaCLI.run(command="proxy-upload-object",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, AlbaHealthCheck.TEMP_FILE_LOC,
                                                          object_key])
                                logger.success("Succesfully uploaded the object to namespace {0}"
                                               .format(namespace_key),
                                               "{0}_preset_{1}_upload_object"
                                               .format(service.name, preset.get('name')))
                            except RuntimeError as ex:
                                raise AlbaException("Uploading the object has failed with {0} on namespace {1} "
                                                    "with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name,
                                                            preset.get('name')), "proxy-upload-object")
                            try:
                                # download object
                                AlbaCLI.run(command="proxy-download-object",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, object_key,
                                                          AlbaHealthCheck.TEMP_FILE_FETCHED_LOC])
                                logger.success("Succesfully downloaded the object to namespace {0}"
                                               .format(namespace_key),
                                               "{0}_preset_{1}_download_object".format(service.name,
                                                                                       preset.get('name')))
                            except RuntimeError as ex:
                                raise AlbaException("Downloading the object has failed with {0} "
                                                    "on namespace {1} with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name,
                                                            preset.get('name')),
                                                    "proxy-download-object")
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

                    except ObjectNotFoundException as e:
                        amount_of_presets_not_working.append(preset.get('name'))
                        logger.failure("Failed to put object on namespace '{0}' failed on proxy '{1}' "
                                       "with preset '{2}' With error {3}".format(namespace_key, service.name,
                                                                                 preset.get('name'), e),
                                       '{0}_preset_{1}_create_object'.format(service.name, preset.get('name')))
                    except AlbaException as e:
                        if e.alba_command == "proxy-create-namespace":
                            # @TODO uncomment when the issue has been that blocks uploads
                            # after namespaces are created
                            # linked ticket: https://github.com/openvstorage/alba/issues/427
                            # Should fail as we do not cleanup
                            logger.warning(str(e), '{0}_preset_{1}_create_namespace'.format(service.name,
                                                                                            preset.get('name')))
                        if e.alba_command == "show-namespace":
                            logger.failure(str(e), '{0}_preset_{1}_show_namespace'.format(service.name,
                                                                                          preset.get('name')))
                        if e.alba_command == "proxy-upload-object":
                            logger.failure(str(e), "{0}_preset_{1}_create_object".format(service.name,
                                                                                         preset.get('name')))
                        if e.alba_command == "download-object":
                            logger.failure(str(e), "{0}_preset_{1}_download_object".format(service.name,
                                                                                           preset.get('name')))
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
                            except RuntimeError as ex:
                                # Ignore object not found
                                if "Proxy exception: Proxy_protocol.Protocol.Error.ObjectDoesNotExist" \
                                        in str(ex):
                                    pass
                                else:
                                    raise AlbaException("Deleting the object has failed with {0}"
                                                        .format(str(ex)), "proxy-delete-object")
                            subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_LOC)], stdout=fnull,
                                            stderr=subprocess.STDOUT)
                            subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC)], stdout=fnull,
                                            stderr=subprocess.STDOUT)

                            # @TODO uncomment when the issue has been that blocks uploads
                            # after namespaces are created
                            # linked ticket: https://github.com/openvstorage/alba/issues/427
                            # # Remove namespace afterwards
                            # logger.info("Deleting namespace '{0}'.".format(namespace_key))
                            # try:
                            #     AlbaCLI.run(command="proxy-delete-namespace",
                            #                 named_params={'host': ip, 'port': service.ports[0]},
                            #                 extra_params=[namespace_key])
                            # except RuntimeError as ex:
                            #     raise AlbaException("Deleting namespace failed with {0}".format(str(ex)),
                            # "proxy-delete-namespace")
                        except subprocess.CalledProcessError:
                            raise
                        except AlbaException:
                            raise
            except subprocess.CalledProcessError as e:
                # this should stay for the deletion of the remaining files
                amount_of_presets_not_working.append(service.name)
                logger.failure("Proxy '{0}' has some problems. Got '{1}' as error".format(service.name, e),
                               'proxy_{0}'.format(service.name))

            except ConfigNotMatchedException as e:
                amount_of_presets_not_working.append(service.name)
                logger.failure("Proxy '{0}' has some problems. Got '{1}' as error".format(service.name, e),
                               'proxy_{0}'.format(service.name))
        if proxies_tested == 0:
            logger.info("Found no proxies.")
        # for unattended
        return amount_of_presets_not_working

    @staticmethod
    def check_backend_asds(logger, disks, backend_name, config):
        """
        Checks if Alba ASD's work

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param disks: list of alba ASD's
        :type disks: list
        :param backend_name: name of a existing backend
        :type backend_name: str
        :param config: path of the configuration file for the abm
        :type config: str
        :return: returns a tuple that consists of lists: (workingdisks, defectivedisks)
        :rtype: tuple that consists of lists
        """

        workingdisks = []
        defectivedisks = []

        logger.info("Checking seperate ASD's for backend '{0}':".format(backend_name), 'check_asds')

        # check if disks are working
        if len(disks) == 0:
            return workingdisks, defectivedisks
        # Map long id to ip
        osd_mapping = {}
        try:
            for osd in AlbaCLI.run(command='list-osds', config=config):
                osd_mapping[osd.get('long_id')] = osd.get('ips')[0]
        except RuntimeError as ex:
            logger.failure("Could not fetch osd list from Alba. Got {0}".format(str(ex)))
            return None
        for disk in disks:
            key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
            value = str(time.time())
            if disk.get('status') == 'error':
                defectivedisks.append(disk.get('asd_id'))
                logger.failure("ASD test with DISK_ID '{0}' failed because: {1}".format(disk.get('asd_id'), disk.get('status_detail')),
                               'alba_asd_{0}'.format(disk.get('asd_id')))
                continue
            # Fetch ip of the asd with list-asds
            ip_address = osd_mapping.get(disk.get('asd_id'))
            try:
                # check if disk is missing
                if not disk.get('port'):
                    raise DiskNotFoundException('Disk is missing')
                # put object
                try:
                    AlbaCLI.run(command="asd-set",
                                named_params={'host': ip_address, 'port': str(disk.get('port')),
                                              'long-id': disk.get('asd_id')},
                                extra_params=[key, value])
                except RuntimeError as ex:
                    raise AlbaException(str(ex), 'asd-set')
                # get object
                try:
                    fetched_object = AlbaCLI.run(command="asd-multi-get",
                                    named_params={'host': ip_address, 'port': str(disk.get('port')),
                                                  'long-id': disk.get('asd_id')},
                                    extra_params=[key],
                                    to_json=False)
                except RuntimeError as ex:
                    raise AlbaException(str(ex), 'asd-multi-get')

                # check if put/get is successfull
                if 'None' in fetched_object:
                    # test failed!
                    raise ObjectNotFoundException(fetched_object)
                else:
                    # test successfull!
                    logger.success("ASD test with DISK_ID '{0}' succeeded!".format(disk.get('asd_id')),
                                   'alba_asd_{0}'.format(disk.get('asd_id')))

                    workingdisks.append(disk.get('asd_id'))

                # delete object
                try:
                    AlbaCLI.run(command="asd-delete",
                                named_params={'host': ip_address, 'port': str(disk.get('port')),
                                              'long-id': disk.get('asd_id')},
                                extra_params=[key])
                except RuntimeError as ex:
                    raise AlbaException(str(ex), 'asd-delete')

            except ObjectNotFoundException:
                defectivedisks.append(disk.get('asd_id'))
                logger.failure("ASD test with DISK_ID '{0}' failed on NODE '{1}'!"
                               .format(disk.get('asd_id'), ip_address),
                               'alba_asd_{0}'.format(disk.get('asd_id')))
            except (AlbaException, DiskNotFoundException) as e:
                defectivedisks.append(disk.get('asd_id'))
                logger.failure("ASD test with DISK_ID '{0}' failed because: {1}"
                               .format(disk.get('asd_id'), str(e)),
                               'alba_asd_{0}'.format(disk.get('asd_id')))
        return workingdisks, defectivedisks

    @staticmethod
    @exposetocli('alba', 'backend-test')
    def check_backends(logger):
        """
        Checks Alba as a whole

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking available ALBA backends ...")
        if System.get_my_storagerouter().node_type == 'EXTRA':
            return logger.skip("Skipping ASD check because this is a EXTRA node ...")
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
                    logger.failure('Could not fetch the asd information for alba backend {0}'.format(backend.get('name')),'alba_backend_{0}'.format(backend.get('name')))
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
    @exposetocli('alba', 'disk-safety')
    def get_disk_safety(logger):
        """
        Send disk safety for each vpool and the amount of namespaces with the lowest disk safety to DB
        """

        logger.info('Checking if objects need to be repaired...')
        test_name = 'disk-safety'
        abm_services = set(service for service in ServiceHelper.get_services() if service.type.name == ServiceType.SERVICE_TYPES.ALBA_MGR)

        disk_lost_overview = {}
        for abm_service in abm_services:
            alba_backend = abm_service.abm_service.alba_backend
            if alba_backend.name in disk_lost_overview:
                continue
            # Determine if services are from ab instance
            config = Configuration.get_configuration_path('ovs/arakoon/{0}-abm/config'.format(alba_backend.name))
            # Fetch alba info
            presets = []
            try:
                try:
                    # @TODO add this to extra_params to include errored asds. Currently there is a bug with it
                    # Ticket: https://github.com/openvstorage/alba/issues/441
                    # extra_params=['--include-errored-as-dead']
                    namespaces = AlbaCLI.run(command='get-disk-safety', config=config)
                except Exception as ex:
                    raise AlbaException(str(ex), 'get-disk-safety')
                try:
                    presets = AlbaCLI.run(command='list-presets', config=config)
                except Exception as ex:
                    AlbaException(str(ex), 'list-presets')
            except AlbaException as ex:
                logger.exception('Could not fetch alba information. Message: {0}'.format(ex), test_name)
                # Do not execute further
                continue

            # Maximum amount of disks that may be lost - preset will determine this
            max_lost_disks = 0
            for preset_name in presets:
                for policy in preset_name['policies']:
                    if policy[1] > max_lost_disks:
                        max_lost_disks = policy[1]

            lost_disks = {}
            details = {'total_objects': 0, 'lost_disks': lost_disks}
            disk_lost_overview[alba_backend.name] = details

            for namespace in namespaces:
                for bucket_safety in namespace['bucket_safety']:
                    bucket = bucket_safety['bucket']
                    disk_lost = abs(bucket[2] - bucket_safety['applicable_dead_osds'] - (bucket[0] + bucket[1]))
                    remaining_safety = bucket_safety['remaining_safety']
                    if disk_lost not in lost_disks:
                        lost_disks[disk_lost] = {"remaining_safety": remaining_safety, "objects_to_repair": 0}
                    # Amount of lost disks at this point
                        lost_disks[disk_lost]['objects_to_repair'] += bucket_safety['count']
                    details['total_objects'] += bucket_safety['count']
        for backend_name, disk_safety_info in disk_lost_overview.iteritems():
            # Get worst values first to see if the environment is in a critical state
            objects_lost = sum(item["objects_to_repair"] for item in disk_safety_info["lost_disks"].values() if item["remaining_safety"] < 0)
            lowest_safety = min(item["remaining_safety"] for item in disk_safety_info["lost_disks"].values()) if len(disk_safety_info["lost_disks"].values()) > 0 else 0
            objects_no_safety = disk_safety_info.get(0, 0)
            objects_to_repair = sum(item["objects_to_repair"] for key, item in disk_safety_info["lost_disks"].iteritems() if key >= 0) - objects_lost
            disk_lost = min(key for key in disk_safety_info["lost_disks"].keys()) if len(disk_safety_info["lost_disks"].keys()) > 0 else 0
            total_objects = disk_safety_info['total_objects']
            # limit to 4 numbers
            repair_percentage = float('{0:.4f}'.format((float(objects_to_repair) / total_objects) * 100)) if total_objects != 0 else 0
            if disk_lost == 0:
                logger.success('Backend {0} has no disks that are lost.'.format(backend_name))
            else:
                msg = "Another {0} disks can be lost." if lowest_safety > 0 else "Losing more disks will cause data loss!"
                logger.failure('Backend {0} has lost {1} disk(s). {2}'.format(backend_name, disk_lost, msg))

            msg = 'Backend {0}: {1} out of {2} objects have to be repaired.'.format(backend_name, objects_to_repair, total_objects)
            if objects_to_repair == 0:
                logger.success(msg)
            else:
                logger.warning(msg)
            if objects_no_safety > 0:
                logger.failure('Backend {0}: {1} out of {2} objects will be beyond repair if another disk fails.')
            if objects_lost > 0:
                logger.failure('Backend {0}: {1} out of {2} objects are beyond repair.')
            # logger.warning('Backend {0}: {1}% of the objects have to be repaired'.format(backend_name,
            #                                                                              repair_percentage))
            # Log if the amount is rising
            cache = CacheHelper.get()
            repair_rising = False
            if cache is None or cache.get(backend_name, None) is None:
                # First run of healthcheck
                logger.success('Object repair for backend_name {0} will be monitored on incrementations.'.format(backend_name))
            elif objects_to_repair == 0:
                # Amount of objects to repair are rising
                logger.success('No objects in objects repair queue for backend_name {0}.'.format(backend_name))
            elif cache[backend_name]['object_to_repair'] > objects_to_repair:
                # Amount of objects to repair is descending
                logger.success('Amount of objects to repair is descending for backend_name {0}.'.format(backend_name))
            elif cache[backend_name]['object_to_repair'] < objects_to_repair:
                # Amount of objects to repair is rising
                repair_rising = True
                logger.failure('Amount of objects to repair are rising for backend_name {0}.'.format(backend_name))
            elif cache[backend_name]['object_to_repair'] == objects_to_repair:
                # Amount of objects to repair is the same
                logger.success('Amount of objects to repair are the same for backend_name {0}.'.format(backend_name))

            if logger.print_progress is False:
                # Custom recap for operations
                logger.custom(
                    'Recap of disk-safety: {0}% of the objects have to be repaired. Backend has lost {1} and number of objects to repair are {2}.'
                    .format(repair_percentage, disk_lost, 'rising' if repair_rising is True else 'descending or the same'),
                    '{0}_{1}'.format(test_name, backend_name),
                    ' '.join([str(repair_percentage), 'SUCCESS' if disk_lost == 0 else 'FAILURE', 'FAILURE' if repair_rising is True else 'SUCCESS']))
            cache[backend_name] = {
                    'object_to_repair': objects_to_repair,
                    'total_objects': total_objects
                }
            CacheHelper.set(cache)
        return CacheHelper.get()

    @staticmethod
    @exposetocli('alba', 'processes-test')
    def check_alba_processes(logger):
        """
        Checks the availability of processes for Alba

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
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
    @exposetocli('alba', 'test')
    def run(logger):
        AlbaHealthCheck.check_backends(logger)
        AlbaHealthCheck.check_if_proxies_work(logger)
        AlbaHealthCheck.get_disk_safety(logger)
        AlbaHealthCheck.check_alba_processes(logger)
