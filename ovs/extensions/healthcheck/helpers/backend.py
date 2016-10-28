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
