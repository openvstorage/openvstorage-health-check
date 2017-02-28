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
import time
import datetime
from ovs.extensions.storage.volatilefactory import VolatileFactory


class CacheHelper(object):

    client = VolatileFactory.get_client()
    prefix = 'health-check_'

    @staticmethod
    def add(item, key=None, expire_time=0):
        """
        Store the information to the config management
        :param item: item to set
        :param key: key to use
        :param expire_time: nr of seconds to keep the key. 0 = forever
        :return: Nonzero on success.
        :rtype: int
        """
        _key = CacheHelper._generate_key(key=key)
        timestamp = int(time.time())
        value = {'item': item, 'time_added': timestamp, 'time_updated': timestamp}
        return CacheHelper.client.add(key=_key, value=value, time=expire_time)

    @staticmethod
    def set(item, key=None, expire_time=0):
        """
        Store the information to the config management
        :param item: item to set
        :param key: key to use
        :param expire_time: nr of seconds to keep the key. 0 = forever
        :return: True if successful, False if not
        """
        _key = CacheHelper._generate_key(key=key)
        timestamp = int(time.time())
        value = {'item': item, 'time_added': timestamp, 'time_updated': timestamp}
        CacheHelper.client.set(key=_key, value=value, time=expire_time)
        return CacheHelper.get(key=key) == item

    @staticmethod
    def update(item, key, expire_time=0):
        """
        Store the information to the config management
        :param item: item to update
        :param key: key to update
        :param expire_time: nr of seconds to keep the key. 0 = forever
        :return: True if successful, False if not
        """
        _key = CacheHelper._generate_key(key=key)
        retrieved_value = CacheHelper.get(key=key, raw=True)
        timestamp = int(time.time())
        value = {'item': item, 'time_added': retrieved_value['time_added'], 'time_updated': timestamp}
        CacheHelper.client.set(key=_key, value=value, time=expire_time)
        return CacheHelper.get(key=key) == item

    @staticmethod
    def append(item, key=None, expire_time=0):
        """
        Appends the information to the value
        Supports dicts, lists
        :param item: item to set
        :param key: key to use
        :param expire_time: nr of seconds to keep the key. 0 = forever
        :return: True if successful, False if not
        """
        supported_types = [dict, list]
        retrieved_value = CacheHelper.get(key=key)
        for item_type in supported_types:
            if isinstance(item, item_type) and isinstance(retrieved_value, item_type):
                if item_type == list:
                    return CacheHelper.update(key=key, item=retrieved_value + item, expire_time=expire_time)
                if item_type == dict:
                    item.update(retrieved_value)
                    return CacheHelper.update(key=key, item=item, expire_time=expire_time)
        raise TypeError("{0} is not supported for appending to type {1}.".format(type(item), type(retrieved_value)))

    @staticmethod
    def get(key=None, raw=False, exists_hours=None):
        """
        Gets a value from a specified key
        :param key: key to use
        :param raw: get raw value of key
        :param exists_hours: check if key is already present for x amount of hours
        :return: the value in case it was found else None
        """
        _key = CacheHelper._generate_key(key=key)
        if exists_hours is None:
            if raw:
                return CacheHelper.client.get(_key)
            else:
                return CacheHelper.client.get(_key)['item']
        else:
            value = CacheHelper.client.get(_key)
            return time.time() < (value['time_added'] + datetime.timedelta(hours=int(exists_hours)).total_seconds())

    @staticmethod
    def delete(key=None):
        """
        Deletes the value from a specified key
        :param key: key to use
        :return: True if successful, False if not
        """
        _key = CacheHelper._generate_key(key=key)
        CacheHelper.client.delete(_key)

    @staticmethod
    def _generate_key(key=None):
        """
        Internal method to append the prefix to the key
        :param key: key to use
        :return: the generated key
        """
        if key is None:
            _key = "{0}generic".format(CacheHelper.prefix)
        else:
            _key = "{0}{1}".format(CacheHelper.prefix, key)
        return _key
