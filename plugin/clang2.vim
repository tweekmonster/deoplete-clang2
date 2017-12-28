augroup clang2
  autocmd!
  autocmd FileType c,cpp,objc,objcpp call clang2#init()
augroup END

if has('nvim')
  if empty(remote#host#PluginsForHost('clang2-rplugin'))
    let s:path = expand('<sfile>:p:h:h')

    " This seems a bit greedy, but it prevents blocking while the main python3
    " provider is dealing with completions.  Deoplete might be the one that needs
    " to run in a Python3 clone.
    call remote#host#RegisterClone('clang2-rplugin', 'python3')

    " rplugin is not placed in rplugin/python3 so that it won't be added to the
    " manifiest when :UpdateRemotePlugins is called.
    call remote#host#RegisterPlugin('clang2-rplugin', s:path.'/rplugin/clang2', [
          \ {'sync': v:true, 'name': 'Clang2_objc_close_brace', 'type': 'function', 'opts': {}},
          \ ])
  endif
else
  let s:foo = yarp#py3('clang2_wrap')
  function! Clang2_objc_close_brace(v) abort
    return s:foo.call('close_objc_brace', a:v)
  endfunction
endif
