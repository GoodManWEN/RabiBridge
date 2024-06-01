from pydantic import validate_call
from typing import Literal, Any, Callable, Tuple

def get_serialisation_handler(mode: Literal['json', 'pickle', 'msgpack']) -> Tuple[Callable[..., bytes], Callable[..., Any]]:
    '''
    Get serialisation handler for different modes, which can be defined in the configuration file.

    Note:
        Since pickle has serialisation security issues in the python environment, we usually recommend using msgpack. json serialised data is larger in size in comparison. If you use json as a serialisation and deserialisation tool, you can use higher performance implementations such as ujson or orjson. at the same time, another problem with json is that you can't serialise bytes string directly.
    '''
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
    
