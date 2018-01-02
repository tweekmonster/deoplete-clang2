import neovim

from . import scan


@neovim.plugin
class Clang2ElectricBoogaloo(object):
    def __init__(self, nvim):
        self.nvim = nvim

    @neovim.function('Clang2_objc_close_brace', sync=True)
    def close_objc_brace(self, args):
        line, col = args
        min_line = max(0, line - 10)
        buf_lines = self.nvim.current.buffer[min_line:line]
        buf_lines[-1] = buf_lines[-1][:col - 1]
        text = '\n'.join(buf_lines)
        i = scan.find_boundary(text)
        if i == -1:
            return 0, 0

        line -= text[i:].count('\n')
        col = i - text[:i].rfind('\n')
        return line, col
