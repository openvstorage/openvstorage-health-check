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

from ovs.dal.lists.disklist import DiskList
from ovs.extensions.healthcheck.helpers.storagerouter import StoragerouterHelper
from ovs.dal.lists.diskpartitionlist import DiskPartitionList


class DiskHelper(object):
    """
    DiskHelper class
    """

    def __init__(self):
        pass

    @staticmethod
    def get_diskpartitions_by_guid(diskguid):
        """
        Fetch disk partitions by disk guid

        :param diskguid: guid of disk object
        :type diskguid: str
        :return: list of DiskPartition Objects
        :rtype: list (ovs.dal.hybrids.diskpartition.diskpartition)
        """

        return [dp for dp in DiskPartitionList.get_partitions() if dp.disk_guid == diskguid]

    @staticmethod
    def get_roles_from_disks(storagerouter_ip=None):
        """
        Fetch disk roles from all disks with optional storagerouter_ip

        :param storagerouter_ip: ip address of a storage router
        :type storagerouter_ip: str
        :return: list of lists with roles
        :rtype: list > list
        """
        if not storagerouter_ip:
            return [partition.roles for disk in DiskList.get_disks() for partition in disk.partitions]
        else:
            storagerouter_guid = StoragerouterHelper.get_storagerouter_guid_by_ip(storagerouter_ip)
            return [partition.roles for disk in DiskList.get_disks()
                    if disk.storagerouter_guid == storagerouter_guid for partition in disk.partitions]
