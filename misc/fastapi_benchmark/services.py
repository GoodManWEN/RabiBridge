from rabibridge import RMQServer, register_call, multiprocess_spawn_helper
import uvloop
import asyncio
uvloop.install()

@register_call(queue_size=10000, fetch_size=128, timeout=10, re_register=False)
async def func1():
    # await asyncio.sleep(0)
    return 23

async def process_async():
    s = RMQServer()
    s.load_services(globals())
    async with s:
        await s.run_serve()

def single_process():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    multiprocess_spawn_helper(4, single_process, bind_core=True)