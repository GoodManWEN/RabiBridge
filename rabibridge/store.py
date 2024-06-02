import inspect
from typing import Any, Dict
from pydantic import BaseModel, Field

class Store(BaseModel):
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    def __init__(self, **kwargs: Any):
        super().__init__(extra_fields=kwargs)

    def __getattr__(self, item):
        try:
            return self.extra_fields[item]
        except KeyError:
            raise AttributeError(f"'Store' object has no attribute '{item}'")

    def __setattr__(self, key, value):
        if key == "extra_fields":
            super().__setattr__(key, value)
        else:
            self.extra_fields[key] = value

def resolve_dependencies(args: tuple, kwargs: dict, signature: inspect.Signature, store_obj: Store):
    for name, param in signature.parameters.items():
        if param.annotation == Store:
            kwargs[name] = store_obj
    return args, kwargs