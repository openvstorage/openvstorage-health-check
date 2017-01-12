@staticmethod
def get_disk_safety_buckets_mock(logger):
    return {'mybackend02': {'1,2': {'max_disk_safety': 2, 'current_disk_safety':
        {2: [{'namespace': 'b4eef27e-ef54-4fe8-8658-cdfbda7ceae4_000000065', 'amount_in_bucket': 100}]}}},
            'mybackend':
                {'1,2': {'max_disk_safety': 2, 'current_disk_safety':
                    {1: [{'namespace': 'b4eef27e-ef54-4fe8-8658-cdfbda7ceae4_000000065',
                          'amount_in_bucket': 100}]}}},
            'mybackend-global': {'1,2': {'max_disk_safety': 2, 'current_disk_safety':
                {0: [{'namespace': 'e88c88c9-632c-4975-b39f-e9993e352560', 'amount_in_bucket': 100}]}},
                                 '1,3': {'max_disk_safety': 3, 'current_disk_safety':
                                     {0: [{'namespace': 'e88c88c9-632c-4975-b39f-e9993e352560',
                                           'amount_in_bucket': 100}]}}
                                 },
            }