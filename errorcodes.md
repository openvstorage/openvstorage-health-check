# Error codes
The json output from the healthcheck returns status codes for every provided message.
These error codes can be used for internal alerting purposes.

## Error code ranges
There are a couple ranges reserved for the OpenvStorage healthcheck. When adding your own tests to the healthcheck,
these ranges should be respected.

| Ranges        | Component     |
| ------------- | ------------- |
| HC0-999       | Healthcheck   |
| FWK0-999      | Framework     |
| ALBA0-999     | Alba          |
| ARA0-999      | Arakoon       |
| VOL0-999      | Volumedriver  |

## Current code overview
 | Error code |                                            Information                                            |                                  Solution                                  | 
 | :--------- | :------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------- | 
 |   HC0000   |                                            Default code                                           |                                Default code                                | 
 |  VOL0000   |                                         No vPools present                                         |                          Add vPools to this node                           | 
 |  VOL0001   |                                       vPool not on this node                                      |                         Extend vPool to this node                          | 
 |  VOL1001   |                            Volumedriver does not recognize this volume                            |                Verify whether this volume is still present                 | 
 |  VOL1002   | Volumedriver can't retrieve information about the volume. This indicates the volume might be down |                   Verify whether this volume is running                    | 
 |  VOL1003   |                       Volumedriver is not responding to calls (fast enough)                       |                Verify whether this volumedriver is running                 | 
 |  VOL1004   |      Volume is in the 'halted' state. The volume could still be failing over to another node      | A possible solution is restarting this volume (after the failover is done) | 
 |  VOL1011   |                           The volumes DTL state which is not recognized                           |                     Report this issue to OpenvStorage                      | 
 |  VOL1012   |                               The volumes DTL state is still syncing                              |                        Wait for the sync to finish                         | 
 |  VOL1013   |                                The volumes DTL should be configured                               |                     Configure the DTL for this volume                      | 
 |  VOL1014   |                                    The volumes DTL is degraded                                    |                  Perform the DTL checkup for this volume                   |

