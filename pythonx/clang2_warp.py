from clang2 import Clang2ElectricBoogaloo as _Clang2ElectricBoogaloo
import vim

_obj = _Clang2ElectricBoogaloo(vim)


def close_objc_brace(*args):
    return _obj.close_objc_brace(args)
