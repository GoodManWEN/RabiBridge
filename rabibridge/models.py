from aio_pika.abc import AbstractQueue
from pydantic import BaseModel
from typing import Any, Optional, Callable, Union 
from types import FunctionType
from pathlib import Path

# pydantic can implement constraints from third-party libraries, but it's too cumbersome to implement, so any involved here are always replaced with ANY.

class ServiceSchema(BaseModel):
    queue_name: str
    queue_obj: Any                  # queue_obj: AbstractQueue
    channel_obj: Any                # channel_obj: AbstractChannel
    func_ptr: Callable[..., Any]
    queue_size: Optional[int]
    fetch_size: Optional[int]       # Get limits in channels, connection is a tcp connection
    timeout: Optional[int]          # secs
    re_resiger: Optional[bool]      # Whether to re-register
    is_async: Optional[bool]        # Whether the function is asynchronous or not
    anchor_file: Optional[Union[Path, str]]  # The file path of the function