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

from ovs.extensions.storage.exceptions import KeyNotFoundException
from ovs.extensions.storage.persistentfactory import PersistentFactory


class CacheHelper(object):

    client = PersistentFactory.get_client()
    prefix = 'health-check_'

    @staticmethod
    def set(item, key=None):
        """
        Store the information to the config management
        :param item: item to set
        :param key: key to use
        :return: True if successful, False if not
        """
        key = CacheHelper._generate_key(key=key)
        return CacheHelper.client.set(key=key, value=item)

    @staticmethod
    def append(item, key=None):
        """
        Appends the information to the value
        Supports dicts, lists
        :param item: item to set
        :param key: key to use
        :return: True if successful, False if not
        """
        supported_types = [dict, list]
        retrieved_value = CacheHelper.get(key=key)
        for item_type in supported_types:
            if isinstance(item, item_type) and isinstance(retrieved_value, item_type):
                if item_type == list:
                    return CacheHelper.set(key=key, item=retrieved_value + item)
                if item_type == dict:
                    item.update(retrieved_value)
                    return CacheHelper.set(key=key, item=item)
        raise TypeError("{0} is not supported for appending to type {1}.".format(type(item), type(retrieved_value)))

    @staticmethod
    def get(key=None):
        """
        Gets a value from a specified key
        :param key: key to use
        :return: the value in case it was found else None
        """
        key = CacheHelper._generate_key(key=key)
        try:
            return CacheHelper.client.get(key)
        except KeyNotFoundException:
            return None

    @staticmethod
    def delete(key=None):
        """
        Deletes the value from a specified key
        :param key: key to use
        :return: True if successful, False if not
        """
        key = CacheHelper._generate_key(key=key)
        try:
            CacheHelper.client.delete(key)
            return True
        except KeyNotFoundException:
            return False

    @staticmethod
    def _generate_key(key=None):
        """
        Internal method to append the prefix to the key
        :param key: key to use
        :return: the generated key
        """
        if key is None:
            key = "{0}generic".format(CacheHelper.prefix)
        else:
            key = "{0}{1}".format(CacheHelper.prefix, key)
        return key

    @staticmethod
    def _test_type_handling():
        """
        Test if CacheHelper can cope with all primitive types
        :return:
        """
        testers = {
            'integer': 1,
            'double': 2.0,
            'string': "test",
            'literal': 'test',
            'dict': {"test": "test"},
            'list': [1, 2],
            'set': {1, 2}
        }

        for key, value in testers.iteritems():
            try:
                CacheHelper.set(value)
            except Exception as e:
                print "Could not set {0} type. Got {1}".format(key, e.message)
            try:
                CacheHelper.append(value)
                print "Appended {0}".format(key)
            except Exception as e:
                print "Could not append {0} type. Got {1}".format(key, e.message)
            try:
                data = CacheHelper.get()
                print data
            except Exception as e:
                print "Could not get {0} type. Got {1}".format(key, e.message)
        CacheHelper.delete()
