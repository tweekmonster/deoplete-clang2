import re
import string
import logging

from collections import deque

log = logging.getLogger('clang2')

brace_open = '[({'
brace_close = '])}'
quote_delim = '"\''
ascii_chars = string.ascii_letters
whitespace_chars = string.whitespace
word_chars = string.ascii_letters + string.digits + '_'
operators = (
    '=', '*', '/', '+', '-', '%', '++', '--',
    '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=', '<<=', '>>=',
    '==', '>', '>=', '<', '<=', '!=',
    '||', '&&', '^', '!', '~', '&', '|', '?', ':', '<<', '>>',
)
reserved = (
    'auto', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'enum', 'extern', 'float', 'for', 'goto', 'if', 'inline',
    'int', 'long', 'register', 'restrict', 'return', 'short', 'signed',
    'sizeof', 'static', 'struct', 'switch', 'typedef', 'union', 'unsigned',
    'void', 'volatile', 'while', '_Bool', '_Complex', '_Imaginary', 'bycopy',
    'byref', 'id', 'IMP', 'in', 'inout', 'nil', 'NO', 'NULL', 'oneway', 'out',
    'Protocol', 'SEL', 'YES', '@interface', '@end', '@implementation',
    '@protocol', '@class', '@public', '@protected', '@private', '@property',
    '@try', '@throw', '@catch', '@finally', '@synthesize', '@dynamic',
    '@selector',
)

left_re = re.compile(r'(?:\(.*?\))?(?:(?:\[.*\])|'
                     r'(?:[a-zA-Z]\w*?))$').match
arg_re = re.compile(r'[a-zA-Z]\w*:$').match
cast_re = re.compile(r'^\(.*?\)')


def white_forward(i, text):
    """Scan forward and skip whitespace."""
    while i < len(text) and text[i] in whitespace_chars:
        i += 1
    return i


def white_backward(i, text):
    """Scan backward and skip whitespace."""
    while i > 0 and text[i - 1] in whitespace_chars:
        i -= 1
    return i


def white_backward_continue(i, text):
    """Scan backward and skip characters.

    Skipped characters are those that should be included in the current atom.
    """
    # Type casting can have spaces before the variable.
    # Example: (NSString *) variable
    if text[i - 1] == ')':
        return i - 1

    return i


def skip_literal_mark(i, text):
    """Check if the current position indicates a literal type.

    Literals will be preceded with @.  Example: @"", @{}, @[]

    This will also check for block literals, which are preceded with ^.
    Example: ^(params){}, or ^{}
    """
    if i > 0:
        if text[i - 1] == '@':
            return i - 1

        if text[i] in '({':
            # Check for blocks
            n = white_backward(i, text)
            if text[n - 1] == '^':
                return n
    return i


def prev_pos(i, text):
    """Get the next position before the cursor.

    Returns the position where text can begin being evaluated as an
    Objective-C instance, method, or argument.
    """
    quote = ''
    brace = ''
    brace_skip = 0
    colon = text[i] == ':' and i > 0 and text[i - 1] != '\\'
    if colon:
        i -= 1

    while i > 0:
        if text[i - 1] == '\\':
            i -= 1
            continue

        c = text[i]
        if colon:
            # If we started at a colon, evaluate after hitting a non-word
            # character.
            if c not in word_chars:
                if c in whitespace_chars:
                    i = white_backward(i + 1, text)
                    n = white_backward_continue(i, text)
                    if n < i:
                        i = n
                        continue
                else:
                    i = white_backward(skip_literal_mark(i, text), text)
                    n = white_backward_continue(i, text)
                    if n < i:
                        i = n
                        continue
                return i + 1
        elif brace:
            if c in brace_close:
                b = brace_open[brace_close.index(c)]
                if b == brace:
                    brace_skip += 1
            elif c == brace:
                if brace_skip:
                    brace_skip -= 1
                else:
                    brace = ''
                    brace_skip = 0
                    i = white_backward(skip_literal_mark(i, text), text)
                    n = white_backward_continue(i, text)
                    if n < i:
                        i = n
                        continue
                    return i
        elif quote:
            if c == quote:
                quote = ''
                i = white_backward(skip_literal_mark(i, text), text)
                n = white_backward_continue(i, text)
                if n < i:
                    i = n
                    continue
                return i
        else:
            if c in quote_delim:
                quote = c
            elif c == ';':
                return i
            elif c in brace_open:
                # Hit an open brace.  The caller should figure it out.
                return -1
            elif not colon and c == ':':
                return i + 1
            elif c in brace_close:
                brace = brace_open[brace_close.index(c)]
                brace_skip = 0
            elif c in whitespace_chars:
                i = white_backward(i + 1, text)
                n = white_backward_continue(i, text)
                if n < i:
                    i = n
                    continue
                return i
        i -= 1
        if i == 0:
            return i
    return -1


def is_left_atom(atom):
    """Checks for a valid 'left side' atom in the current evaluation.

    Valid items are those that may have methods that can be called.

    Examples:

    - obj
    - [obj method]
    - (cast)[obj method]
    - @"string"
    - @{key: val}
    - @[val]
    """
    if left_re(atom):
        return True

    atom = cast_re.sub('', atom)
    if len(atom) > 2 and atom[0] == '@' and \
            ((atom[1] == '"' and atom[-1] == '"') or
             (atom[1] == '[' and atom[-1] == ']') or
             (atom[1] == '{' and atom[-1] == '}')):
        return True
    return False


def valid_atoms(prev):
    """Validate the previous two atoms.

    The left atom can be an object literal, method call, or string of word
    characters.  The name must begin with an ASCII letter.  The left atom can
    be prefixed a type cast (or at least what looks like a type cast).

    The right atom must begin with an ASCII letter.
    """
    if len(prev) < 2:
        return False

    log.debug('Evaluating atoms. Left: %r, Right: %r', prev[0], prev[1])

    # Left
    if not is_left_atom(prev[0]):
        return False

    # Right
    if prev[1][0] not in ascii_chars:
        return False

    return True


def find_boundary(text):
    """Finds starting position for closing an Objective-C method.

    It works by scanning backwards to the previous "atom".  An atom is a
    contiguous string of printable characters, or any character enclosed in
    braces or quotes.  For example:

      @"this is " stringByAppendingString:@"a string"
      ^[ insert   ^ atom                             ^] start

      The colon in methods are only considered a delimiter when an atom
      boundary has already been crossed:

      @"this is " stringByAppendingString:@"a string" className
      ^ atom      ^ atom                  ^[ insert   ^ atom   ^] start
    """
    i = white_backward(len(text), text)

    # An 'arg' is an atom that ends with a colon, while 'val' does not.
    # An 'arg' precedes a 'val'.  If these become unbalanced, evaluate what has
    # been parsed.
    arg_count = 0
    val_count = 0
    prev = deque(maxlen=2)

    while i > 0:
        n = prev_pos(i - 1, text)
        if n == -1 or n == i:
            log.debug('At end: %r', n)
            if val_count > 1 and val_count > arg_count and \
                    valid_atoms(prev):
                return white_forward(i, text)
            return -1

        # Encountering a semicolon ends the loop immediately.
        s = white_backward(n, text)
        hard_stop = text[s] == ';'
        if hard_stop:
            n = white_forward(n + 1, text)
            if val_count > 1 and val_count > arg_count and \
                    valid_atoms(prev):
                log.debug('Hard stop with atoms')
                return white_forward(n, text)
            log.debug('Hard stop')
            return -1

        atom = text[n:i]
        atom_s = atom.strip()
        if not atom_s:
            log.debug('Empty: %r', prev)
            i = n
            continue

        log.debug('Current atom: %r, Arg: %d, Val: %d', atom_s, arg_count, val_count)

        # Break early if the current atom isn't an arg, but the previous atom
        # was a method call.
        if len(prev) == 1 and atom_s and atom_s[-1] != ':':
            if prev[-1][0] == '[' and prev[-1][-1] == ']':
                if not is_left_atom(atom_s):
                    log.debug('Early break')
                    return -1
                return white_forward(n, text)

        # Atoms can't be reserved keywords or operators.
        if atom_s in reserved or atom_s in operators:
            if val_count > 1 and val_count > arg_count and \
                    valid_atoms(prev):
                return white_forward(i, text)
            prev.appendleft(atom_s)
            i = n
            log.debug('Skipping reserved or operator')
            continue

        if arg_re(atom_s):
            arg_count += 1
        else:
            val_count += 1
        log.debug('Args: %d, Vals: %d', arg_count, val_count)

        if val_count > 1 and val_count > arg_count:
            if not valid_atoms(prev):
                print('Not valid:', prev)
                prev.appendleft(atom_s)
                i = n
                continue

            if val_count == 2 and arg_count == 0:
                # If there were no arguments, use the pair from the current
                # position.
                i = n

            return white_forward(i, text)

        prev.appendleft(atom_s)
        i = n

    log.debug('Final eval')
    if val_count > 1 and val_count > arg_count and \
            valid_atoms(prev):
        return white_forward(i, text)
    return -1
