import asyncio
from rabibridge import RMQClient
from loguru import logger
import numpy as np
from typing import Optional, Callable, Any
from multiprocessing import Process, shared_memory
import time
try:
    import uvloop
    uvloop.install()
except:
    ...

THREAD_NUM = 64

async def update_shared_array(pidx, shared_array, total_counts):
    while True:
        await asyncio.sleep(0.25)
        shared_array[pidx] += total_counts[0]

async def async_thread(bridge, total_counts):
    async with bridge:
        while True:
            await bridge.try_call_async('func1', timeout=10)
            total_counts[0] += 1

async def process_async(pidx, shared_array, total_counts):
    loop = asyncio.get_running_loop()
    bridge = RMQClient(loop)
    logger.info('Connecting to RMQServer')
    loop.create_task(update_shared_array(pidx, shared_array, total_counts))
    coros = []
    for _ in range(THREAD_NUM):
        coros.append(async_thread(bridge, total_counts))
    await asyncio.gather(*coros)

def single_process(pidx: int, shm_name: str, dtype: Any, shape: Any):
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    shared_array = np.ndarray(shape, dtype=dtype, buffer=existing_shm.buf)
    loop = asyncio.new_event_loop()
    total_counts = [0, ]
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_async(pidx, shared_array, total_counts))
    except KeyboardInterrupt:
        pass

def multiprocess_spawn_helper(num_processes: Optional[int], single_process: Callable[..., Any], *, bind_core: Optional[bool] = False):
    from psutil import cpu_count
    from psutil import Process as psutil_Process
    
    dtype = np.int64
    array = np.zeros(num_processes+1, dtype=dtype)
    
    shm = shared_memory.SharedMemory(create=True, size=array.nbytes)
    shared_array = np.ndarray(array.shape, dtype=array.dtype, buffer=shm.buf)
    shared_array[:] = array[:]
    
    if num_processes is None:
        num_processes = cpu_count(logical=True)
    processes = []
    for pidx in range(num_processes):
        p = Process(target=single_process, args=(pidx, shm.name, dtype, array.shape))
        processes.append(p)
        p.start()
        if bind_core:
            psp = psutil_Process(p.pid)
            psp.cpu_affinity([pidx])

    try:
        time_0 = time.time()
        last_r = 0
        while True:
            time.sleep(1)
            time_now = time.time()
            r = np.sum(shared_array)
            logger.info(f'Total Counts: {r}, QPS: {round((r-last_r)/(time_now-time_0), 2)}/s')
            last_r = r
    except KeyboardInterrupt:
        for p in processes:
            p.terminate()
            p.join()
    
    shm.close() 
    shm.unlink()

if __name__ == '__main__':
    multiprocess_spawn_helper(4, single_process, bind_core=False)