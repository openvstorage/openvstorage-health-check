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
from ovs.dal.datalist import DataList
from ovs.dal.hybrids.service import Service
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.dal.lists.servicelist import ServiceList
from ovs.extensions.generic.system import System


class ServiceHelper(object):
    """
    A service helper class
    """

    LOCAL_SR = System.get_my_storagerouter()

    def __init__(self):
        pass

    @staticmethod
    def get_services():
        """
        Fetch all services

        :return:
        """
        return ServiceList.get_services()

    @staticmethod
    def get_service(service_guid):
        """
        Fetches a service by guid
        :param service_guid: guid of the service
        :type service_guid: str
        :return: Service object
        :rtype: ovs.dal.hybrids.service.service
        """
        return Service(service_guid)

    @staticmethod
    def get_local_services():
        """
        Fetches all services that run on this node
        :return: list of all services that run on this node
        :rtype: ovs.dal.lists.datalist.DataList
        """
        return DataList(Service, {'type': DataList.where_operator.AND,
                                  'items': [('storagerouter_guid', DataList.operator.EQUALS, ServiceHelper.LOCAL_SR.guid)]})

    @staticmethod
    def get_local_arakoon_services():
        """
        Fetches all arakoon services that run on this node
        :return: list of all arakoon services that run on this node
        :rtype: ovs.dal.lists.datalist.DataList
        """
        return DataList(Service, {'type': DataList.where_operator.AND,
                                  'items': [('storagerouter_guid', DataList.operator.EQUALS, ServiceHelper.LOCAL_SR.guid),
                                            ('type.name', DataList.operator.IN, [ServiceType.SERVICE_TYPES.ARAKOON,
                                                                                 ServiceType.SERVICE_TYPES.ALBA_MGR,
                                                                                 ServiceType.SERVICE_TYPES.NS_MGR])]})

    @staticmethod
    def get_local_abm_services():
        """
        Fetches all arakoon services that run on this node
        :return: list of all arakoon services that run on this node
        :rtype: ovs.dal.lists.datalist.DataList
        """
        return DataList(Service, {'type': DataList.where_operator.AND,
                                  'items': [
                                      ('storagerouter_guid', DataList.operator.EQUALS, ServiceHelper.LOCAL_SR.guid),
                                      ('type.name', DataList.operator.EQUALS, ServiceType.SERVICE_TYPES.ALBA_MGR)
                                  ]})

    @staticmethod
    def get_local_voldr_services():
        """
        Fetches all alba proxy services that run on this node
        :return: list of all alba proxy services that run on this node
        :rtype: ovs.dal.lists.datalist.DataList
        """
        return DataList(Service, {'type': DataList.where_operator.AND,
                                  'items': [
                                      ('storagerouter_guid', DataList.operator.EQUALS, ServiceHelper.LOCAL_SR.guid),
                                      ('type.name', DataList.operator.EQUALS, ServiceType.SERVICE_TYPES.MD_SERVER)
                                  ]})

    @staticmethod
    def get_local_proxy_services():
        """
        Fetches all alba proxy services that run on this node
        :return: list of all alba proxy services that run on this node
        :rtype: ovs.dal.lists.datalist.DataList
        """
        return DataList(Service, {'type': DataList.where_operator.AND,
                                  'items': [
                                      ('storagerouter_guid', DataList.operator.EQUALS, ServiceHelper.LOCAL_SR.guid),
                                      ('type.name', DataList.operator.EQUALS, ServiceType.SERVICE_TYPES.ALBA_PROXY)
                                  ]})
