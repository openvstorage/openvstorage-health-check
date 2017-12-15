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
import shlex
import socket
import subprocess


class NetworkHelper(object):

    @staticmethod
    def check_port_connection(port_number, ip):
        """
        Checks the port connection on a IP address
        :param port_number: Port number of a service that is running on the local machine. (Public or loopback)
        :type port_number: int
        :param ip: IP address to try
        :type ip: str
        :return: True if the port is available; False if the port is NOT available
        :rtype: bool
        """
        # check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return sock.connect_ex((ip, int(port_number))) == 0

    @staticmethod
    def check_if_dns_resolves(fqdn='google.com'):
        """
        Checks if DNS resolving works on a local machine
        :param fqdn: the absolute pathname of the file
        :type fqdn: str
        :return: True if the DNS resolving works; False it doesn't work
        :rtype: bool
        """
        try:
            socket.gethostbyname(fqdn)
            return True
        except Exception:
            return False
