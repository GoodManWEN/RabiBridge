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
    bridge.load_services(globals())             # Automatic capture procedure of the main namespace
    async with bridge:
        await bridge.run_serve()

asyncio.run(main())