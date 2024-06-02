from rabibridge import register_call, Store

@register_call()
def hot_plug_function(store: Store):
    return 'hot_plug_function' + ' ' + str(store)