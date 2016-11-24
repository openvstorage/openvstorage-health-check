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
from ovs.dal.hybrids.service import Service
from ovs.dal.lists.servicelist import ServiceList


class ServiceHelper(object):
    """
    A Servicehelper class
    """

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
