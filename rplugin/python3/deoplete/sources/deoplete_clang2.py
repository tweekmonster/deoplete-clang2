import os
import re
import sys
import glob
import json
import time
import shlex
import hashlib
import tarfile
import tempfile
import threading
import subprocess

from itertools import chain
from urllib.request import urlopen

from .base import Base

repo_dirs = set(['.git', '.hg', '.svn'])
flag_pattern = ''.join(r""""
-resource-dir|
(?:
    (?:-(?:internal|externc|c|cxx|objc))*?
    -i(?:
        (?:nclude-(?:p[ct]h))|
        quote|prefix|sysroot|system|framework|dirafter|macros|withprefix|
        withprefixbefore|withsysroot
    )
)
""".split())

std_default = {
    'c': 'c11',
    'cpp': 'c++1z',
    'objc': 'c11',
    'objcpp': 'c++1z',
}

lang_names = {
    'c': 'c',
    'cpp': 'c++',
    'objc': 'objective-c',
    'objcpp': 'objective-c++',
}

pch_cache = os.path.join(tempfile.gettempdir(), 'deoplete-clang2')

if sys.platform == 'darwin':
    darwin_sdk_dl_path = os.path.expanduser('~/Library/Developer/Frameworks')
    darwin_sdk_paths = (
        '/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs',
        '/Developer/SDKs',
        darwin_sdk_dl_path,
    )
else:
    darwin_sdk_dl_path = os.path.join(os.getenv('XDG_DATA_HOME', '~/.local/share'), 'SDKs')
    darwin_sdk_paths = (darwin_sdk_dl_path,)

darwin_download = threading.Lock()
darwin_versions = {
    '10.1': ('10.1.5', 1010),
    '10.1.5': ('10.1.5', 1010),
    '10.2': ('10.2.8', 1020),
    '10.2.8': ('10.2.8', 1020),
    '10.3': ('10.3.9', 1030),
    '10.3.0': ('10.3.0', 1030),
    '10.3.9': ('10.3.9', 1030),
    '10.4': ('10.4u', 1040),
    '10.5': ('10.5', 1050),
    '10.6': ('10.6', 1060),
    '10.7': ('10.7', 1070),
    '10.8': ('10.8', 1080),
    '10.9': ('10.9', 1090),
    '10.10': ('10.10', 100000),
    '10.11': ('10.11', 101100),
}

darwin_sdk_url = 'https://github.com/phracker/MacOSX-SDKs/releases/download/MacOSX10.11.sdk/MacOSX%s.sdk.tar.xz'


def dl_progress(nvim, msg):
    nvim.async_call(lambda n, m: n.eval('clang2#status(%r)' % m),
                    nvim, msg)


def download_sdk(nvim, version):
    with darwin_download:
        dest = tempfile.NamedTemporaryFile('wb', delete=False)
        chunk = 16 * 1024
        try:
            r = urlopen(darwin_sdk_url % version)
            last = time.time()
            dl_bytes = 0
            while True:
                buf = r.read(chunk)
                if not buf:
                    break
                dest.write(buf)
                dl_bytes += len(buf)

                if time.time() - last >= 1:
                    dl_progress(nvim,
                                'Downloading MacOSX%s.sdk (%d bytes)'
                                % (version, dl_bytes))
                    last = time.time()

            dl_progress(nvim,
                        'Extracting MacOSX%s.sdk to %s'
                        % (version, darwin_sdk_dl_path))
            dest.close()

            with tarfile.open(dest.name) as fp:
                fp.extractall(darwin_sdk_dl_path)
        except Exception as e:
            dl_progress('Error downloading SDK: %s' % e)
        finally:
            dest.remove()


class Source(Base):
    def __init__(self, nvim):
        super(Source, self).__init__(nvim)
        self.clang_path = ''
        self.min_pattern_length = 0
        self.nvim = nvim
        self.name = 'clang2'
        self.mark = '[clang]'
        self.rank = 500
        self.bad_flags = []
        self.clang_flags = {}
        self.pch_flags = {}
        self.filetypes = ['c', 'cpp', 'objc', 'objcpp']
        self.db_files = {}
        self.last = {}
        self.scope_completions = []
        self.user_flags = {}
        self.sys_includes = {}
        self.darwin_version = 0
        self.last_neomake_flags = set()

    def on_event(self, context, filename=''):
        if context['event'] == 'BufWritePost':
            self.find_db_flags(context)
            self.last = {}
            self.scope_completions = []

        self.clang_path = context['vars'].get(
            'deoplete#sources#clang#executable', 'clang')

        if context['vars'].get('deoplete#sources#clang#autofill_neomake', 1):
            cmd, flags = self.build_flags(context)
            if context['filetype'] == 'cpp':
                cmd += ['-stdlib=libc++']
            neomake_flags = set(cmd + flags)
            if self.last_neomake_flags ^ neomake_flags:
                self.last_neomake_flags = neomake_flags
                self.nvim.async_call(lambda n, m:
                                     n.eval('clang2#set_neomake_cflags(%r)' % m),
                                     self.nvim, cmd + flags)

    def get_complete_position(self, context):
        m = re.search(r'^\s*#(?:include|import)\s+["<]', context['input'])
        if m:
            context['clang2_include'] = m.group(0)
            return m.end()

        pat = r'->|\.'
        ft = context.get('filetype', '')
        objc = ft in ('objc', 'objcpp')
        if objc:
            pat += r'|[:@\[]|(?:\S\s+)'
        elif ft == 'cpp':
            pat += r'|::'
        pat = r'(?:' + pat + ')'
        context['clang2_pattern'] = pat

        m = re.search(r'(' + pat + r')(\w*?)$', context['input'])
        if m is not None:
            if objc and m.group(1) == '@':
                return m.start(1) - 1
            return m.start(2)
        return re.search(r'\w*$', context['input']).start()

    def find_file(self, path, filename):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in repo_dirs]
            for file in files:
                if file == filename:
                    return os.path.join(root, file)
        return None

    def clean_flags(self, flags):
        if isinstance(flags, str):
            flags = shlex.split(flags, comments=True, posix=True)

        home = os.path.expanduser('~')
        out = []
        for i, flag in enumerate(flags):
            flag = os.path.expandvars(flag)
            if flag.startswith('-darwin='):
                self.darwin_version = darwin_versions.get(flag.split('=', 1)[1])
                continue

            if flag.startswith('~') or \
                    ('~' in flag and
                     re.match(r'(-[IDF]|' + flag_pattern + r')', flag)):
                flag = flag.replace('~', home)
            out.append(flag)

        self.debug('cleaned flags: %r', out)
        return out

    def get_clang_flags(self, lang):
        """Get the default flags used by clang.

        XXX: Not exactly sure why, but using -fsyntax-only causes clang to not
        search the default include paths.  Maybe my setup is busted?
        """
        if lang in self.clang_flags:
            return self.clang_flags[lang]
        flags = []
        clang_flags = ['-fsyntax-only', '-x', lang]
        if lang == 'c++':
            clang_flags.append('-stdlib=libc++')
        clang_flags.extend(['-', '-v'])
        stdout = self.call_clang([], clang_flags, True)

        for item in re.finditer(r'(' + flag_pattern + ')\s*(\S+)',
                                ' '.join(stdout)):
            flag = item.group(1)
            val = item.group(2)
            if not os.path.exists(val):
                continue

            f = '%s%s' % (flag, val)
            if f not in flags:
                flags.append(f)
        self.clang_flags[lang] = self.clean_flags(flags)
        return self.clang_flags[lang]

    def parse_clang_flags_file(self, filename):
        """Parse a .clang file."""
        try:
            with open(filename, 'rt') as fp:
                return self.clean_flags(fp.read())
        except IOError:
            return []

    def get_user_flags(self, context):
        """Get flags from the .clang file or return flags from Vim."""
        cwd = context['cwd']
        flags = context['vars'].get('deoplete#sources#clang#flags', [])

        if cwd in self.user_flags:
            if self.user_flags[cwd]:
                return self.parse_clang_flags_file(self.user_flags[cwd])
            return self.clean_flags(flags)

        parent = cwd
        last_parent = ''
        while parent != last_parent:
            file = os.path.join(parent, '.clang')
            if os.path.isfile(file):
                self.user_flags[cwd] = file
                return self.parse_clang_flags_file(file)

            if set(os.listdir(parent)).isdisjoint(repo_dirs):
                # We're at an apparent project root.
                break

            last_parent = parent
            parent = os.path.dirname(parent)

        self.user_flags[cwd] = None
        return self.clean_flags(flags)

    def call_clang(self, src, cmd, ret_stderr=False, cwd=None):
        """Call clang to do something.

        This will call clang up to 5 times if it reports that unknown arguments
        are used.  On each pass, the offending arguments are removed and
        rembmered.

        In my opinion, this is acceptable since we aren't interested in
        compiling a working binary.  This would allow you to copy and paste
        your existing compile flags (for the most part) without needing to
        worry about what does or doesn't work for getting completion.
        """
        stdout = ''
        stderr = ''
        retry = 5

        cmd = [self.clang_path] + [arg for arg in cmd
                                   if arg not in self.bad_flags]

        # Retry a couple times if 'unknown argument' is encountered because I
        # just want completions and I don't care how they're obtained as long
        # as its useful.
        while retry > 0:
            self.debug('Command: %r', ' '.join(cmd))
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, cwd=cwd)
            source = '\n'.join(src).encode('utf8')
            if len(src) and source[-1] != b'\n':
                source += b'\n'
            out, err = p.communicate(source)
            stderr = err.decode('utf8')
            if 'unknown argument' in stderr:
                for bad in re.finditer(r"unknown argument: '([^']+)'", stderr):
                    arg = bad.group(1)
                    self.debug('Removing argument: %r', arg)
                    if arg not in self.bad_flags:
                        self.bad_flags.append(arg)
                    if arg not in cmd:
                        break
                    while cmd.count(arg):
                        cmd.remove(arg)
                retry -= 1
                continue
            elif self.debug_enabled and stderr.strip():
                # This can be really spammy.
                self.debug('stderr: %s', stderr)

            stdout = out.decode('utf8')
            break

        if ret_stderr:
            return stderr.split('\n')
        return stdout.split('\n')

    def find_db_flags(self, context):
        """Find the compile_commands.json file."""
        cwd = context.get('cwd', '')
        bufname = context.get('bufname', '')
        absname, _ = os.path.splitext(os.path.join(cwd, bufname))

        if cwd in self.db_files:
            return self.db_files[cwd]['entries'].get(absname)

        db_file = self.find_file(cwd, 'compile_commands.json')
        if db_file is None:
            return None

        entries = {}

        with open(db_file, 'rt') as fp:
            try:
                flags = []
                for entry in json.load(fp):
                    directory = entry.get('directory', cwd)
                    file, ext = os.path.splitext(entry.get('file', ''))
                    for item in re.finditer(r'(-[IDFW]|' + flag_pattern +
                                            ')\s*(\S+)', entry.get('command')):
                        flag = item.group(1)
                        val = item.group(2)

                        if flag not in ('-D', '-W'):
                            val = os.path.normpath(os.path.join(directory, val))

                        f = flag + val
                        if f not in flags:
                            flags.append(f)
                    # The db is assumed to be as good as it gets.  Don't pass
                    # it through clean_flags.
                    entries[file] = flags
            except:
                raise

        self.db_files[cwd] = {
            'file': db_file,
            'entries': entries,
        }

        return entries.get(absname)

    def generate_pch(self, context, cmd, flags):
        """Find a *-Prefix.pch file and generate the pre-compiled header.

        It is written to the temp directory and is cached according to the
        flags used to generate it.
        """
        cwd = context.get('cwd', '')

        if not os.path.exists(pch_cache):
            os.makedirs(pch_cache)

        hflags = hashlib.sha1()
        for f in chain(cmd, flags):
            hflags.update(f.encode('utf8'))

        if not cwd:
            return cmd, flags

        for pch in glob.glob(os.path.join(cwd, '*-Prefix.pch')):
            h = hflags.copy()
            h.update(pch.encode('utf8'))
            name = '%s.%s.h' % (os.path.basename(pch), h.hexdigest())
            generated = os.path.join(pch_cache, name)

            if not os.path.exists(generated) or \
                    os.path.getmtime(pch) > os.path.getmtime(generated):
                self.call_clang([], ['-cc1'] + cmd + flags +
                                [pch, '-emit-pch', '-o', generated])
            if os.path.exists(generated):
                cmd += ['-include-pch', generated]
                break

        return cmd, flags

    def parse_completion(self, item):
        name = item
        ctype = ''
        info = ''
        if ' : ' in item:
            name, comp = name.split(' : ', 1)
        else:
            comp = name

        if name == 'Pattern':
            if comp.startswith('[#'):
                i = comp.find('#]')
                if i != -1:
                    ctype = comp[2:i]
                    comp = comp[i+2:]
            comp = re.sub(r'(\S)\(', r'\1 (', re.sub(r'\)(\S)', r') \1', comp))
            name = comp
            info = re.sub(r'<#([^#]+)#>', r'\1', comp)
        else:
            if comp.startswith('[#'):
                i = comp.find('#]')
                if i != -1:
                    ctype = comp[2:i]
                    comp = comp[i+2:]

            if comp.endswith('#]'):
                i = comp.rfind('[#')
                if i != -1:
                    comp = comp[:i]

            if comp.endswith(')'):
                info = re.sub(r'<#([^#]+)#>', r'\1', comp)

            if ctype != '':
                info = '(%s)%s' % (ctype, info)

        return {
            'word': comp,
            'abbr': name,
            'kind': ctype,
            'info': info,
            'icase': 1,
            'dup': 1,
        }

    def apply_darwin_flags(self, version, flags):
        sdk_name = 'MacOSX%s.sdk' % version[0]
        sdk_path = ''
        for p in darwin_sdk_paths:
            p = os.path.join(p, sdk_name)
            if os.path.isdir(p):
                sdk_path = p
                break

        if not sdk_path:
            if darwin_download.acquire(False):
                darwin_download.release()
                t = threading.Thread(target=download_sdk, args=(self.nvim, version[0]))
                t.daemon = True
                t.start()
            return flags

        return flags + [
            '-D__MACH__',
            '-D__MAC_OS_X_VERSION_MAX_ALLOWED=%d' % version[1],
            '-D__APPLE_CPP__',
            '-DTARGET_CPU_X86_64',
            '-fblocks',
            '-fasm-blocks',
            '-fno-builtin',
            '-isysroot%s' % sdk_path,
            '-iframework%s' % os.path.join(sdk_path, 'System/Library/Frameworks'),
            '-isystem%s' % os.path.join(sdk_path, 'usr/include'),
        ]

    def build_flags(self, context):
        filetype = context.get('filetype', '')
        cmd = ['-x']
        lang = lang_names.get(filetype)
        if not lang:
            return []
        std = context['vars'].get(
            'deoplete#sources#clang#std', {}).get(filetype)
        if not std:
            std = std_default.get(filetype)

        cmd = ['-x', lang]
        std = '-std=%s' % std

        flags = self.get_user_flags(context)

        if self.darwin_version:
            flags = self.apply_darwin_flags(self.darwin_version, flags)

        flags = self.get_clang_flags(lang) + flags
        db_flags = self.find_db_flags(context)
        if db_flags:
            flags = db_flags + flags

        if not any(True for x in flags if x.startswith('-std=')):
            cmd.append(std)

        return cmd, flags

    def _gather_sys_includes(self, flag, path, seen):
        """#include <> files from compiler include flags."""
        if path in self.sys_includes:
            yield from filter(lambda x: x['word'] not in seen,
                              self.sys_includes[path])
            return

        headers = []

        if flag == '-F' or 'framework' in flag:
            for framework in os.listdir(path):
                name = framework
                if name.endswith('.framework'):
                    name = name[:-10]
                fw_path = os.path.join(path, framework, 'Headers') + '/'
                if not os.path.exists(fw_path):
                    continue

                for root, dirs, files in os.walk(fw_path):
                    dirs[:] = list(sorted([d for d in dirs if d not in repo_dirs]))
                    for file in sorted(files):
                        if not file.endswith('.h'):
                            continue
                        full_path = os.path.join(root, file)
                        include_path = os.path.join(name,
                                                    full_path[len(fw_path):])
                        item = {'word': include_path, 'kind': 'sys'}
                        headers.append(item)
                        if include_path not in seen:
                            seen.add(include_path)
                            yield item
        else:
            for root, dirs, files in os.walk(path):
                dirs[:] = list(sorted([d for d in dirs if d not in repo_dirs]))

                for file in sorted(files):
                    if not file.endswith('.h'):
                        continue
                    include_path = os.path.join(root, file)[len(path)+1:]
                    item = {'word': include_path, 'kind': 'sys'}
                    headers.append(item)
                    if include_path not in seen:
                        seen.add(include_path)
                        yield item

        self.sys_includes[path] = headers

    def _gather_local_includes(self, context, seen):
        """#include "" files relative to the current buffer."""
        path = os.path.dirname(context.get('bufname', ''))
        l = len(path)
        for root, dirs, files in os.walk(path):
            dirs[:] = list(sorted([d for d in dirs if d not in repo_dirs]))
            for file in sorted(files):
                if not file.endswith('.h'):
                    continue
                include_path = os.path.join(root, file)[l:].lstrip('/')
                seen.add(include_path)
                yield {'word': include_path, 'kind': 'dir'}

    def gather_includes(self, context):
        seen = set()

        # Exclude already imported files
        src = '\n'.join(self.nvim.current.buffer[:5000])
        seen.update(x[1:-1] for x in re.findall(
            r'^\s*#(?:include|import) ((?:"[^"]+")|(?:<[^>]+>))$', src, re.M))

        if context['clang2_include'][-1] == '"':
            yield from self._gather_local_includes(context, seen)

        _, flags = self.build_flags(context)
        for item in re.finditer(r'(-[IF]|' + flag_pattern +
                                ')\s*(\S+)', ' '.join(flags)):
            yield from self._gather_sys_includes(item.group(1), item.group(2),
                                                 seen)

    def gather_candidates(self, context):
        self.darwin_version = 0

        if 'clang2_include' in context:
            return list(self.gather_includes(context))

        input = context['input']
        filetype = context.get('filetype', '')
        complete_str = context['complete_str']
        min_length = context['vars'].get(
            'deoplete#auto_complete_start_length', 2)
        pattern = context.get('clang2_pattern')
        length_exemption = pattern and re.search(pattern + r'$', input)

        if not length_exemption and len(complete_str) < min_length:
            # Since the source doesn't have a global pattern, its our
            # responsibility to honor the user settings.
            return []

        pos = context['complete_position']
        line = context['position'][1]
        last_input = self.last.get('input', '')
        same_line = self.last.get('line', 0) == line

        # Completions from clang will include all results that are relevant to
        # a delimiter position--not just the current word completion.  This
        # means the results can be reused to drastically reduce the completion
        # time.
        if same_line and self.last.get('col', 0) == pos:
            self.debug('Reusing previous completions')
            return self.last.get('completions', [])

        # Additionally, if the completion is happeing in a position that will
        # result in completions for the current scope, reuse it.
        scope_pos = re.search(r'(?:\s+|(?:[\[\(:])\s*|@)$', input)

        # Check objc where spaces can be significant.
        scope_reuse = (filetype not in ('objc', 'objcpp') or
                       (input != last_input and
                        input.rstrip() == last_input.rstrip()))

        if scope_reuse and same_line and scope_pos and self.scope_completions:
            self.debug('Reusing scope completions')
            return self.scope_completions

        buf = self.nvim.current.buffer
        src = buf[:]
        max_lines = context['vars'].get(
            'deoplete#sources#clang#preproc_max_lines', 50)
        if max_lines:
            for i, l in enumerate(reversed(src[max(0, line-max_lines):line])):
                l = l.lstrip()
                if l.startswith('#'):
                    l = l.lstrip('# ')
                    if l.startswith('ifdef'):
                        self.debug('Ignoring preproc line %d', line - i)
                        src[line - i - 1] = ''
                        break
                    elif l.startswith('endif'):
                        self.debug('Stopped preproc search on line %d',
                                   line - i)
                        break

        code_flags = [
            '-code-completion-macros',
            '-code-completion-patterns',
            # '-code-completion-brief-comments',  - Not very useful atm.
            '-code-completion-at=-:%d:%d' % (line, pos+1),
        ]

        cmd, flags = self.build_flags(context)
        cmd, flags = self.generate_pch(context, cmd, flags)

        completions = []
        cmd = (['-cc1', '-fsyntax-only'] + cmd +
               code_flags + flags + ['-O0', '-w'] + ['-'])

        pattern = ''

        for item in self.call_clang(src, cmd, cwd=os.path.dirname(buf.name)):
            if item.startswith('COMPLETION:'):
                if pattern:
                    completions.append(self.parse_completion(pattern))
                    pattern = ''

                item = item[11:].strip()
                if item.startswith('Pattern :'):
                    pattern = item
                    continue
                completions.append(self.parse_completion(item))
            elif pattern:
                pattern += item

        if pattern:
            completions.append(self.parse_completion(pattern))

        self.last = {
            'input': input,
            'line': line,
            'col': pos,
            'completions': completions,
        }

        if scope_pos:
            self.scope_completions = completions

        return completions
