# -*- coding: utf-8 -*-
# File name: client.py
import asyncio
from rabibridge import RMQClient

async def main():
    bridge = RMQClient(host="localhost", port=5672, username="admin", password="123456")
    async with bridge:
        err_code, result = await bridge.call_async('fibonacci', (10, ))
        print(f"Result is {result}")
        # >>> 

asyncio.run(main())