let s:pl_prev = get(g:, 'clang2_placeholder_prev', '<s-tab>')
let s:pl_next = get(g:, 'clang2_placeholder_next', '<tab>')

function! clang2#status(msg) abort
  echo '[deoplete-clang2]' a:msg
endfunction

function! clang2#after_complete() abort
  if !exists('v:completed_item') || empty(v:completed_item)
    return
  endif

  if v:completed_item.word !~# '<#.*#>'
    return
  endif
  call cursor(line('.'), col('.') - strlen(v:completed_item.word))
  call feedkeys(s:select_placeholder('n', 0), 'n')
endfunction


function! s:noop_postprocess(msg) abort
  " Don't allow the whitespace to be compressed to preserve the alignment of
  " Fix-It hints.
  return a:msg
endfunction


function! clang2#set_neomake_cflags(flags) abort
  if exists(':Neomake') != 2
    return
  endif

  if !exists('g:neomake_'.&filetype.'_clang_maker')
    let g:neomake_{&filetype}_clang_maker = neomake#makers#ft#c#clang()
  endif

  let m = g:neomake_{&filetype}_clang_maker
  if !has_key(m, 'orig_args')
    let m.orig_args = copy(m.args)
  endif

  let m.postprocess = function('s:noop_postprocess')

  let m.args = ['-fsyntax-only']
  if &filetype =~# 'objc'
    " Pretty much a copy and paste of Xcode's warning flags.
    let m.args += [
          \ '-fmessage-length=0',
          \ '-Wno-objc-property-implementation',
          \ '-Wno-objc-missing-property-synthesis',
          \ '-Wnon-modular-include-in-framework-module',
          \ '-Werror=non-modular-include-in-framework-module',
          \ '-Wno-trigraphs',
          \ '-fpascal-strings',
          \ '-fno-common',
          \ '-Wno-missing-field-initializers',
          \ '-Wno-missing-prototypes',
          \ '-Werror=return-type',
          \ '-Wdocumentation',
          \ '-Wunreachable-code',
          \ '-Wno-implicit-atomic-properties',
          \ '-Werror=deprecated-objc-isa-usage',
          \ '-Werror=objc-root-class',
          \ '-Wno-arc-repeated-use-of-weak',
          \ '-Wduplicate-method-match',
          \ '-Wno-missing-braces',
          \ '-Wparentheses',
          \ '-Wswitch',
          \ '-Wunused-function',
          \ '-Wno-unused-label',
          \ '-Wno-unused-parameter',
          \ '-Wunused-variable',
          \ '-Wunused-value',
          \ '-Wempty-body',
          \ '-Wconditional-uninitialized',
          \ '-Wno-unknown-pragmas',
          \ '-Wno-shadow',
          \ '-Wno-four-char-constants',
          \ '-Wno-conversion',
          \ '-Wconstant-conversion',
          \ '-Wint-conversion',
          \ '-Wbool-conversion',
          \ '-Wenum-conversion',
          \ '-Wshorten-64-to-32',
          \ '-Wpointer-sign',
          \ '-Wno-newline-eof',
          \ '-Wno-selector',
          \ '-Wno-strict-selector-match',
          \ '-Wundeclared-selector',
          \ '-Wno-deprecated-implementations',
          \ '-fasm-blocks',
          \ '-fstrict-aliasing',
          \ '-Wprotocol',
          \ '-Wdeprecated-declarations',
          \ '-Wno-sign-conversion',
          \ '-Winfinite-recursion',
          \ ]
  endif

  let m.args += filter(copy(a:flags), 'v:val !~# "^-internal"')
  if exists('g:deoplete#sources#clang#executable')
    let m.exe = g:deoplete#sources#clang#executable
  else
    let m.exe = 'clang'
  endif
endfunction


function! s:find_placeholder(dir) abort
  let text = getline('.')
  let p1 = []
  let p2 = []

  if text !~# '<#.*#>'
    return [p1, p2]
  endif

  let p = getcurpos()
  let origin = p[2]
  if origin >= len(text) - 1
    let origin = 0
  endif

  if a:dir == -1
    let s = origin
    for _ in range(2)
      let s = match(text, '.*\zs<#.\{-}\%<'.s.'c')
      if s == -1
        let s = match(text, '.*\zs<#')
      endif
    endfor
  else
    let s = match(text, '<#', match(text, '<#', origin) == -1 ? 0 : origin)
  endif

  let e = match(text, '#\zs>', s)

  if s == -1 || e == -1
    return [p1, p2]
  endif

  let p[2] = s + 1
  let p1 = copy(p)

  let p[2] = e + 1
  let p2 = copy(p)

  return [p1, p2]
endfunction


function! s:select_placeholder(mode, dir) abort
  let [p1, p2] = s:find_placeholder(a:dir)
  if empty(p1) || empty(p2)
    if mode() =~? 's\|v' || a:dir == 0
      return ''
    endif

    let key = s:getmap(a:mode, a:dir == -1 ? 0 : 1)
    if !empty(key)
      return key
    endif

    let key = a:dir == -1 ? s:pl_prev : s:pl_next
    if key =~# '^<[^<>]*>$'
      return eval('"\'.key.'"')
    endif

    return key
  endif

  call setpos("'<", p1)
  call setpos("'>", p2)

  let vkeys = 'gvze'
  if visualmode() ==# 'V'
    let vkeys = 'gvvze'
  endif

  if a:mode ==# 's'
    return "\<c-g>" . vkeys . "\<c-g>"
  endif

  return "\<esc>" . vkeys . "\<c-g>"
endfunction


function! clang2#_cl_meth(line, col) abort
  let [l, c] = getpos('.')[1:2]
  if a:line == l
    let c += 1
  endif

  call cursor(a:line, a:col)
  undojoin
  normal! i[
  call cursor(l, c)
endfunction


function! s:close_brace() abort
  if &filetype !~# '\<objc'
    let m = s:getmap(']', 0)
    if empty(m)
      return ']'
    endif

    return m
  endif

  let [l, c] = Clang2_objc_close_brace(line('.'), col('.'))
  if l != 0
    return "\<c-g>u]\<c-\>\<c-o>:call clang2#_cl_meth(".l.",".c.")\<cr>"
  endif

  let m = s:getmap(']', 0)
  if empty(m)
    return ']'
  endif

  return m
endfunction

" Parse a map arg
function! s:maparg(map, mode, ...) abort
  let default = {'expr': 0, 'rhs': a:0 ? a:1 : substitute(a:map,
        \ '\(\\\@<!<[^>]\+>\)',
        \ '\=eval(''"\''.submatch(1).''"'')', 'g')}
  let arg = maparg(a:map, a:mode, 0, 1)
  if empty(arg)
    return default
  endif

  while arg.rhs =~? '^<Plug>'
    let arg = maparg(arg.rhs, a:mode, 0, 1)
    if empty(arg)
      return default
    endif
  endwhile

  let m = {
        \ 'rhs': substitute(arg.rhs, '\c<sid>', "\<SNR>" . arg.sid . '_', 'g'),
        \ 'expr': arg.expr,
        \ }
  let m.rhs = substitute(m.rhs,
        \ '\(\\\@<!<[^>]\+>\)',
        \ '\=eval(''"\''.submatch(1).''"'')', 'g')
  return m
endfunction


function! s:getmap(mode, map) abort
  if !exists('b:clang2_orig_maps')
    return ''
  endif

  let mode = get(b:clang2_orig_maps, a:mode, [])
  if a:map < 0 || a:map >= len(mode)
    return a:map
  endif

  let m = mode[a:map]

  if empty(m)
    return ''
  endif

  if m.expr
    return eval(m.rhs)
  endif

  return m.rhs
endfunction


function! s:steal_keys() abort
  if exists('b:clang2_orig_maps')
    return
  endif

  if exists('g:UltiSnipsRemoveSelectModeMappings')
        \ && g:UltiSnipsRemoveSelectModeMappings
    " We must hide our criminal activities from UltiSnips since it's the world
    " police on select maps, apparently.
    let ignored = get(g:, 'UltiSnipsMappingsToIgnore', [])
    call add(ignored, 'deoplete-clang2')
    let g:UltiSnipsMappingsToIgnore = ignored
  endif

  " Original map args to use when there's no placeholders
  let b:clang2_orig_maps = {
        \ 's': [s:maparg(s:pl_prev, 's'), s:maparg(s:pl_next, 's')],
        \ 'n': [s:maparg(s:pl_prev, 'n'), s:maparg(s:pl_next, 'n')],
        \ 'i': [s:maparg(s:pl_prev, 'i'), s:maparg(s:pl_next, 'i')],
        \ ']': [s:maparg(']', 'i', ']')],
        \ }

  execute 'snoremap <silent><buffer><expr> '.strtrans(s:pl_next).' <sid>select_placeholder("s", 1)'
  execute 'snoremap <silent><buffer><expr> '.strtrans(s:pl_prev).' <sid>select_placeholder("s", -1)'
  execute 'nnoremap <silent><buffer><expr> '.strtrans(s:pl_next).' <sid>select_placeholder("n", 1)'
  execute 'nnoremap <silent><buffer><expr> '.strtrans(s:pl_prev).' <sid>select_placeholder("n", -1)'
  execute 'inoremap <silent><buffer><expr> '.strtrans(s:pl_next).' <sid>select_placeholder("i", 1)'
  execute 'inoremap <silent><buffer><expr> '.strtrans(s:pl_prev).' <sid>select_placeholder("i", -1)'

  inoremap <silent><buffer><expr> ] <sid>close_brace()

  autocmd! clang2 InsertEnter <buffer>
endfunction


function! clang2#init() abort
  if exists('b:did_clang2')
    return
  endif

  let b:did_clang2 = 1

  augroup clang2
    autocmd! * <buffer>
    autocmd CompleteDone <buffer> call clang2#after_complete()
    autocmd InsertEnter <buffer> call s:steal_keys()
  augroup END
endfunction
