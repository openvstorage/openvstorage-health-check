# Copyright (C) 2018 iNuron NV
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
Generic system module, executing statements on local node
"""

import os
from subprocess import check_output
from ovs_extensions.generic.sshclient import SSHClient


class System(object):
    """
    Generic helper class
    """
    def __init__(self):
        """
        Dummy init method
        """
        raise RuntimeError('System is a static class')

    @classmethod
    def ports_in_use(cls, client=None):
        """
        Returns the ports in use
        :param client: Remote client on which to retrieve the ports in use
        :type client: SSHClient

        :return: Ports in use
        :rtype: list
        """
        cmd = "netstat -ln | sed 1,2d | sed 's/\s\s*/ /g' | cut -d ' ' -f 4 | cut -d ':' -f 2"
        if client is None:
            output = check_output(cmd, shell=True)
        else:
            output = client.run(cmd, allow_insecure=True)
        for found_port in output.splitlines():
            if found_port.isdigit():
                yield int(found_port.strip())

    @classmethod
    def get_free_ports(cls, selected_range, exclude=None, amount=1, client=None):
        """
        Return requested amount of free ports not currently in use and not within excluded range
        :param selected_range: The range in which the amount of free ports need to be fetched
                               e.g. '2000-2010' or '5000-6000, 8000-8999' ; note single port extends to [port -> 65535]
        :type selected_range: list
        :param exclude: List of port numbers which should be excluded from the calculation
        :type exclude: list
        :param amount: Amount of free ports requested
                       if amount == 0: return all the available ports within the requested range
        :type amount: int
        :param client: SSHClient to node
        :type client: ovs_extensions.generic.sshclient.SSHClient
        :raises ValueError: If requested amount of free ports could not be found
        :return: Sorted incrementing list of the requested amount of free ports
        :rtype: list
        """
        unittest_mode = os.environ.get('RUNNING_UNITTESTS') == 'True'
        requested_range = []
        for port_range in selected_range:
            if isinstance(port_range, list):
                current_range = [port_range[0], port_range[1]]
            else:
                current_range = [port_range, 65535]
            if 0 <= current_range[0] <= 1024:
                current_range = [1025, current_range[1]]
            requested_range += range(current_range[0], current_range[1] + 1)

        free_ports = []
        if exclude is None:
            exclude = []
        exclude_list = list(exclude)

        if unittest_mode is True:
            ports_in_use = []
        else:
            ports_in_use = cls.ports_in_use(client)
        exclude_list += ports_in_use

        if unittest_mode is True:
            start_end = [0, 0]
        else:
            cmd = 'cat /proc/sys/net/ipv4/ip_local_port_range'
            if client is None:
                output = check_output(cmd, shell=True)
            else:
                output = client.run(cmd.split())
            start_end = map(int, output.split())
        ephemeral_port_range = xrange(min(start_end), max(start_end))
        for possible_free_port in requested_range:
            if possible_free_port not in ephemeral_port_range and possible_free_port not in exclude_list:
                free_ports.append(possible_free_port)
                if len(free_ports) == amount:
                    return free_ports
        if amount == 0:
            return free_ports
        raise ValueError('Unable to find the requested amount of free ports')
