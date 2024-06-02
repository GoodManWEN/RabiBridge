import asyncio
import aio_pika
import random
import os
import inspect
import zstandard as zstd
from aio_pika.abc import AbstractRobustChannel, AbstractIncomingMessage, AbstractQueue
from types import FunctionType
from typing import Optional, Literal, Any, Callable, Tuple, Union
from pydantic import validate_call
from pathlib import Path
from watchfiles import awatch

from .utils import logger, trace_exception, load_config, get_config_val, list_main_functions, dynamic_load_module
from .serialisation import get_serialisation_handler
from .permissions import decrypt_pwd
from .models import ServiceSchema
from .exceptions import RemoteExecutionError, FileChangedException
from .store import Store, resolve_dependencies

CONFIG = load_config()
RABBITMQ_HOST: Optional[str] = get_config_val(CONFIG, "rabbitmq", "RABBITMQ_HOST")
RABBITMQ_PORT: Optional[int] = get_config_val(CONFIG, "rabbitmq", "RABBITMQ_PORT")
RABBITMQ_USERNAME: Optional[str] = get_config_val(CONFIG, "rabbitmq", "RABBITMQ_USERNAME")
RABBITMQ_PASSWORD: Optional[str] = decrypt_pwd(get_config_val(CONFIG, "rabbitmq", "RABBITMQ_PASSWORD"), get_config_val(CONFIG, "secret", "SECRET"))
CID_MAX: Optional[int] = get_config_val(CONFIG, "app", "CID_MAX")
COMPRESS_THRESHOLD: Optional[int] = get_config_val(CONFIG, "app", "COMPRESS_THRESHOLD")
DEBUG_MODE: Optional[bool] = get_config_val(CONFIG, "app", "DEBUG_MODE")
SERIALISER: Optional[str] = get_config_val(CONFIG, "app", "SERIALISER")

if SERIALISER is None:
    SERIALISER = 'msgpack'

serialisation_dumps, serialisation_loads = get_serialisation_handler(SERIALISER)


class RMQBase:
    def __init__(
        self, 
        loop: Optional[asyncio.AbstractEventLoop] = None, 
        host: Optional[str] = None, 
        port: Optional[int] = None, 
        username: Optional[str] = None, 
        password: Optional[str] = None
    ):
        if host is None:
            if RABBITMQ_HOST is None:
                raise ValueError("Invalid RabbitMQ host.")
            host = RABBITMQ_HOST
        self.host = host
        if port is None:
            if RABBITMQ_PORT is None:
                raise ValueError("Invalid RabbitMQ port.")
            port = RABBITMQ_PORT
        self.port = port
        if username is None:
            if RABBITMQ_USERNAME is None:
                raise ValueError("Invalid RabbitMQ username.")
            username = RABBITMQ_USERNAME
        self.username = username
        if password is None:
            if RABBITMQ_PASSWORD is None:
                raise ValueError("Invalid RabbitMQ password.")
            password = RABBITMQ_PASSWORD
        self.password = password
        self.loop = loop
        if loop is None:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.loop)
        self.connection = None
        self._cctx_enc = zstd.ZstdCompressor(level=3)
        self._ccxt_dec = zstd.ZstdDecompressor()
        self._zstd_magic_number = 0x28B52FFD
    
    def _stream_compress(self, body: Any) -> bytes:
        body = serialisation_dumps(body)
        if len(body) > COMPRESS_THRESHOLD:
            body = self._cctx_enc.compress(body)
        return body

    def _stream_decompress(self, msg_body: bytes) -> Any:
        if int.from_bytes(msg_body[:4], 'big') == self._zstd_magic_number:
            try:
                return serialisation_loads(self._ccxt_dec.decompress(msg_body))
            except:
                raise ValueError("Decompression error.")
        return serialisation_loads(msg_body)
    
    async def connect(self) -> 'RMQBase':
        raise NotImplementedError()
    
    async def close(self) -> None:
        raise NotImplementedError()
    
    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

class RMQClient(RMQBase):
    '''
    Acting as a client-initiating requestor in a gateway service.
    '''

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None):
        '''
        The following parameters are used preferentially if they are specified, if they are not specified, the configuration file is searched to use, and an error is reported if they are not in the configuration file either.

        Args:
            loop: Event loop in this particular process. Defaults to `None`.
            host: RabbitMQ host. Defaults to `None`.
            port: RabbitMQ port. Defaults to `None`.
            username: RabbitMQ username. Defaults to `None`.
            password: RabbitMQ password. Defaults to `None`.
        '''
        super().__init__(loop, host, port, username, password)
        random.seed(int.from_bytes(os.urandom(4), 'big'))
        self._cid_generator = self._cid_generator_func()
        self.result_futures = {} 
        
    @property
    def correlation_id(self) -> str:
        '''
        A (periodically) self-incrementing pointer that should not normally be called directly by the user.
        '''
        return str(next(self._cid_generator))

    def _cid_generator_func(self):
        val = random.randint(0, CID_MAX) % CID_MAX
        while True:
            yield val
            val = (val + 1) % CID_MAX

    async def connect(self) -> 'RMQClient':
        '''
        It should be connected using `connect()` before making the call and released using `close()` before closing the client. The client can be used as a context manager to ensure that the connection is closed properly after use.

        Examples:
            >>> async with RMQClient(...) as client:
            ...     res = await client.remote_call(...)
            ...     print(res)
        '''
        self.connection = await aio_pika.connect_robust(
            host=self.host,
            port=self.port,
            login=self.username,
            password=self.password,
        )
        self.channel = await self.connection.channel(on_return_raises=True)
        '''
        Current design is lacks of some flexibility, in that a call to an undeclared function can result in the channel broken and not continuing to be used any more. However, as this is the simplest way of returning an exception from a user call under AMQP that can be implemented at the moment. So, as a result, the current code requires developers to try out the code before deploying, which is not a huge drawback IMO.
        '''
        self.exchange = await self.channel.declare_exchange(
            name='rpc', 
            type=aio_pika.ExchangeType.DIRECT,
            durable=True
        )
        self.callback_queue = await self.channel.declare_queue('', exclusive=True)
        await self.callback_queue.consume(self._on_response, no_ack=True)
        return self
    
    async def _on_response(self, message: AbstractIncomingMessage) -> None:
        logger.trace(f"Received message: {message.body}, cid: {message.correlation_id}")
        if message.correlation_id is None:
            logger.warning(f"Correlation ID is None: {repr(message)}")
            return 
        # else 
        try:
            future: asyncio.Future = self.result_futures.pop(message.correlation_id)
        except KeyError:
            # The task no longer exists on the front end
            # logger.trace(f"Correlation ID not found: {message.correlation_id}")
            return
        future.set_result(message.body)

    async def remote_call(
        self, 
        func_name: str, 
        args: tuple[Any] = (), 
        kwargs: dict[Any] = {}, 
        ftype: Literal['async', 'sync'] = 'async',
        *, 
        timeout: Optional[float] = None
    ) -> Any:
        '''
        Args:
            func_name: function name to be called.
            args: arguments. Defaults to `()`.
            kwargs: keyword arguments. Defaults to `{}`.
            ftype: function type to be called remotely. e.g. defaults to 'async', and asynchronous call will be made on server side.
            timeout: Client timeout time, independent from queue timeout hyper-parameter. Defaults to `None`.

        Note:
            The timeout setting is recommended to be consistent with the timeout of the back-end service, if not, there may be a situation where the front-end has already timed out but the back-end still continues to execute the task.
            This is due to the loose coupling of front-end and back-end in rabbitmq, and the timeout cancellation mechanism can not be controlled by the publisher, active cancellation is not easy to realize.
            This function will uplift errors that may occur during execution:

            This function raises errors that may occur during execution, possible errors are: call queue is full (aio_pika.Basic.Nack), no route (aiormq.exceptions.PublishError), call timeout (asyncio.TimeoutError), remote execution error (rabibridge.RemoteExecutionError).

        Examples:
            >>> try:
            ...     res = await client.remote_call(...)
            >>> Except Exceition as e:
            ...     ...
            
        Returns:
            Any: (result) The result of the remote call.
        '''
        # res_future = self.loop.create_future() # may cause future belongs to a different loop error under some particular engine implementation. Currently don't know reason.
        res_future = asyncio.Future()
        correlation_id = self.correlation_id
        self.result_futures[correlation_id] = res_future
        body: bytes = self._stream_compress([args, kwargs])
        logger.trace(f"Call async: {func_name}, {args}, {kwargs}, cid: {correlation_id}, sent body: {body}, routing_key: {ftype}_{func_name}")
        try:
            await self.exchange.publish(
                aio_pika.Message(
                    body=body,
                    correlation_id=correlation_id,
                    reply_to=self.callback_queue.name
                ),
                routing_key=f"{ftype}_{func_name}",
                mandatory=True
            )
            
        except Exception as e: # Basic.Nack
            del self.result_futures[correlation_id]
            raise e

        try:
            res_bytes = await asyncio.wait_for(res_future, timeout=timeout)
            err_code, res = self._stream_decompress(res_bytes)
        except asyncio.TimeoutError as toe:
            logger.error(f"Timeout/decode error, cid: {correlation_id}")
            del self.result_futures[correlation_id]
            raise toe
        else:
            logger.trace(f"Result: {err_code}: {res}, cid: {correlation_id}")
            if err_code == 1:
                raise RemoteExecutionError(res)
            return err_code, res
        
    async def try_remote_call(
        self, 
        func_name: str, 
        args: tuple[Any] = (), 
        kwargs: dict[Any] = {}, 
        ftype: Literal['async', 'sync'] = 'async',
        *, 
        timeout: Optional[float] = None
    ) -> Tuple[bool, Tuple[int, Any]]:
        '''
        A simplified way of writing remote_call, there is no essential difference between the two. Instead of doing a try except externally, you control the process execution through the error code.

        Return:
            (bool, Tuple[int, Any]): (success, (err_code, result))
            Where success means if the call successfully returns on client side, if it returns normally, it means that no timeout or full queue error has occurred, but this does not mean that the returned result is reliable.
            While err_code means if the call run smoothly on remote side, 0 for success, 1 for error. 

            The relationship between success and err_code: If error_code is 0, the result is reliable. If error_code is 1, it is necessary to determine whether the error occurred on the client or server side based on success.
        '''
        try:
            res: Tuple[int, Any] = await self.remote_call(func_name, args, kwargs, ftype, timeout=timeout)
            return True, res
        except Exception as e:
            return False, [1, e]


    async def close(self):
        if self.connection is not None:
            await self.connection.close()


class RMQServer(RMQBase):
    '''
    Used to provide services with daemon process.
    '''

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None):
        '''
        The following parameters are used preferentially if they are specified, if they are not specified, the configuration file is searched to use, and an error is reported if they are not in the configuration file either.

        Args:
            loop: Event loop in this particular process. Defaults to `None`.
            host: RabbitMQ host. Defaults to `None`.
            port: RabbitMQ port. Defaults to `None`.
            username: RabbitMQ username. Defaults to `None`.
            password: RabbitMQ password. Defaults to `None`.
        '''
        super().__init__(loop, host, port, username, password)
        self.services: Optional[dict[str, ServiceSchema]] = None
        self.channels: list[AbstractRobustChannel] = []
        self._srv_coros = []
        self.store = Store()
        self.plugin_dir: Optional[Path] = None
        self._valid_plugins: set[str] = set()

    @validate_call
    def load_services(self, symbols: dict[str, object]) -> None:
        '''
        Automatically captures all registered functions in global space, using which requires that all the specified call has already been registered.

        Args:
            symbols: global dict.

        Examples:
            >>> @register_call(...)
            >>> def call_1():
            ...     ...
            >>> obj.load_services(globals())
            None # call_1 has been loaded
        '''
        self.services = {}
        for name, ptr in list_main_functions(symbols, banned_names=[]):
            schema = getattr(ptr, '_schema', None)
            if schema is None: 
                continue
                # queue_size, fetch_size, timeout, re_register, is_async = None, None, None, False, asyncio.iscoroutinefunction(ptr)
            else:
                queue_size, fetch_size, timeout, re_register, is_async = schema.values()

            queue_name = f"rpc_{'async' if is_async else 'sync'}_{name}"
            self.services[queue_name] = {
                'queue_name': queue_name, 
                'queue_obj': None,
                'channel_obj': None,
                'func_ptr': ptr, 
                'queue_size': queue_size, 
                'fetch_size': fetch_size,
                'timeout': timeout,
                're_register': re_register,
                'is_async': is_async,
                'anchor_file': ptr._co_filename
            }
            logger.info(f"Service {queue_name} loaded. queue_size: {queue_size}, fetch_size: {fetch_size}. {ptr}")

    @validate_call
    def add_service(self, func_ptr: Callable[..., Any], queue_size: Optional[int] = None, fetch_size: Optional[int] = None, timeout: Optional[int] = None, re_register: bool = False) -> ServiceSchema:
        '''
        If you do not wish to use automatic capture, you can register the service manually. Manually registered services do not need to be pre-registered using the `recister_call` decorator.

        For technical details and meanings of the parameters, please refer to the description in `register_call`.

        Args:
            func_ptr: function pointer.
            queue_size: queue size.
            fetch_size: fetch size.
            timeout: timeout. Defaults to `None`.
            re_register: re-register. Defaults to `False`.
            
        '''
        if not isinstance(func_ptr, FunctionType):
            raise ValueError("func_ptr must be a function pointer.")
        if self.services is None:
            self.services = {}
        
        is_async = False
        if asyncio.iscoroutinefunction(func_ptr):
            is_async = True
        schema = getattr(func_ptr, '_schema', None)
        if schema is not None: 
            queue_size_1, fetch_size_1, timeout_1, re_register_1, is_async = schema.values()
            if queue_size is None:
                queue_size = queue_size_1
            if fetch_size is None:
                fetch_size = fetch_size_1
            if timeout is None:
                timeout = timeout_1
            if re_register is None:
                re_register = re_register_1
        
        queue_name = f"rpc_{'async' if is_async else 'sync'}_{func_ptr.__name__}"
        if queue_name not in self.services:
            add_obj = {
                'queue_name': queue_name, 
                'queue_obj': None,
                'channel_obj': None,
                'func_ptr': func_ptr, 
                'queue_size': queue_size, 
                'fetch_size': fetch_size,
                'timeout': timeout,
                're_register': re_register,
                'is_async': is_async,
                'anchor_file': func_ptr._co_filename  # self defined value
            }
            self.services[queue_name] = add_obj
            logger.info(f"Service {queue_name} loaded. queue_size: {queue_size}, fetch_size: {fetch_size}. At {func_ptr}")
            return add_obj
        else:
            return self.services[queue_name]

    @validate_call
    def load_plugins(self, plugin_dir: Union[Path, str]) -> None:
        '''
        Load services from a specified directory, the directory should contain python files that have been registered with the `register_call` decorator.
        
        Args:
            plugin_dir: plugin directory.
        '''
        if self.services is None:
            self.services = {}
        if isinstance(plugin_dir, str):
            plugin_dir = Path(plugin_dir)
        plugin_dir = plugin_dir.resolve()
        self.plugin_dir = plugin_dir
        self._valid_plugins.clear()
        if not plugin_dir.exists():
            raise ValueError("Plugin directory does not exist.")
        for file in plugin_dir.iterdir():
            if not file.is_file():
                continue
            if file.suffix == '.py' and file.stem.startswith('plugin'):
                try:
                    module = dynamic_load_module(file)
                    functions = inspect.getmembers(module, inspect.isfunction)
                    for _, func_ptr in functions:
                        _schema = getattr(func_ptr, '_schema', None)
                        if _schema is not None:
                            add_obj = self.add_service(func_ptr)
                            self._valid_plugins.add(f"{add_obj['anchor_file']}: {add_obj['queue_name']}")
                except Exception as e:
                    logger.warning(f"Load plugin error: {type(e)}: {e}")
                    continue

    async def _unplug_offline_plugins(self):
        
        if self.plugin_dir is None:
            raise ValueError("Plugin directory should be already specified to run this method.")
        
        _pop_list = []
        for service, service_schema in self.services.items():
            if service_schema['func_ptr'].__module__ == '__main__':
                continue
            identity = f"{service_schema['anchor_file']}: {service_schema['queue_name']}"
            if identity not in self._valid_plugins:
                _pop_list.append(service)
        
        for service in _pop_list:
            try:
                service_schema = self.services.pop(service)
                await service_schema['channel_obj'].close()
            except:
                continue
            logger.info(f"Service {service} has been unplugged. {service_schema}")

    async def connect(self) -> "RMQServer":
        '''
        It should be connected using `connect()` before making the call and released using `close()` before closing the client. The client can be used as a context manager to ensure that the connection is closed properly after use.
        
        Examples:
            >>> s = RMQServer(...)
            >>> s.load_services(globals())
            >>> async with s:
            ...     await server.run_serve()
        '''
        if self.services is None:
            raise ValueError("Services not loaded, you must load services first.")
        if self.connection is not None:
            raise ValueError("Connection already exists.")
        
        self.connection = await aio_pika.connect_robust(
            host=self.host,
            port=self.port,
            login=self.username,
            password=self.password
        )

        await self._create_coroutines()
            
        return self
    
    async def _create_coroutines(self) -> None:
        for queue_name, serv_obj in self.services.items():
            queue_name, queue_obj, channel_obj, func_ptr, queue_size, fetch_size, timeout, re_register, is_async, _ = serv_obj.values()

            if queue_obj is None or channel_obj is None:
                # channel
                channel_obj: AbstractRobustChannel = await self.connection.channel()
                if fetch_size is not None:
                    await channel_obj.set_qos(prefetch_count=fetch_size)
                self.channels.append(channel_obj)
                exchange = await channel_obj.declare_exchange(
                    name='rpc',
                    type=aio_pika.ExchangeType.DIRECT,
                    durable=True
                )

                # queue
                args = {'x-overflow': 'reject-publish'}
                if timeout is not None:
                    args['x-message-ttl'] = timeout
                if queue_size is not None:
                    args['x-max-length'] = queue_size
                if re_register:
                    try:
                        await channel_obj.declare_queue(name=queue_name, durable=True, arguments=args, passive=True, auto_delete=True)
                        await channel_obj.queue_delete(queue_name)
                        logger.trace(f"Queue {queue_name} exist, former one deleted.")
                    except aio_pika.exceptions.ChannelClosed:
                        # queue does not exist
                        logger.trace(f"Queue {queue_name} does not exist.")
                queue_obj = await channel_obj.declare_queue(name=queue_name, durable=True, arguments=args, auto_delete=True)
                await queue_obj.bind(exchange, routing_key=queue_name[4:])
                self.services[queue_name]['queue_obj'] = queue_obj
                self.services[queue_name]['channel_obj'] = channel_obj
            self._srv_coros.append(self._queue_listen_handler(queue_name, queue_obj, func_ptr, channel_obj, is_async_function=is_async))

    async def _call_handler(self, queue_name: str, message: AbstractIncomingMessage, func_ptr: Callable, func_signature: inspect.Signature, channel: AbstractRobustChannel, is_async_function: bool):
        try:
            async with message.process():
                if message.reply_to is None:
                    raise ValueError("Reply_to queue is None")
                args, kwargs = self._stream_decompress(message.body)
                # logger.trace(f"Received message: {args}, {kwargs}, cid: {message.correlation_id}, reply_to: {message.reply_to}")
                logger.info(f"Received call: {queue_name}, reply_to: {message.reply_to}, cid: {message.correlation_id}")
                call_code: int = 0 
                try:
                    args, kwargs = resolve_dependencies(args, kwargs, func_signature, self.store)
                    if is_async_function:
                        result = await func_ptr(*args, **kwargs)
                    else:
                        result = func_ptr(*args, **kwargs)       ### TBD: migration to use thread pooling for execution
                    logger.trace(f"Run result: {result}")
                    ret_body = self._stream_compress([call_code, result])
                except Exception as e:
                    call_code = 1
                    err_msg = trace_exception(e)
                    logger.debug(f"Run error: {err_msg}")
                    ret_body = self._stream_compress([call_code, err_msg])

                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=ret_body, 
                        correlation_id=message.correlation_id
                    ),
                    routing_key=message.reply_to
                )
                if call_code == 0:
                    logger.trace(f"Sent result: {result}, cid: {message.correlation_id}")
                else:
                    logger.trace(f"Sent error: {err_msg}, cid: {message.correlation_id}")
        except Exception as e:
            if DEBUG_MODE:
                raise e
            logger.error(trace_exception(e))

    async def _queue_listen_handler(self, queue_name: str, queue: aio_pika.Queue, func_ptr: callable, channel: AbstractRobustChannel, is_async_function: bool):
        logger.info(f'Start listening {queue_name}')  
        func_signature: inspect.Signature = inspect.signature(func_ptr)
        async with queue.iterator() as qiterator:
            async for message in qiterator: # message: AbstractIncomingMessage
                self.loop.create_task(self._call_handler(queue_name, message, func_ptr, func_signature, channel, is_async_function))

    async def _file_event_watcher(self, path: Path):
        async for change in awatch(path):
            evt, cpath = change.pop()
            if Path(cpath).parent != self.plugin_dir:
                continue
            raise FileChangedException(f'File event: {evt}, {cpath}')
            

    async def run_serve(self, *, reload: bool = False):
        '''
        Start the service, the program will block once called.

        Args:
            reload: whether to reload the service on file changes. Defaults to `False`. **You need to explicitly call `load_plugins()` first to enable this option**

        Note:
            Repeated loading and unloading in the current version can lead to memory leaks.
        '''
        if reload == True and self.plugin_dir is None:
            raise ValueError("Plugin directory should be already specified to run this method.")
        
        pid = os.getpid()
        logger.info(f'Start serving at pid: {pid}...')
        while True:
            if reload:
                self._srv_coros.append(self._file_event_watcher(self.plugin_dir))
            try:
                await asyncio.gather(*self._srv_coros) # Once gather is interrupted by an exception, one of the tasks will be set to the done state
            except FileChangedException as fce:
                logger.info(f'File changed captured: {fce}')
                self.load_plugins(self.plugin_dir)
                await self._unplug_offline_plugins()
                self._srv_coros.clear()
                await self._create_coroutines()
                logger.info('Reloaded services.')
                
            except Exception as e:
                raise e
            if not reload:
                break
            # else 
            
  
    async def close(self):
        logger.info('Closing...')
        if self.connection is not None:
            await self.connection.close()

    