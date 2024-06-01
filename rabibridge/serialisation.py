from pydantic import validate_call
from typing import Literal, Any, Callable, Tuple

def get_serialisation_handler(mode: Literal['json', 'pickle', 'msgpack']) -> Tuple[Callable[..., bytes], Callable[..., Any]]:
    if mode == 'msgpack':
        import msgpack
        return msgpack.dumps, msgpack.loads
    elif mode == 'pickle':
        import pickle
        return pickle.dumps, pickle.loads
    elif mode == 'json':
        import json
        json_dumps = lambda x: json.dumps(x).encode('utf-8')
        return json_dumps, json.loads
    
