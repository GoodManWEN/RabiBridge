import asyncio
import aio_pika
import random
import os
import pickle
import zstandard as zstd
from aio_pika.abc import AbstractChannel, AbstractIncomingMessage
from types import FunctionType
from typing import Optional, Literal, Any, Callable, Tuple
from pydantic import validate_call

from .utils import logger, trace_exception, load_config, get_config_val, list_main_functions
from .permissions import decrypt_pwd
from .models import ServiceSchema

CONFIG = load_config()
RABBITMQ_HOST: Optional[str] = get_config_val(CONFIG, "rabbitmq", "RABBITMQ_HOST")
RABBITMQ_PORT: Optional[int] = get_config_val(CONFIG, "rabbitmq", "RABBITMQ_PORT")
RABBITMQ_USERNAME: Optional[str] = get_config_val(CONFIG, "rabbitmq", "RABBITMQ_USERNAME")
RABBITMQ_PASSWORD: Optional[str] = decrypt_pwd(get_config_val(CONFIG, "rabbitmq", "RABBITMQ_PASSWORD"), CONFIG["secret"]["SECRET"])
CID_MAX: Optional[int] = get_config_val(CONFIG, "app", "CID_MAX")
COMPRESS_THRESHOLD: Optional[int] = get_config_val(CONFIG, "app", "COMPRESS_THRESHOLD")
DEBUG_MODE: Optional[bool] = get_config_val(CONFIG, "app", "DEBUG_MODE")


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
        if port is None:
            if RABBITMQ_PORT is None:
                raise ValueError("Invalid RabbitMQ port.")
            port = RABBITMQ_PORT
        if username is None:
            if RABBITMQ_USERNAME is None:
                raise ValueError("Invalid RabbitMQ username.")
            username = RABBITMQ_USERNAME
        if password is None:
            if RABBITMQ_PASSWORD is None:
                raise ValueError("Invalid RabbitMQ password.")
            password = RABBITMQ_PASSWORD
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
        body = pickle.dumps(body)
        if len(body) > COMPRESS_THRESHOLD:
            body = self._cctx_enc.compress(body)
        return body

    def _stream_decompress(self, msg_body: bytes) -> Any:
        if int.from_bytes(msg_body[:4], 'big') == self._zstd_magic_number:
            try:
                return pickle.loads(self._ccxt_dec.decompress(msg_body))
            except:
                ...
        return pickle.loads(msg_body)
    
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

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None):
        super().__init__(loop, host, port, username, password)
        random.seed(int.from_bytes(os.urandom(4), 'big'))
        self._cid_generator = self._cid_generator_func()
        self.result_futures = {} 
        
    @property
    def correlation_id(self) -> str:
        return str(next(self._cid_generator))

    def _cid_generator_func(self):
        val = random.randint(0, CID_MAX) % CID_MAX
        while True:
            yield val
            val = (val + 1) % CID_MAX

    async def connect(self) -> 'RMQClient':
        self.connection = await aio_pika.connect(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            login=RABBITMQ_USERNAME,
            password=RABBITMQ_PASSWORD
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
        await self.callback_queue.consume(self.on_response, no_ack=True)
        return self
    
    async def on_response(self, message: AbstractIncomingMessage) -> None:
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
    ) -> Tuple[int, Any]:
        '''
        Note:
            The timeout setting is recommended to be consistent with the timeout of the back-end service, if not, there may be a situation where the front-end has already timed out but the back-end still continues to execute the task.
            This is due to the loose coupling of front-end and back-end in rabbitmq, and the timeout cancellation mechanism can not be controlled by the publisher, active cancellation is not easy to realize.
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
        except asyncio.TimeoutError as toe:
            logger.error(f"Timeout, cid: {correlation_id}")
            del self.result_futures[correlation_id]
            raise toe
        else:
            res = self._stream_decompress(res_bytes)
            logger.trace(f"Result: {res}, cid: {correlation_id}")
            return res
        
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
        Return:
            (bool, Tuple[int, Any]): (success, (err_code, result))
            where success means if the call successfully returns, while err_code means if the call run smoothly on remote side, 0 for success, 1 for error.
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
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None):
        super().__init__(loop, host, port, username, password)
        self.services: Optional[dict[str, ServiceSchema]] = None
        self.channels: list[AbstractChannel] = []
        self._srv_coros = []

    @validate_call
    def load_services(self, symbols: dict[str, object]) -> None:
        '''
        Automatically captures all registered functions in global space, using which requires that all the specified call has already been registered.

        Args:
            symbols (dict[str, object]): global dict.

        Examples:
            >>> @register_call(...)
            >>> def call_1():
            >>>     ...
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
            if queue_size is not None and fetch_size is not None:
                assert fetch_size <= queue_size # have to be true
            queue_name = f"rpc_{'async' if is_async else 'sync'}_{name}"
            self.services[queue_name] = {
                'queue_name': queue_name, 
                'queue_obj': None,
                'func_ptr': ptr, 
                'queue_size': queue_size, 
                'fetch_size': fetch_size,
                'timeout': timeout,
                're_register': re_register,
                'is_async': is_async
            }
            logger.info(f"Service {queue_name} loaded. queue_size: {queue_size}, fetch_size: {fetch_size}. {ptr}")

    @validate_call
    def add_service(self, func_ptr: Callable[..., Any], queue_size: Optional[int], fetch_size: Optional[int], timeout: Optional[int] = None, re_register: bool = False):
        if not isinstance(func_ptr, FunctionType):
            raise ValueError("func_ptr must be a function pointer.")
        label = 'sync'
        if asyncio.iscoroutinefunction(func_ptr):
            label = 'async'
        queue_name = f"rpc_{label}_{func_ptr.__name__}"
        if queue_size is not None and fetch_size is not None:
            assert fetch_size <= queue_size # have to be true
        if self.services is None:
            self.services = {}
        self.services[queue_name] = {
            'queue_name': queue_name, 
            'queue_obj': None,
            'func_ptr': func_ptr, 
            'queue_size': queue_size, 
            'fetch_size': fetch_size,
            'timeout': timeout,
            're_register': re_register
        }
        logger.info(f"Service {queue_name} loaded. queue_size: {queue_size}, fetch_size: {fetch_size}. {func_ptr}")

    async def connect(self) -> "RMQServer":
        if self.services is None:
            raise ValueError("Services not loaded, you must load services first.")
        if self.connection is not None:
            raise ValueError("Connection already exists.")
        
        self.connection = await aio_pika.connect(
            host=RABBITMQ_HOST,
            port=RABBITMQ_PORT,
            login=RABBITMQ_USERNAME,
            password=RABBITMQ_PASSWORD
        )

        for queue_name, serv_obj in self.services.items():
            queue_name, _, func_ptr, queue_size, fetch_size, timeout, re_register, is_async = serv_obj.values()
            # channel
            channel: AbstractChannel = await self.connection.channel()
            if fetch_size is not None:
                await channel.set_qos(prefetch_count=fetch_size)
            self.channels.append(channel)
            exchange = await channel.declare_exchange(
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
                    await channel.declare_queue(name=queue_name, durable=True, arguments=args, passive=True)
                    await channel.queue_delete(queue_name)
                    logger.trace(f"Queue {queue_name} exist, former one deleted.")
                except aio_pika.exceptions.ChannelClosed:
                    # queue does not exist
                    logger.trace(f"Queue {queue_name} does not exist.")
            queue = await channel.declare_queue(name=queue_name, durable=True, arguments=args)
            await queue.bind(exchange, routing_key=queue_name[4:])
            self.services[queue_name]['queue_obj'] = queue 
            self._srv_coros.append(self.queue_listen_handler(queue, func_ptr, channel, is_async_function=is_async))
            
        return self
    

    async def call_handler(self, message: AbstractIncomingMessage, func_ptr: callable, channel: AbstractChannel, is_async_function: bool):
        try:
            async with message.process():
                if message.reply_to is None:
                    raise ValueError("Reply_to queue is None")
                args, kwargs = self._stream_decompress(message.body)
                logger.debug(f"Received message: {args}, {kwargs}, cid: {message.correlation_id}, reply_to: {message.reply_to}")
                call_code: int = 0 
                try:
                    if is_async_function:
                        result = await func_ptr(*args, **kwargs)
                    else:
                        result = func_ptr(*args, **kwargs)       ### TBD: migration to use thread pooling for execution
                except Exception as e:
                    call_code = 1
                    trace_exception(e)
                if call_code == 0:
                    logger.trace(f"Run result: {result}")
                    ret_body = self._stream_compress([call_code, result])
                else:
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
                logger.trace(f"Sent result: {result}, cid: {message.correlation_id}")
        except Exception as e:
            if DEBUG_MODE:
                raise e
            logger.error(trace_exception(e))

    async def queue_listen_handler(self, queue: aio_pika.Queue, func_ptr: callable, channel: AbstractChannel, is_async_function: bool):
        logger.info('start listening')  
        async with queue.iterator() as qiterator:
            async for message in qiterator: # message: AbstractIncomingMessage
                self.loop.create_task(self.call_handler(message, func_ptr, channel, is_async_function))

    async def run_serve(self):
        logger.info('start serving...')
        await asyncio.gather(*self._srv_coros)
  
    async def close(self):
        logger.info('closing...')
        if self.connection is not None:
            await self.connection.close()

    