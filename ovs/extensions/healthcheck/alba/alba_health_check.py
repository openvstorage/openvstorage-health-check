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
import ast
import uuid
import time
import hashlib
import subprocess
from ovs.extensions.generic.system import System
from ovs.extensions.plugins.albacli import AlbaCLI
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.healthcheck.decorators import ExposeToCli
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.healthcheck.helpers.cache import CacheHelper
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.alba_node import AlbaNodeHelper
from ovs.extensions.healthcheck.helpers.backend import BackendHelper
from ovs.extensions.healthcheck.helpers.storagedriver import StoragedriverHelper
from ovs.extensions.healthcheck.helpers.configuration import ConfigurationManager, ConfigurationProduct
from ovs.extensions.healthcheck.helpers.exceptions import ObjectNotFoundException, ConnectionFailedException, \
    DiskNotFoundException, ConfigNotMatchedException
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult


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
                logger.failure("Error during fetch of alba backend '{0}': {1}".format(abl.name, e), 'check_alba', False)

        # give a precheck result for fetching the backend data
        if errors_found == 0:
            logger.success("No problems occured when fetching alba backends!", 'fetch_alba_backends')
        else:
            logger.failure("Error during fetch of alba backend '{0}': {1}".format(abl.name, e), 'fetch_alba_backends')

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

        # try put/get/verify on all available proxies on the local node
        for service in ServiceHelper.get_services():
            if service.storagerouter_guid == AlbaHealthCheck.MACHINE_DETAILS.guid:
                if service.type.name == ServiceType.SERVICE_TYPES.ALBA_PROXY:
                    logger.info("Checking ALBA proxy '{0}': ".format(service.name), 'check_alba')
                    storagedriver_id = "{0}{1}".format(service.name.split('_')[1], AlbaHealthCheck.MACHINE_ID)
                    ip = StoragedriverHelper.get_by_storagedriver_id(storagedriver_id).storage_ip

                    # Encapsulating try to determine test output
                    try:
                        # Determine what to what backend the proxy is connected
                        proxy_client_cfg = AlbaCLI.run('proxy-client-cfg', host=ip, port=service.ports[0])

                        # Check if proxy config is correctly setup
                        client_config = re.match('^client_cfg:\n{ cluster_id = "(?P<cluster_id>[0-9a-zA-Z_-]+)";.*',
                                                 proxy_client_cfg)

                        if client_config is None:
                            raise ConfigNotMatchedException('Proxy config does not have ''the correct format on node {0}'
                                                            ' with port {1}.'.format(ip, service.ports[0]))

                        # Fetch arakoon information
                        abm_name = client_config.groupdict()['cluster_id']
                        abm_config = ConfigurationManager.get_config_file_path(arakoon_name=abm_name,
                                                                               product=ConfigurationProduct.ARAKOON)

                        # Determine presets / backend
                        presets = AlbaCLI.run('list-presets', config=abm_config, to_json=True)

                        for preset in presets:
                            # If preset is not in use, test will fail so add a skip
                            if preset['in_use'] is False:
                                logger.skip("Preset '{0}' is not in use and will not be checked".format(preset['name']),
                                            "proxy_{0}".format(service.name))
                                continue
                            # Encapsulation try for cleanup
                            try:
                                # Generate new namespace name using the preset
                                namespace_key = 'ovs-healthcheck-ns-{0}'.format(preset.get('name'))
                                object_key = 'ovs-healthcheck-obj-{0}'.format(str(uuid.uuid4()))

                                # Create namespace
                                AlbaCLI.run('proxy-create-namespace', host=ip, port=service.ports[0],
                                            extra_params=[namespace_key, preset['name']])
                                # Fetch namespace
                                AlbaCLI.run('show-namespace', config=abm_config, to_json=True, extra_params=[namespace_key])
                                logger.success("Namespace successfully created on proxy '{0}' with preset '{1}'!".format(service.name,preset.get('name')),
                                               '{0}_preset_{1}_create_namespace'.format(service.name, preset.get('name')))

                                # Put test object to given dir
                                with open(AlbaHealthCheck.TEMP_FILE_LOC, 'wb') as fout:
                                    fout.write(os.urandom(AlbaHealthCheck.TEMP_FILE_SIZE))

                                # try to put object
                                AlbaCLI.run('proxy-upload-object', host=ip, port=service.ports[0],
                                            extra_params=[namespace_key, AlbaHealthCheck.TEMP_FILE_LOC, object_key])
                                # download object
                                AlbaCLI.run('download-object', config=abm_config,
                                            extra_params=[namespace_key, object_key,AlbaHealthCheck.TEMP_FILE_FETCHED_LOC])
                                # check if files exists - issue #57
                                if os.path.isfile(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC) \
                                        and os.path.isfile(AlbaHealthCheck.TEMP_FILE_LOC):
                                    hash_original = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_LOC, 'rb').read()).hexdigest()
                                    hash_fetched = hashlib.md5(open(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC, 'rb').read()).hexdigest()

                                    if hash_original == hash_fetched:
                                        logger.success("Creation of a object in namespace '{0}' on proxy '{1}' "
                                                       "with preset '{2}' succeeded!".format(namespace_key,service.name,preset.get('name')),
                                                       '{0}_preset_{1}_create_object'.format(service.name, preset.get('name')))
                                    else:
                                        logger.failure("Creation of a object '{0}' in namespace '{1}' on proxy"
                                                       " '{2}' with preset '{3}' failed!".format(object_key,namespace_key,service.name,preset.get('name')),
                                                       '{0}_preset_{1}_create_object'.format(service.name, preset.get('name')))
                                else:
                                    # creation of object failed
                                    raise ObjectNotFoundException(ValueError('Creation of object has failed'))

                            except RuntimeError as e:
                                # put was not successfully executed, so get return success = False
                                logger.failure("Creating/fetching namespace ""'{0}' with preset '{1}' on proxy '{2}' "
                                               "failed! With error {3}".format(namespace_key, preset.get('name'), service.name, e),
                                               '{0}_preset_{1}_create_namespace'.format(service.name, preset.get('name')))

                            except ObjectNotFoundException as e:
                                amount_of_presets_not_working.append(preset.get('name'))
                                logger.failure("Failed to put object on namespace '{0}' failed on proxy '{1}' "
                                               "with preset '{2}' With error {3}".format(namespace_key, service.name, preset.get('name'), e),
                                               '{0}_preset_{1}_create_object'.format(service.name, preset.get('name')))
                            finally:
                                # Delete the created namespace and preset
                                try:
                                    # Remove object first
                                    logger.info("Deleting created object '{0}' on '{1}'.".format(object_key, namespace_key))
                                    AlbaCLI.run('proxy-delete-object', host=ip, port=service.ports[0], extra_params=[namespace_key, object_key])
                                    subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_LOC)], stdout=fnull, stderr=subprocess.STDOUT)
                                    subprocess.call(['rm', str(AlbaHealthCheck.TEMP_FILE_FETCHED_LOC)], stdout=fnull, stderr=subprocess.STDOUT)
                                    # @todo uncomment when the issue has been that blocks uploads after namespaces are created
                                    # # Remove namespace afterwards
                                    # logger.info("Deleting namespace '{0}'.".format(namespace_key))
                                    # AlbaCLI.run('proxy-delete-namespace', host=ip, port=service.ports[0], extra_params=[namespace_key])
                                except subprocess.CalledProcessError as e:
                                    raise

                    except subprocess.CalledProcessError as e:
                        # this should stay for the deletion of the remaining files
                        amount_of_presets_not_working.append(service.name)
                        logger.failure("Proxy '{0}' has some problems. Got '{1}' as error".format(service.name, e), 'proxy_{0}'.format(service.name))

                    except ConfigNotMatchedException as e:
                        amount_of_presets_not_working.append(service.name)
                        logger.failure("Proxy '{0}' has some problems. Got '{1}' as error".format(service.name, e),'proxy_{0}'.format(service.name))

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
                            # put object but ignore crap for a moment
                            AlbaCLI.run('asd-set', host=ip_address, port=str(disk.get('port')),
                                        long_id=disk.get('asd_id'), extra_params=[key, value])

                            # get object
                            try:
                                g = AlbaCLI.run('asd-multi-get', host=ip_address, port=str(disk.get('port')),
                                                long_id=disk.get('asd_id'), extra_params=[key])
                            except Exception:
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
                                AlbaCLI.run('asd-delete', host=ip_address, port=str(disk.get('port')),
                                            long_id=disk.get('asd_id'), extra_params=[key])
                            except subprocess.CalledProcessError:
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
    @ExposeToCli('alba', 'backend-test')
    def check_alba(logger):
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

                logger.info("Checking the ALBA proxies ...", 'check_alba_proxies')
                AlbaHealthCheck.check_if_proxies_work(logger)

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
                                                   " ALL disks are working fine!".format(backend.get('name')),
                                                   'alba_backend_{0}'.format(backend.get('name')))
                                else:
                                    logger.warning("Alba backend '{0}' should be "
                                                   "AVAILABLE FOR vPOOL USE with {1} disks,"
                                                   " BUT there are {2} defective disks: {3}".format(backend.get('name'),
                                                                                                    len(workingdisks),
                                                                                                    len(defectivedisks),
                                                                                                    ', '
                                                                                                    .join(defectivedisks
                                                                                                          )),
                                                   'alba_backend_{0}'.format(backend.get('name'), len(defectivedisks)))
                            else:
                                if len(workingdisks) == 0 and len(defectivedisks) == 0:
                                    logger.skip("Alba backend '{0}' is NOT available for vPool use, there are no"
                                                " disks assigned to this backend!".format(backend.get('name')),
                                                'alba_backend_{0}'.format(backend.get('name')))
                                else:
                                    logger.failure("Alba backend '{0}' is NOT available for vPool use, preset"
                                                   " requirements NOT SATISFIED! There are {1} working disks AND {2}"
                                                   " defective disks!".format(backend.get('name'), len(workingdisks),
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

            config = "arakoon://config/ovs/arakoon/{0}/config?ini=%2Fopt%2FOpenvStorage%2Fconfig%2Farakoon_cacc.ini".format(service_name)

            # Fetch alba info
            try:
                try:
                    namespaces = AlbaCLI.run('show-namespaces', config=config, to_json=True)[1]
                except Exception as ex:
                    raise SystemError("Could not execute 'alba show-namespaces'. Got {0}".format(ex.message))
                try:
                    presets = AlbaCLI.run('list-presets', config=config, to_json=True)
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
            disk_safety_overview = {}
            bucket_overview = {}
            max_disk_safety = 0
            total_objects = 0

            for namespace in namespaces:
                statistics = namespace['statistics']
                bucket_counts = statistics['bucket_count']
                preset_name = namespace['namespace']['preset_name']
                for bucket_count in bucket_counts:
                    bucket, objects = bucket_count
                    total_objects += objects
                    # Amount of lost disks at this point
                    disk_lost = bucket[0] + bucket[1] - bucket[2]
                    disk_safety = bucket[1] - disk_lost
                    if disk_safety > max_disk_safety:
                        max_disk_safety = disk_safety

                    if preset_name not in bucket_overview:
                        bucket_overview[preset_name] = {}

                    if str(bucket) not in bucket_overview[preset_name]:
                        bucket_overview[preset_name][str(bucket)] = {'objects': 0, 'disk_safety': 0}
                    if disk_lost not in disk_lost_overview:
                        disk_lost_overview[disk_lost] = 0
                    if disk_safety not in disk_safety_overview:
                        disk_safety_overview[disk_safety] = 0
                    disk_lost_overview[disk_lost] += objects
                    disk_safety_overview[disk_safety] += objects
                    bucket_overview[preset_name][str(bucket)]['objects'] += objects
                    bucket_overview[preset_name][str(bucket)]['disk_safety'] = disk_safety

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
            total_objects = 0
            object_to_be_repaired = 0
            current_disks_lost = 0
            for result in points:
                total_objects = result["fields"]["total_objects"]
                # Ignore fully healthy ones
                if result["tags"]["disk_lost"] != 0:
                    current_disks_lost = result["tags"]["disk_lost"]
                    object_to_be_repaired = result["fields"]["objects"]
            repair_percentage = object_to_be_repaired / total_objects
            if current_disks_lost == 0:
                logger.success("Found no losts disks. All data is safe.")
            else:
                logger.failure("Currently found {0} disks that are lost.".format(current_disks_lost))
            logger.info("{0} out of {1} have to be repaired.".format(object_to_be_repaired, total_objects))
            logger.info('{0}% of the objects have to be repaired'.format(repair_percentage))
            # Log if the amount is rising
            cache = CacheHelper.get()
            repair_rising = None
            if cache is None:
                # First run of healthcheck
                logger.info("Object repair will be monitored on incrementations.")
            elif cache["repair_percentage"] < repair_percentage:
                # Amount of objects to repair are rising
                repair_rising = True
                logger.failure("Amount of objects to repair are rising!")
            else:
                repair_rising = False
                logger.success("Amount of objects to repair are descending or the same!")

            # Recap for Ops checkMK
            logger.custom('Recap of disk-safety: {0}% of the objects have to be repaired. {1} of lost disks and number of objects to repair are {2}.'
                          .format(repair_percentage, current_disks_lost, 'rising' if repair_rising is True else 'descending or the same'),
                          test_name, " ".join([str(repair_percentage), 'SUCCESS' if current_disks_lost == 0 else 'FAILURE',
                                               'FAILURE' if repair_rising is True else 'SUCCESS']))
            result["repair_percentage"] = repair_percentage
            result["lost_disks"] = current_disks_lost
            CacheHelper.set(result)
            return result
        return result

    @staticmethod
    @ExposeToCli('alba', 'test')
    def run(logger):
        AlbaHealthCheck.check_alba(logger)
        AlbaHealthCheck.get_disk_safety(logger)
