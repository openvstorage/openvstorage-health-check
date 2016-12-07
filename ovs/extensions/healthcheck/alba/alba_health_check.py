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

import json
import os
import re
import uuid
import time
import hashlib
import subprocess
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.helpers.cache import CacheHelper
from ovs.extensions.healthcheck.decorators import ExposeToCli
from ovs.extensions.healthcheck.helpers.albacli import AlbaCLI
from ovs.extensions.healthcheck.helpers.alba_node import AlbaNodeHelper
from ovs.extensions.healthcheck.helpers.backend import BackendHelper
from ovs.extensions.healthcheck.helpers.configuration import ConfigurationManager, ConfigurationProduct
from ovs.extensions.healthcheck.helpers.exceptions import ObjectNotFoundException, ConnectionFailedException, \
    DiskNotFoundException, ConfigNotMatchedException, AlbaException
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
                                except Exception as ex:
                                    raise ConnectionFailedException(ex)
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
                logger.failure("Error during fetch of alba backend '{0}': {1}".format(abl.name, e), 'check_alba')

            # give a precheck result for fetching the backend data
            if errors_found == 0:
                logger.success("No problems occured when fetching alba backends!", 'fetch_alba_backends')
            else:
                logger.failure("Error during fetch of alba backend '{0}'".format(abl.name), 'fetch_alba_backends')

        return result

    @staticmethod
    @ExposeToCli('alba', 'proxy-test')
    def check_if_proxies_work(logger):
        """
        Checks if all Alba Proxies work on a local machine, it creates a namespace and tries to put and object

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler
        """

        amount_of_presets_not_working = []

        # ignore possible subprocess output
        fnull = open(os.devnull, 'w')

        proxies_tested = 0

        logger.info("Starting alba proxy-test")
        # try put/get/verify on all available proxies on the local node
        for service in ServiceHelper.get_services():
            if service.storagerouter_guid == AlbaHealthCheck.MACHINE_DETAILS.guid and service.type.name == ServiceType.SERVICE_TYPES.ALBA_PROXY:
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
                    abm_config = ConfigurationManager.get_config_file_path(arakoon_name=abm_name, product=ConfigurationProduct.ARAKOON)

                    # Check if proxy config is correctly setup
                    if abm_name is None or re.match('^client_cfg:\n{ cluster_id = "(?P<cluster_id>[0-9a-zA-Z_-]+)";.*', abm_name) is None:
                        ConfigNotMatchedException('Proxy config does not have the correct format on node {0}'
                                                  ' with port {1}.'.format(ip, service.ports[0]))

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
                            try:
                                # Create namespace
                                AlbaCLI.run(command="proxy-create-namespace",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, preset['name']])
                            except RuntimeError as ex:
                                # @TODO remove check when the issue has been that blocks uploads
                                # after namespaces are created
                                # linked ticket: https://github.com/openvstorage/alba/issues/427
                                if "Proxy exception: Proxy_protocol.Protocol.Error.NamespaceAlreadyExists" in str(ex):
                                    logger.skip("Namespace {0} already exists.".format(namespace_key))
                                else:
                                    # pass

                                    raise AlbaException("Create namespace has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name, preset.get('name')),
                                                    "proxy-create-namespace")
                            try:
                                # Fetch namespace
                                AlbaCLI.run(command="show-namespace", config=abm_config, extra_params=[namespace_key])
                                logger.success("Namespace successfully fetched on proxy '{0}' with preset '{1}'!"
                                               .format(service.name, preset.get('name')),
                                               '{0}_preset_{1}_create_namespace'
                                               .format(service.name, preset.get('name')))
                            except RuntimeError as ex:
                                raise AlbaException("Show namespace has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name, preset.get('name')),
                                                    "show-namespace")

                            # Put test object to given dir
                            with open(AlbaHealthCheck.TEMP_FILE_LOC, 'wb') as fout:
                                fout.write(os.urandom(AlbaHealthCheck.TEMP_FILE_SIZE))
                            try:
                                # try to put object
                                AlbaCLI.run(command="proxy-upload-object",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, AlbaHealthCheck.TEMP_FILE_LOC, object_key])
                                logger.success("Succesfully uploaded the object to namespace {0}".format(namespace_key),
                                              "{0}_preset_{1}_upload_object".format(service.name, preset.get('name')))
                            except RuntimeError as ex:
                                raise AlbaException("Uploading the object has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name, preset.get('name')),
                                                    "proxy-upload-object")
                            try:
                                # download object
                                AlbaCLI.run(command="proxy-download-object",
                                            named_params={'host': ip, 'port': service.ports[0]},
                                            extra_params=[namespace_key, object_key, AlbaHealthCheck.TEMP_FILE_FETCHED_LOC])
                                logger.success("Succesfully downloaded the object to namespace {0}".format(namespace_key),
                                              "{0}_preset_{1}_download_object".format(service.name, preset.get('name')))
                            except RuntimeError as ex:
                                raise AlbaException("Downloading the object has failed with {0} on namespace {1} with proxy {2} with preset {3}"
                                                    .format(str(ex), namespace_key, service.name, preset.get('name')),
                                                    "proxy-download-object")
                            # check if files exists - issue #57
                            if os.path.isfile(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC) \
                                    and os.path.isfile(AlbaHealthCheck.TEMP_FILE_LOC):
                                hash_original = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_LOC, 'rb').read())\
                                    .hexdigest()
                                hash_fetched = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC, 'rb')
                                                           .read()).hexdigest()

                                if hash_original == hash_fetched:
                                    logger.success("Creation of a object in namespace '{0}' on proxy '{1}' "
                                                   "with preset '{2}' succeeded!"
                                                   .format(namespace_key,service.name,preset.get('name')),
                                                   '{0}_preset_{1}_compare_object'
                                                   .format(service.name, preset.get('name')))
                                else:
                                    logger.failure("Creation of a object '{0}' in namespace '{1}' on proxy"
                                                   " '{2}' with preset '{3}' failed!"
                                                   .format(object_key, namespace_key, service.name,
                                                           preset.get('name')),
                                                   '{0}_preset_{1}_compare_object'
                                                   .format(service.name, preset.get('name')))
                            else:
                                # creation of object failed
                                raise ObjectNotFoundException(ValueError('Creation of object has failed'))

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
                                logger.warning(str(e), '{0}_preset_{1}_create_namespace'.format(service.name, preset.get('name')))
                            if e.alba_command == "show-namespace":
                                logger.failure(str(e), '{0}_preset_{1}_show_namespace'.format(service.name, preset.get('name')))
                            if e.alba_command == "proxy-upload-object":
                                logger.failure(str(e), "{0}_preset_{1}_create_object".format(service.name, preset.get('name')))
                            if e.alba_command == "download-object":
                                logger.failure(str(e), "{0}_preset_{1}_download_object".format(service.name, preset.get('name')))
                        finally:
                            # Delete the created namespace and preset
                            try:
                                # Remove object first
                                logger.info("Deleting created object '{0}' on '{1}'.".format(object_key, namespace_key))
                                try:
                                    AlbaCLI.run(command="proxy-delete-object",
                                                named_params={'host': ip, 'port': service.ports[0]},
                                                extra_params=[namespace_key, object_key])
                                except RuntimeError as ex:
                                    # Ignore object not found
                                    if "Proxy exception: Proxy_protocol.Protocol.Error.ObjectDoesNotExist" in str(ex):
                                        pass
                                    else:
                                        raise AlbaException("Deleting the object has failed with {0}".format(str(ex)), "proxy-delete-object")
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
                                #     raise AlbaException("Deleting namespace failed with {0}".format(str(ex)), "proxy-delete-namespace")
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
    def check_backend_asds(logger, disks, backend_name):
        """
        Checks if Alba ASD's work

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param disks: list of alba ASD's
        :type disks: list
        :param backend_name: name of a existing backend
        :type backend_name: str
        :return: returns a tuple that consists of lists: (workingdisks, defectivedisks)
        :rtype: tuple that consists of lists
        """

        workingdisks = []
        defectivedisks = []

        logger.info("Checking seperate ASD's for backend '{0}':".format(backend_name), 'check_asds')

        # check if disks are working
        if len(disks) != 0:
            for disk in disks:
                key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
                value = str(time.time())

                if disk.get('status') != 'error':
                    ip_address = AlbaNodeHelper.get_albanode_by_node_id(disk.get('node_id')).ip
                    try:
                        # check if disk is missing
                        if disk.get('port'):
                            # put object
                            AlbaCLI.run(command="asd-set",
                                        named_params={'host': ip_address, 'port': str(disk.get('port')),
                                                      'long-id': disk.get('asd_id')},
                                        extra_params=[key, value])
                            # get object
                            try:
                                g = AlbaCLI.run(command="asd-multi-get",
                                                named_params={'host': ip_address, 'port': str(disk.get('port')),
                                                              'long-id': disk.get('asd_id')},
                                                extra_params=[key],
                                                to_json=False)
                            except RuntimeError:
                                raise ConnectionFailedException('Connection failed to disk')

                            # check if put/get is successfull
                            if 'None' in g:
                                # test failed!
                                raise ObjectNotFoundException(g)
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
                            except RuntimeError:
                                raise ConnectionFailedException('Connection failed to disk when trying to delete!')
                        else:
                            # disk is missing
                            raise DiskNotFoundException('Disk is missing')

                    except ObjectNotFoundException:
                        defectivedisks.append(disk.get('asd_id'))
                        logger.failure("ASD test with DISK_ID '{0}' failed on NODE '{1}'!"
                                       .format(disk.get('asd_id'), ip_address),
                                       'alba_asd_{0}'.format(disk.get('asd_id')))
                    except (ConnectionFailedException, DiskNotFoundException) as e:
                        defectivedisks.append(disk.get('asd_id'))
                        logger.failure("ASD test with DISK_ID '{0}' failed because: {1}"
                                       .format(disk.get('asd_id'), e),
                                       'alba_asd_{0}'.format(disk.get('asd_id')))
                else:
                    defectivedisks.append(disk.get('asd_id'))
                    logger.failure("ASD test with DISK_ID '{0}' failed because: {1}"
                                   .format(disk.get('asd_id'), disk.get('status_detail')),
                                   'alba_asd_{0}'.format(disk.get('asd_id')))

        return workingdisks, defectivedisks

    @staticmethod
    @ExposeToCli('alba', 'asds-test')
    def check_asds(logger):
        """
        Checks Alba as a whole

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        logger.info("Checking available ALBA backends ...")
        try:
            alba_backends = AlbaHealthCheck._fetch_available_backends(logger)
            if len(alba_backends) != 0:
                logger.success("We found {0} backend(s)!".format(len(alba_backends)),
                               'alba_backends_found'.format(len(alba_backends)))

                logger.info("Checking the ALBA ASDs ...", 'check_alba_asds')
                if System.get_my_storagerouter().node_type != 'EXTRA':
                    logger.success("Start checking all the ASDs!", 'check_alba_asds')
                    for backend in alba_backends:

                        # check disks of backend, ignore global backends
                        if backend.get('type') == 'LOCAL':
                            result_disks = AlbaHealthCheck.check_backend_asds(logger, backend.get('all_disks'),
                                                                              backend.get('name'))
                            workingdisks = result_disks[0]
                            defectivedisks = result_disks[1]

                            # check if backend is available for vPOOL attachment / use
                            if backend.get('is_available_for_vpool'):
                                if len(defectivedisks) == 0:
                                    logger.success("Alba backend '{0}' should be AVAILABLE FOR vPOOL USE,"
                                                   " ALL asds are working fine!".format(backend.get('name')),
                                                   'alba_backend_{0}'.format(backend.get('name')))
                                else:
                                    logger.warning("Alba backend '{0}' should be "
                                                   "AVAILABLE FOR vPOOL USE with {1} asds,"
                                                   " BUT there are {2} defective asds: {3}"
                                                   .format(backend.get('name'), len(workingdisks), len(defectivedisks),
                                                           ', '.join(defectivedisks)),
                                                   'alba_backend_{0}'.format(backend.get('name'), len(defectivedisks)))
                            else:
                                if len(workingdisks) == 0 and len(defectivedisks) == 0:
                                    logger.skip("Alba backend '{0}' is NOT available for vPool use, there are no"
                                                " asds assigned to this backend!".format(backend.get('name')),
                                                'alba_backend_{0}'.format(backend.get('name')))
                                else:
                                    logger.failure("Alba backend '{0}' is NOT available for vPool use, preset"
                                                   " requirements NOT SATISFIED! There are {1} working asds AND {2}"
                                                   " defective asds!".format(backend.get('name'), len(workingdisks),
                                                                             len(defectivedisks)),
                                                   'alba_backend_{0}'.format(backend.get('name')))
                        else:
                            logger.skip("ALBA backend '{0}' is a 'global' backend ...".format(backend.get('name')),
                                        'alba_backend_{0}'.format(backend.get('name')))
                else:
                    logger.skip("Skipping ASD check because this is a EXTRA node ...", 'check_alba_asds')
            else:
                logger.skip("No backends found ...", 'alba_backends_found')
        except ConnectionFailedException as ex:
            logger.failure("Failed to connect to configuration master with exception: {0}".format(ex),
                           'configuration_master')
        except (ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult) as e:
            logger.failure("Seems like a arakoon has some problems: {0}".format(e),
                           'arakoon_connected')

    @staticmethod
    @ExposeToCli('alba', 'disk-safety')
    def get_disk_safety(logger):
        """
        Send disk safety for each vpool and the amount of namespaces with the lowest disk safety to DB
        """

        logger.info("Checking if objects need to be repaired...")

        points = []
        abms = []

        test_name = 'disk-safety'
        result = {
                "repair_percentage": None,
                "lost_disks": None
            }
        for service in ServiceHelper.get_services():
            if service.type.name == ServiceType.SERVICE_TYPES.ALBA_MGR and service not in abms:
                abms.append(service.name)

        abl = BackendHelper.get_albabackends()
        for ab in abl:
            # Determine if services are from ab instance
            service_name = ServiceHelper.get_service(ab.abm_services[0].service_guid).name
            if service_name not in abms:
                continue

            config = Configuration.get_configuration_path('ovs/arakoon/{0}/config'.format(service_name))

            # Fetch alba info
            try:
                try:
                    # @TODO add this to extra_params to include errored asds. Currently there is a bug with it
                    # Ticket: https://github.com/openvstorage/alba/issues/441
                    # extra_params=["--include-errored-as-dead"]
                    namespaces = AlbaCLI.run(command="get-disk-safety", config=config)
                except Exception as ex:
                    raise SystemError("Could not execute 'alba get-disk-safety'. Got {0}".format(ex.message))
                try:
                    presets = AlbaCLI.run(command="list-presets", config=config)
                except Exception as ex:
                    raise SystemError("Could not execute 'list-presets'. Got {0}".format(ex.message))
            except SystemError as ex:
                logger.exception('Could not fetch alba information. Message: {0}'.format(ex.message), test_name)
                # Do not execute further
                return None

            # Maximum amount of disks that may be lost - preset will determine this
            max_lost_disks = 0
            for preset_name in presets:
                for policy in preset_name['policies']:
                    if policy[1] > max_lost_disks:
                        max_lost_disks = policy[1]

            disk_lost_overview = {}
            total_objects = 0

            for namespace in namespaces:
                for bucket_safety in namespace['bucket_safety']:
                    bucket = bucket_safety['bucket']
                    objects = bucket_safety['count']
                    total_objects += objects
                    applicable_dead_osds = bucket_safety['applicable_dead_osds']
                    # Amount of lost disks at this point
                    bucket[2] = bucket[2] - applicable_dead_osds
                    disk_lost = bucket[0] + bucket[1] - bucket[2]
                    if disk_lost not in disk_lost_overview:
                        disk_lost_overview[disk_lost] = 0
                    disk_lost_overview[disk_lost] += objects

            for disk_lost, objects in disk_lost_overview.iteritems():
                lost = {
                    'measurement': 'disk_lost',
                    'tags': {
                        'backend_name': ab.name,
                        'disk_lost': disk_lost
                    },
                    'fields': {
                        'total_objects': total_objects,
                        'objects': objects
                    }
                }

                points.append(lost)

        if len(points) == 0:
            logger.skip('Found no objects present of the system.', test_name)
        else:
            backends_to_be_repaired = {}
            for result in points:
                # Ignore fully healthy ones
                if result["tags"]["disk_lost"] == 0:
                    continue
                total_objects = result["fields"]["total_objects"]
                objects = result["fields"]["objects"]

                backend_name = result["tags"]["backend_name"]

                if backend_name not in backends_to_be_repaired:
                    backends_to_be_repaired[backend_name] = {"objects": 0, "total_objects": total_objects}
                backends_to_be_repaired[backend_name]["objects"] += objects

            repair_percentage = 0
            if len(backends_to_be_repaired) == 0:
                logger.success("Found no backends with disk lost. All data is safe.")
            else:
                logger.failure("Currently found {0} backend(s) with disk lost.".format(len(backends_to_be_repaired)))
                for backend, disk_lost in backends_to_be_repaired.iteritems():
                    # limit to 4 numbers
                    repair_percentage = float("{0:.4f}".format((float(disk_lost['objects']) /
                                                                float(disk_lost['total_objects'])) * 100))
                    logger.warning("Backend {0}: {1} out of {2} objects have to be repaired."
                                   .format(backend, disk_lost['objects'], disk_lost['total_objects']))
                    logger.warning('Backend {0}: {1}% of the objects have to be repaired'.format(backend,
                                                                                                 repair_percentage),
                                   'repair_percentage_{0}_{1}'.format(backend, repair_percentage))
            # Log if the amount is rising
            cache = CacheHelper.get()
            if cache is None:
                # First run of healthcheck
                logger.success("Object repair will be monitored on incrementations.", 'repair_OK')
            elif repair_percentage == 0:
                # Amount of objects to repair are rising
                logger.success("No objects in objects repair queue", 'repair_OK')
            elif cache["repair_percentage"] > repair_percentage:
                # Amount of objects to repair is descending
                logger.failure("Amount of objects to repair is descending!", 'repair_DESCENDING')
            elif cache["repair_percentage"] < repair_percentage:
                # Amount of objects to repair is rising
                logger.failure("Amount of objects to repair are rising!", 'repair_RISING')
            elif cache["repair_percentage"] == repair_percentage:
                # Amount of objects to repair is the same
                logger.success("Amount of objects to repair are the same!", 'repair_SAME')

            result["repair_percentage"] = repair_percentage
            result["lost_backends"] = backends_to_be_repaired
            CacheHelper.set(result)
        return result

    @staticmethod
    @ExposeToCli('alba', 'test')
    def run(logger):
        AlbaHealthCheck.check_if_proxies_work(logger)
        AlbaHealthCheck.check_asds(logger)
        AlbaHealthCheck.get_disk_safety(logger)
