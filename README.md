# RabiBridge

[![fury](https://badge.fury.io/py/RabiBridge.svg)](https://badge.fury.io/py/RabiBridge)
[![licence](https://img.shields.io/github/license/GoodManWEN/RabiBridge)](https://github.com/GoodManWEN/RabiBridge/blob/master/LICENSE)
[![pyversions](https://img.shields.io/pypi/pyversions/RabiBridge.svg)](https://pypi.org/project/RabiBridge/)
[![Publish](https://github.com/GoodManWEN/RabiBridge/workflows/Publish/badge.svg)](https://github.com/GoodManWEN/RabiBridge/actions?query=workflow:Publish)
[![Docs](https://github.com/GoodManWEN/RabiBridge/workflows/Docs/badge.svg)](https://github.com/GoodManWEN/RabiBridge/actions?query=workflow:Docs)

This is a lightweight RPC framework based on RabbitMQ, designed to achieve network service decoupling and traffic peak shaving and protect your backend service. Applicable to FastAPI / aiohttp and other asynchronous frameworks

## Catalogue
- [Feature](#Feature)
- [Dependency](#Dependency)
- [Quick Start](#Quick-Start)
- [Documentation](#Documentation)
- [Configuration](#Configuration)
- [Performance](#Performance)
- [Licence](#Licence)

## Feature
- Based on message queues
- Low Latency
- Distributed services and horizontal scaling
- Fully asynchronous framework
- Connections ensured by tls
- Stable under extensive stress testing

## Dependency
- Python 3.x
- RabbitMQ

## Installation

```
pip install RabiBridge
```

## Quick Start

1. First start your rabbitmq service
```sh
docker run -d \
  --name rabbitmq \
  -e RABBITMQ_DEFAULT_USER=admin \
  -e RABBITMQ_DEFAULT_PASS=123456 \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:management
```

2. Import `RabiBridge`, create a function to call, register and run serve.
```python
# -*- coding: utf-8 -*-
# File name: service.py
import asyncio
from rabibridge import RMQServer, register_call

@register_call(timeout=10)
async def fibonacci(n: int):
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    return await fibonacci(n-1) + await fibonacci(n-2)

async def main():
    bridge = RMQServer(host="localhost", port=5672, username="admin", password="123456")
    bridge.load_services(globals()) # Automatic capture procedure of the main namespace
    async with bridge:
        await bridge.run_serve()

asyncio.run(main())
```

3. Call remotely.
```python
# -*- coding: utf-8 -*-
# File name: client.py
import asyncio
from rabibridge import RMQClient

async def main():
    async with RMQClient(host="localhost", port=5672, username="admin", password="123456") as bridge:
        err_code, result = await bridge.remote_call('fibonacci', (10, ))
        print(f"Result is {result}")
        # >>> Result is 55

asyncio.run(main())
```


## Documentation

For the detailed function description, please refer to the [API reference](https://goodmanwen.github.io/RabiBridge/).

[Production deployment example](https://github.com/GoodManWEN/RabiBridge/blob/main/docs/blogs/production_deployment_example.md)

[Encryption in configuration file](https://github.com/GoodManWEN/RabiBridge/blob/main/docs/blogs/encryption_in_configuration_file.md)

## Configuration

For production and other needs,  to achieve higher convenience and stronger security, it is recommended to use configuration files instead of passing parameters. The configuration file options are as follows:

```toml
[rabbitmq]      
RABBITMQ_HOST = 'localhost'                    # RabbitMQ configuration info, same below.
RABBITMQ_PORT = 5672
RABBITMQ_USERNAME = "admin"
RABBITMQ_PASSWORD = "fMgmG7+ooAYLjXdPnhInjQ==" # AES Encrypted, check "Encryption in configuration file"

[app]
DEBUG_MODE = false                             # Whether to run in Debug mode.
CID_MAX = 1073741824                           # The maximum value of the independent ID assigned by 
                                               # the client for each message, which should not be 
                                               # too small or too large.
COMPRESS_THRESHOLD = 1024                      # Stream compression algorithm will be enabled when 
                                               # the message size exceeds this byte threshold.
SERIALISER = 'msgpack'                         # Literal['msgpack', 'pickle', 'json']

[secret]
SECRET = "your secret that no one knows"       # Avoid being known by anyone.
```

## Performance

![](https://github.com/GoodManWEN/RabiBridge/blob/main/misc/echo-performance-with-number-of-cpu-cores.png?raw=true)

Testing Platform: 
```
CPU Model            : Intel(R) Xeon(R) Platinum 8369B CPU @ 2.70GHz
CPU Cores            : 16 Cores 2699.998 MHz x86_64
CPU Cache            : L2 1280K & L3 49152K
OS                   : Ubuntu 22.04.4 LTS (64 Bit) KVM
Kernel               : 5.15.0-106-generic
Total RAM            : 950 MB / 30663 MB (4646 MB Buff)
Location             : San Jose / US
Region               : California
```

## Licence
The MIT License
