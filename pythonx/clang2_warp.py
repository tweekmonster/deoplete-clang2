from clang2 import Clang2ElectricBoogaloo as _Clang2ElectricBoogaloo
import vim

_obj = _Clang2ElectricBoogaloo(vim)


def bar(*args):
    return _obj.bar(args)
