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
import socket


class NetworkHelper(object):

    @staticmethod
    def check_port_connection(port_number, ip):
        """
        Checks the port connection on a IP address
        :param port_number: Port number of a service that is running on the local machine. (Public or loopback)
        :type port_number: int
        :param ip: ip address to try
        :type ip: str
        :return: True if the port is available; False if the port is NOT available
        :rtype: bool
        """
        # check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((ip, int(port_number)))
        if result == 0:
            return True
        else:
            # Check if it might be referencing to the wrong ip
            if ip not in NetworkHelper._get_local_ip_addresses():
                return False
            result = sock.connect_ex(('127.0.0.1', int(port_number)))
            if result == 0:
                return True
            else:
                return False

    @staticmethod
    def _get_local_ip_addresses():
        """
        Fetches all ips adresses configured on this node
        :return: all local ip adresses
        :rtype: list
        """
        cmd = "ip a | grep 'inet ' | sed 's/\s\s*/ /g' | cut -d ' ' -f 3 | cut -d '/' -f 1 "
        if "|" in cmd:
            cmd_parts = cmd.split('|')
        else:
            cmd_parts = [cmd]

        counter = 0
        processes = {}
        for cmd_part in cmd_parts:
            cmd_part = cmd_part.strip()
            if counter == 0:
                # First command uses no stdin from another Popen object
                processes[counter] = subprocess.Popen(shlex.split(cmd_part), stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                # All other commands use the previous Popen objects output and pipe it to theirs
                processes[counter] = subprocess.Popen(shlex.split(cmd_part), stdin=processes[counter - 1].stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            counter += 1
        output, err = processes[counter - 1].communicate()
        exit_code = processes[0].wait()
        if exit_code != 0 or err:
            raise subprocess.CalledProcessError("Command {0} exited with {1} and message {2}".format(cmd, exit_code, err), cmd)

        return output.split('\n')

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
