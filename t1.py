class MagicDict(dict):
    def __init__(self, *args, **kwargs):
        super(MagicDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    def __getitem__(self, key):
        try:
            return super(MagicDict, self).__getitem__(key)
        except KeyError:
            return MagicDict()
    
c = MagicDict()
print(c["12"]["13"])