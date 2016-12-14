let s:pl_prev = get(g:, 'clang2_placeholder_prev', '<s-tab>')
let s:pl_next = get(g:, 'clang2_placeholder_next', '<tab>')

function! clang2#status(msg) abort
  echo '[deoplete-clang2]' a:msg
endfunction

function! clang2#after_complete() abort
  if !exists('v:completed_item') || empty(v:completed_item)
    return
  endif

  let b:complete_start = [line('.'), col('.') - strlen(v:completed_item.word)]
  if getline('.') !~# '<#.*#>'
    return
  endif
  call feedkeys(s:select_placeholder('n', 0), 'n')
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
  if a:dir == 0
    let orig_key = ''
  else
    let orig_key = a:dir == -1 ? s:pl_prev : s:pl_next
    if orig_key =~# '^<[^<>]*>$'
      let orig_key = eval('"\'.orig_key.'"')
    endif
  endif

  if a:dir != 0 && exists('b:clang2_orig_maps')
    let saved_key = b:clang2_orig_maps[a:mode][a:dir == -1 ? 1 : 0]
    if !empty(saved_key)
      let orig_key = saved_key
    endif
  endif

  let [p1, p2] = s:find_placeholder(a:dir)
  if empty(p1) || empty(p2)
    if mode() =~? 's\|v'
      return ''
    endif
    return orig_key
  endif

  call setpos("'<", p1)
  call setpos("'>", p2)

  if a:mode ==# 's'
    return "\<c-g>gvze\<c-g>"
  endif

  return "\<esc>gvze\<c-g>"
endfunction


" Parse a map arg
function! s:maparg(map, mode) abort
  let arg = maparg(a:map, a:mode)
  return substitute(arg, '\(<[^>]\+>\)', '\=eval(''"\''.submatch(1).''"'')', 'g')
endfunction


function! s:steal_keys() abort
  if exists('b:clang2_orig_maps')
    return
  endif

  " Original map args to use when there's no placeholders
  let b:clang2_orig_maps = {
        \ 's': [s:maparg(s:pl_prev, 's'), s:maparg(s:pl_next, 's')],
        \ 'n': [s:maparg(s:pl_prev, 'n'), s:maparg(s:pl_next, 'n')],
        \ 'i': [s:maparg(s:pl_prev, 'i'), s:maparg(s:pl_next, 'i')],
        \ ']': s:maparg(']', 'i'),
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
