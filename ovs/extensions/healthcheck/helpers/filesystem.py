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
import os
import grp
from pwd import getpwuid


class FilesystemHelper(object):

    @staticmethod
    def get_owner_of_file(filename):
        """
        Gets the OWNER of a certain file
        :param filename: the absolute pathname of the file
        :type filename: str
        :return: owner name of a file
        :rtype: str
        """
        return getpwuid(os.stat(filename).st_uid).pw_name

    @staticmethod
    def get_group_of_file(filename):
        """
        Gets the GROUP of a certain file
        :param filename: the absolute pathname of the file
        :type filename: str
        :return: group of a file
        :rtype: str
        """
        return grp.getgrgid(os.stat(filename).st_gid).gr_name

    @staticmethod
    def check_rights_of_file(filename, rights):
        """
        Checks if there are RIGHTS mistakes in a certain file
        :param filename: the absolute pathname of the file
        :type filename: str
        :param rights: the correct rights that the file needs to have
        :type rights: str
        :return: True if the rights are correct; False if they are wrong
        :rtype: bool
        """
        # fetch file to start compare
        st = os.stat(filename)
        return oct(st.st_mode)[-3:] == str(rights)
