from rabibridge import RMQServer, register_call, multiprocess_spawn_helper, logger
import asyncio
import os
try:
    import uvloop
    uvloop.install()
except:
    ...

base_dir = os.path.dirname(os.path.abspath(__file__))

async def process_async():
    s = RMQServer()
    s.load_services(globals())
    s.load_plugins(os.path.join(base_dir, 'plugins'))
    s.store.logger = logger
    async with s:
        await s.run_serve(reload=True)

def single_process():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_async())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    multiprocess_spawn_helper(4, single_process, bind_core=False)