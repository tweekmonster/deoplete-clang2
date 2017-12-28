<h1>deoplete-clang2<br>
&nbsp;&nbsp;&nbsp;<sup><em><code>Electric Boogaloo</code></em></sup></h1>

This is a `clang` completer for [deoplete.nvim][] that's faster than
[deoplete-clang][].  Instead of using `libclang`, it just uses `clang -cc1`
like most other `clang` plugins.  Unlike other plugins, Objective-C was given a
little more attention.

![](https://cloud.githubusercontent.com/assets/111942/21212064/1851c006-c257-11e6-83a4-a3a96482ceaf.gif)

If you are like me, you:

- want completions to be relatively easy to setup
- are not entirely sure how to use `clang -cc1`
- just want the damned completions
  - for Objective-C
    - with the ability to fill in method arguments without having an aneurysm
    - and type `]` to wrap method calls (within reason)
      - (you also think Xcode's method of doing this sucks)
    - also, magically get completions for the MacOSX SDKs
      - without Xcode
        - on Linux

This was developed mainly to scratch an old itch.  I'm currently not committed
to continuing development beyond fixing obvious bugs.  Pull requests to add
useful features are welcome, though.

With that said, you may want to keep an eye on [clang-server][] that @zchee is
working on.

## Requirements

- [Neovim][] or vim8  with if_python3
- [deoplete.nvim][]
- `clang`

I'm using `clang 3.8.0`.  Lower versions may work, but are untested.

**Vim8 support:**

- install [nvim-yarp](https://github.com/roxma/nvim-yarp) plugin for Vim8. 
- install neovim python client: `pip install neovim`
- install [vim-hug-neovim-rpc](https://github.com/roxma/vim-hug-neovim-rpc) plugin for Vim8. 


## Install

Follow your package manager's instructions.


## Usage

Completions will insert functions with argument placeholders in the form of
`<#Type var#>`.  While the cursor is on a line with one of these placeholders,
pressing `<tab>` will enter select mode with the next placeholder selected.
Pressing `<tab>` again will move to the next placeholder and pressing `<s-tab>`
will cycle backwards.

In Objective-C sources, pressing `]` will try to place a `[` in the appropriate
place.  While it isn't perfect, it's a whole lot better than how Xcode works.
You will have the best results by avoiding nested multi-argument method calls.


## Config

**Note:** For simple projects, you probably don't need to configure anything.  You
definitely shouldn't need to configure anything if your project uses a
[compilation database][].

Create a `.clang` file at your project root.  You should be able to just paste
most of your compile flags in there (the parts that make sense at least).
Mainly, it should have the relevant `-I`, `-D`, `-F` flags.  The plugin will
try to fill in the blanks for system include paths and discard the flags that
are causing completions to not work.

You can also use `let g:deoplete#sources#clang#flags = ['-Iwhatever', ...]` in
your nvim configs.

`g:deoplete#sources#clang#executable` sets the path to the `clang` executable.

`g:deoplete#sources#clang#autofill_neomake` is a boolean that tells this plugin
to fill in the `g:neomake_<filetype>_clang_maker` variable with the `clang`
executable path and flags.  You will still need to enable it with
`g:neomake_<filetype>_enabled_makers = ["clang"]`.

`g:deoplete#sources#clang#std` is a dict containing the standards you want to
use.  It's not used if you already have `-std=whatever` in your flags.  The
defaults are:

```
{
    'c': 'c11',
    'cpp': 'c++1z',
    'objc': 'c11',
    'objcpp': 'c++1z',
}
```

`g:deoplete#sources#clang#preproc_max_lines` sets the maximum number of lines to
search for a `#ifdef` or `#endif` line.  `#ifdef` lines are discarded to get
completions within conditional preprocessor blocks.  The default is `50`,
setting it to `0` disables this feature.

### MacOSX10.`_` SDK completions

(You may find it funny that I haven't tested this on macOS)

Just add `-darwin=10.XX` to your flags (where `XX` is the release, e.g.
`10.8`).  It will be turned into the following flags:

```
-D__MACH__
-D__MAC_OS_X_VERSION_MAX_ALLOWED=10XX
-D__APPLE_CPP__
-DTARGET_CPU_X86_64
-fblocks
-fasm-blocks
-fno-builtin
-isysroot<sdk_path>
-iframework<sdk_path>/System/Library/Frameworks
-isystem<sdk_path>/usr/include
```

The above is the minimum flags to get SDK completions without clang spewing a
litany of errors.  If you're working on a simple project, `-darwin=10.XX`
should be the only flag you need.

On macOS, the following directories are searched for the SDK:

- `/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs`
- `/Developer/SDKs`
- `~/Library/Developer/Frameworks` (download destination)

On non-macOS:

- `$XDG_DATA_HOME/SDKs` or `~/.local/share/SDKs` (download destination)

If the SDK is not found on the system or SDK paths, it will be downloaded from
[phracker/MacOSX-SDKs][] in the background.


[deoplete.nvim]: https://github.com/Shougo/deoplete.nvim
[deoplete-clang]: https://github.com/zchee/deoplete-clang
[clang-server]: https://github.com/zchee/clang-server
[Neovim]: https://github.com/neovim/neovim
[compilation database]: http://clang.llvm.org/docs/JSONCompilationDatabase.html
[phracker/MacOSX-SDKs]: https://github.com/phracker/MacOSX-SDKs
