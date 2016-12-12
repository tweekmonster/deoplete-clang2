function! clang2#dl_progress(msg) abort
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
  stopinsert
  execute "normal! ".s:select_placeholder('n', 0)
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

  " Not sure why, but after completion, the ending cursor position is off by
  " one.
  let p[2] = e + (a:dir == 0 ? 2 : 1)
  let p2 = copy(p)

  return [p1, p2]
endfunction


function! s:select_placeholder(mode, dir) abort
  if a:dir == 0
    let orig_key = ''
  else
    let orig_key = a:dir == -1 ? "\<c-p>" : "\<c-n>"
  endif

  if a:dir != 0 && exists('b:clang2_orig_maps')
    let saved_key = b:clang2_orig_maps[a:mode][a:dir == -1 ? 1 : 0]
    if !empty(saved_key)
      let orig_key = saved_key
    endif
  endif

  if pumvisible()
    return orig_key
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


function! clang2#init() abort
  if exists('b:did_clang2')
    return
  endif

  let b:did_clang2 = 1

  augroup clang2
    autocmd! * <buffer>
    autocmd CompleteDone <buffer> call clang2#after_complete()
  augroup END


  " Original map args to use when there's no placeholders
  let b:clang2_orig_maps = {
        \ 's': [s:maparg("\<c-n>", 's'), s:maparg("\<c-p>", 's')],
        \ 'n': [s:maparg("\<c-n>", 'n'), s:maparg("\<c-p>", 'n')],
        \ 'i': [s:maparg("\<c-n>", 'i'), s:maparg("\<c-p>", 'i')],
        \ }


  snoremap <silent><buffer><expr> <c-n> <sid>select_placeholder('s', 1)
  snoremap <silent><buffer><expr> <c-p> <sid>select_placeholder('s', -1)
  nnoremap <silent><buffer><expr> <c-n> <sid>select_placeholder('n', 1)
  nnoremap <silent><buffer><expr> <c-p> <sid>select_placeholder('n', -1)
  inoremap <silent><buffer><expr> <c-n> <sid>select_placeholder('i', 1)
  inoremap <silent><buffer><expr> <c-p> <sid>select_placeholder('i', -1)
endfunction
