Module rabibridge
=================

Sub-modules
-----------
* rabibridge.exceptions
* rabibridge.models
* rabibridge.mq
* rabibridge.permissions
* rabibridge.serialisation
* rabibridge.utils

Functions
---------

    
`multiprocess_spawn_helper(num_processes: Optional[int], single_process: Callable[..., Any], *, bind_core: Optional[bool] = False)`
:   

    
`register_call(queue_size: Optional[int] = None, fetch_size: Optional[int] = None, timeout: Optional[int] = None, *, validate: bool = False, re_register: bool = False)`
:   Args:
        `queue_size`: what the queue length for this call should be (maximum number of waiting tasks). Default to None means no limit. *Changing this parameter affects the persistence settings in rabbitmq, so it needs to be redeclared.*
        `fetch_size`: fetch size. You need to set a reasonable value to achieve maximum performance. Although for I/O-bound tasks, as more waiting does not open more connections, they usually don't consume too many system resources under an I/O multiplexing model. However, you generally shouldn't let your application listen to too many file descriptors at the same time. Typically, maintaining the system's listening file descriptors in the range of a few hundred to a few thousand is the key to ensuring efficiency. These file descriptors can ideally be assumed to be evenly distributed across different processes, with each process evenly distributed across different calls. From this, you can infer an appropriate value for this parameter to set, which usually shouldn't be too small or too large. Of course, if your business puts significant pressure on the backend, say a complex SQL search, limiting `fetch_size` to a very small value is an effective way to protect the backend service. 
        `timeout`: message timeout from the queue. Defaults to None. *Changing this parameter affects the persistence settings in rabbitmq, so it needs to be redeclared.*
        `validate`: whether to force constraints on the type legitimacy of input parameters when a remote call occurs, a wrapper for the pydantic.validate_call decorator. Defaults to False.
        `re_register`: whether to remove the hyperparameter in rabbitmq that the queue has been persisted and redeclare. Defaults to False.
    
    Note:
        re_register should not be used in multiprocessing mode, where reclaim will cause other worker disconeected.

Classes
-------

`RMQClient(loop: Optional[asyncio.events.AbstractEventLoop] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None)`
:   Acting as a client-initiating requestor in a gateway service.
    
    The following parameters are used preferentially if they are specified, if they are not specified, the configuration file is searched to use, and an error is reported if they are not in the configuration file either.
    
    Args:
        loop: Event loop in this particular process. Defaults to None.
        host: RabbitMQ host. Defaults to None.
        port: RabbitMQ port. Defaults to None.
        username: RabbitMQ username. Defaults to None.
        password: RabbitMQ password. Defaults to None.

    ### Ancestors (in MRO)

    * rabibridge.mq.RMQBase

    ### Instance variables

    `correlation_id: str`
    :   A (periodically) self-incrementing pointer that should not normally be called directly by the user.

    ### Methods

    `close(self)`
    :

    `connect(self) ‑> rabibridge.mq.RMQClient`
    :   It should be connected using `connect()` before making the call and released using `close()` before closing the client. The client can be used as a context manager to ensure that the connection is closed properly after use.
        
        Examples:
            >>> async with RMQClient(...) as client:
            >>>     res = await client.remote_call(...)
            >>>     print(res)

    `remote_call(self, func_name: str, args: tuple[typing.Any] = (), kwargs: dict[typing.Any] = {}, ftype: Literal['async', 'sync'] = 'async', *, timeout: Optional[float] = None) ‑> Any`
    :   Args:
            `func_name`: function name to be called.
            `args`: arguments. Defaults to ().
            `kwargs`: keyword arguments. Defaults to {}.
            `ftype`: function type to be called remotely. e.g. defaults to 'async', and asynchronous call will be made on server side.
            `timeout`: Client timeout time, independent from queue timeout hyper-parameter. Defaults to None.
        
        Note:
            The timeout setting is recommended to be consistent with the timeout of the back-end service, if not, there may be a situation where the front-end has already timed out but the back-end still continues to execute the task.
            This is due to the loose coupling of front-end and back-end in rabbitmq, and the timeout cancellation mechanism can not be controlled by the publisher, active cancellation is not easy to realize.
            This function will uplift errors that may occur during execution:
        
            This function raises errors that may occur during execution, possible errors are: call queue is full (aio_pika.Basic.Nack), call timeout (asyncio.TimeoutError), remote execution error (rabibridge.RemoteExecutionError).
        
        Examples:
            >>> try:
            >>>     res = await client.remote_call(...)
            >>> Except Exceition as e:
            >>>     ...
            
        Returns:
            Any: (result) The result of the remote call.

    `try_remote_call(self, func_name: str, args: tuple[typing.Any] = (), kwargs: dict[typing.Any] = {}, ftype: Literal['async', 'sync'] = 'async', *, timeout: Optional[float] = None) ‑> Tuple[bool, Tuple[int, Any]]`
    :   A simplified way of writing remote_call, there is no essential difference between the two. Instead of doing a try except externally, you control the process execution through the error code.
        
        Return:
            (bool, Tuple[int, Any]): (success, (err_code, result))
            Where success means if the call successfully returns on client side, if it returns normally, it means that no timeout or full queue error has occurred, but this does not mean that the returned result is reliable.
            While err_code means if the call run smoothly on remote side, 0 for success, 1 for error. 
        
            The relationship between success and err_code: If error_code is 0, the result is reliable. If error_code is 1, it is necessary to determine whether the error occurred on the client or server side based on success.

`RMQServer(loop: Optional[asyncio.events.AbstractEventLoop] = None, host: Optional[str] = None, port: Optional[int] = None, username: Optional[str] = None, password: Optional[str] = None)`
:   Used to provide services with daemon process.
    
    The following parameters are used preferentially if they are specified, if they are not specified, the configuration file is searched to use, and an error is reported if they are not in the configuration file either.
    
    Args:
        `loop`: Event loop in this particular process. Defaults to None.
        `host`: RabbitMQ host. Defaults to None.
        `port`: RabbitMQ port. Defaults to None.
        `username`: RabbitMQ username. Defaults to None.
        `password`: RabbitMQ password. Defaults to None.

    ### Ancestors (in MRO)

    * rabibridge.mq.RMQBase

    ### Methods

    `add_service(self, func_ptr: Callable[..., Any], queue_size: Optional[int], fetch_size: Optional[int], timeout: Optional[int] = None, re_register: bool = False)`
    :   If you do not wish to use automatic capture, you can register the service manually. Manually registered services do not need to be pre-registered using the `recister_call` decorator.
        
        For technical details and meanings of the parameters, please refer to the description in `register_call`.
        
        Args:
            `func_ptr`: function pointer.
            `queue_size`: queue size.
            `fetch_size`: fetch size.
            `timeout`: timeout. Defaults to None.
            `re_register`: re-register. Defaults to False.

    `close(self)`
    :

    `connect(self) ‑> rabibridge.mq.RMQServer`
    :   It should be connected using `connect()` before making the call and released using `close()` before closing the client. The client can be used as a context manager to ensure that the connection is closed properly after use.
        
        Examples:
            >>> s = RMQServer(...)
            >>> s.load_services(globals())
            >>> async with s:
            >>>     await server.run_serve()

    `load_services(self, symbols: dict[str, object]) ‑> None`
    :   Automatically captures all registered functions in global space, using which requires that all the specified call has already been registered.
        
        Args:
            `symbols`: global dict.
        
        Examples:
            >>> @register_call(...)
            >>> def call_1():
            >>>     ...
            >>> obj.load_services(globals())
            None # call_1 has been loaded

    `run_serve(self)`
    :   Start the service, the program will block once called.

`RemoteExecutionError(*args, **kwargs)`
:   Raised when an exception occurs during remote execution.

    ### Ancestors (in MRO)

    * builtins.Exception
    * builtins.BaseException