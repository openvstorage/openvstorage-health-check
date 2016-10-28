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

from ovs.log.log_handler import LogHandler
from ovs.dal.lists.backendlist import BackendList
from ovs.dal.hybrids.albabackend import AlbaBackend
from ovs.dal.lists.backendtypelist import BackendTypeList
from ovs.dal.lists.albabackendlist import AlbaBackendList
from ovs.extensions.healthcheck.helpers.exceptions import PresetNotFoundError, AlbaBackendNotFoundError


class BackendHelper(object):
    """
    BackendHelper class
    """
    LOGGER = LogHandler.get(source='helpers', name="ci_backend")

    def __init__(self):
        pass

    @staticmethod
    def get_backend_by_name(backend_name):
        """
        Fetch backend object by name

        :param backend_name: name of a backend
        :type backend_name: str
        :return: Backend object
        :rtype: ovs.dal.hybrids.backend.Backend
        """

        return BackendList.get_by_name(backend_name)

    @staticmethod
    def get_backend_status_by_name(backend_name):
        """
        Fetch the backendstatus of a named backend

        :param backend_name: name of a backend
        :type backend_name: str
        :return: backend status
        :rtype: str
        """

        return BackendList.get_by_name(backend_name).status

    @staticmethod
    def get_backendtype_guid_by_code(backendtype_code):
        """
        Get a backend type guid by a backend code

        :param backendtype_code: type name of a backend
        :type backendtype_code: str
        :return: backendtype_guid
        :rtype: str
        """

        return BackendTypeList.get_backend_type_by_code(backendtype_code).guid

    @staticmethod
    def get_albabackend_by_guid(albabackend_guid):
        """
        Get a albabackend by albabackend guid

        :param albabackend_guid: albabackend guid
        :type albabackend_guid: str
        :return: alba backend object
        :rtype: ovs.dal.hybrids.albabackend
        """

        return AlbaBackend(albabackend_guid)

    @staticmethod
    def get_albabackend_by_name(albabackend_name):
        """
        Get a Albabackend by name

        :param albabackend_name: albabackend name
        :type albabackend_name: str
        :return: alba backend object
        :rtype: ovs.dal.hybrids.albabackend
        """

        try:
            return [alba_backend for alba_backend in AlbaBackendList.get_albabackends()
                    if alba_backend.name == albabackend_name][0]
        except IndexError:
            error_msg = "No Alba backend found with name: {0}".format(albabackend_name)
            BackendHelper.LOGGER.error(error_msg)
            raise NameError(error_msg)

    @staticmethod
    def get_asd_safety(albabackend_guid, asd_id, api):
        """
        Request the calculation of the disk safety

        :param albabackend_guid: guid of the alba backend
        :type albabackend_guid: str
        :param asd_id: id of the asd
        :type asd_id: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        :return: task id of celery
        :rtype: str
        """
        params = {'asd_id': asd_id}
        return api.get('alba/backends/{0}/calculate_safety'.format(albabackend_guid), params=params)

    @staticmethod
    def _map_alba_nodes(api):
        """
        Will map the alba_node_id with its guid counterpart and return the map dict

        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        """
        mapping = {}

        options = {
            'contents': 'node_id,_relations',
        }
        response = api.get(
            api='alba/nodes',
            params=options
        )
        for node in response['data']:
            mapping[node['node_id']] = node['guid']

        return mapping

    @staticmethod
    def get_backend_local_stack(albabackend_name, api):
        """
        Fetches the local stack property of a backend

        :param albabackend_name: backend name
        :type albabackend_name: str
        :param api: specify a valid api connection to the setup
        :type api: ci.helpers.api.OVSClient
        """
        options = {
            'contents': 'local_stack',
        }
        return api.get(api='/alba/backends/{0}/'.format(BackendHelper.get_alba_backend_guid_by_name(albabackend_name)),
                       params={'queryparams': options}
                       )

    @staticmethod
    def get_albabackends():
        """
        Fetches all the alba backends on the cluster

        :return: alba backends
        :rtype: list
        """

        return AlbaBackendList.get_albabackends()

    @staticmethod
    def get_preset_by_albabackend(preset_name, albabackend_name):
        """
        Fetches preset by albabackend_guid

        :param preset_name: name of a existing preset
        :type preset_name: str
        :param albabackend_name: name of a existing alba backend
        :type albabackend_name: str
        :return: alba backends
        :rtype: list
        """

        try:
            return [preset for preset in BackendList.get_by_name(albabackend_name).alba_backend.presets
                    if preset['name'] == preset_name][0]
        except IndexError:
            raise PresetNotFoundError("Preset `{0}` on alba backend `{1}` was not found"
                                      .format(preset_name, albabackend_name))
        except AttributeError:
            raise AlbaBackendNotFoundError("Albabackend with name `{0}` does not exist".format(albabackend_name))
