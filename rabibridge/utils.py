import os
import toml
import sys
import traceback
import asyncio
from types import FunctionType
from typing import Generator, Tuple, Optional, Any, Callable
from loguru import logger
from pydantic import validate_call
from functools import wraps
from base64 import b64decode, b64encode

# 切换日志等级到trace
logger.remove()
# logger.add(sink=os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'), rotation='1 day', retention='7 days', level='TRACE'))
logger.add(sys.stdout, level='TRACE')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_BASE_DIR = os.path.dirname(BASE_DIR)

def load_config() -> dict:
    '''
    Args:
        None
    
    Returns:
        dict: the configuration dictionary.

    Note:
        The configuration file is located in the `config` folder of the project root directory, named `env.toml`.
    '''
    config_path = os.path.join(os.path.join(BASE_BASE_DIR, 'config'), 'env.toml')
    try:
        return toml.load(config_path)
    except:
        return {}

@validate_call
def get_config_val(config: dict, k1: str, k2: str) -> Any:
    return config.get(k1, {}).get(k2, None)

@validate_call
def decode_pwd(cipher: Optional[str], secret: Optional[str], decrypt_function: Callable[[bytes, bytes], bytes]) -> Optional[str]:
    if cipher is None or secret is None:
        return None
    return b64decode(decrypt_function(b64decode(cipher.encode('utf-8')), b64encode(secret.encode('utf-8')))).decode('utf-8')

@validate_call
def encode_pwd(pwd: Optional[str], secret: Optional[str], encrypt_function: Callable[[bytes, bytes], bytes]) -> Optional[str]:
    if pwd is None or secret is None:
        return None
    return b64encode(encrypt_function(pwd.encode('utf-8'), b64encode(secret.encode('utf-8')))).decode('utf-8')

@validate_call
def list_main_functions(global_symbols: dict[str, object], banned_names: list[str] = []) -> Generator[Tuple[str, str, object], None, None]:
    l = []
    for name, obj in global_symbols.items():
        if isinstance(obj, FunctionType):
            if obj.__module__ in ['__main__', '__mp_main__']:
                l.append([name, obj])
    for name, obj in l:
        if name not in banned_names:
            yield name, obj

@validate_call
def register_call(
    queue_size: Optional[int] = None, 
    fetch_size: Optional[int] = None, 
    timeout: Optional[int] = None,                   # secs
    *,
    validate: bool = False,
    re_register: bool = False,
):
    '''
    Args:
        queue_size: what the queue length for this call should be (maximum number of waiting tasks). Default to `None` means no limit. **Changing this parameter affects the persistence settings in rabbitmq, so it needs to be redeclared.**
        fetch_size: fetch size. You need to set a reasonable value to achieve maximum performance. Although for I/O-bound tasks, as more waiting does not open more connections, they usually don't consume too many system resources under an I/O multiplexing model. However, you generally shouldn't let your application listen to too many file descriptors at the same time. Typically, maintaining the system's listening file descriptors in the range of a few hundred to a few thousand is the key to ensuring efficiency. These file descriptors can ideally be assumed to be evenly distributed across different processes, with each process evenly distributed across different calls. From this, you can infer an appropriate value for this parameter to set, which usually shouldn't be too small or too large. Of course, if your business puts significant pressure on the backend, say a complex SQL search, limiting `fetch_size` to a very small value is an effective way to protect the backend service. The default is `None`, which means get all the messages in the current queue in the ready state.
        timeout: message timeout from the queue. Defaults to `None`. **Changing this parameter affects the persistence settings in rabbitmq, so it needs to be redeclared.**
        validate: whether to force constraints on the type legitimacy of input parameters when a remote call occurs, a wrapper for the `pydantic.validate_call` decorator. Defaults to `False`.
        re_register: whether to remove the hyperparameter in rabbitmq that the queue has been persisted and redeclare. Defaults to `False`.

    Note:
        re_register should not be used in multiprocessing mode, where reclaim will cause other worker disconeected.
    '''
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper._schema = {
            'queue_size': queue_size,
            'fetch_size': fetch_size,
            'timeout': timeout * 1000 if timeout is not None else None,
            're_register': re_register,
            'async': asyncio.iscoroutinefunction(func)
        }
        return wrapper if not validate else validate_call(wrapper)
    return decorator


def trace_exception(e: Exception) -> str:
    return ''.join(traceback.format_exception(type(e), value=e, tb=e.__traceback__))


@validate_call
def multiprocess_spawn_helper(num_processes: Optional[int], single_process: Callable[..., Any], *, bind_core: Optional[bool] = False):
    '''
    A simple function to help you use the multiprocessing module to expand a copy of a child process in each core. We recommend reading the source code directly if you want to understand the details.

    Args:
        num_processes: the number of processes to spawn. Input `None` means the number of logical cores.
        single_process: the function to be executed in each process.
        bind_core: whether to bind the process to the core. If your number of deployments is equal to the number of cores and your business is under pressure, turning on this option is good for avoiding register overhead due to core switching and can slightly improve performance. Most of the time it is not recommended to turn on. Defaults to `False`.
    '''
    from multiprocessing import Process
    from psutil import cpu_count
    from psutil import Process as psutil_Process
    
    
    if num_processes is None:
        num_processes = cpu_count(logical=True)
    processes = []
    for i in range(num_processes):
        p = Process(target=single_process, args=())
        processes.append(p)
        p.start()
        if bind_core:
            psp = psutil_Process(p.pid)
            psp.cpu_affinity([i])

    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        for p in processes:
            p.terminate()
            p.join()