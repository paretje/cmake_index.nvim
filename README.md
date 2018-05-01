# cmake_index.nvim

Core building block for vim as C/C++ IDE.

This plugin starts cmake server for your project, fetches all useful information and exposes to other plugins through API.
See [How to configure cmake_index.nvim to work with...](#how-to-configure-cmake_indexnvim-to-work-with) section at end of this file.

### Why?

Are you bored writting `.clang_complete`, `.ycm_extra_conf.py`, `.clang` and other similar files by hand? Do you want everything to __just work__? You open source file from arbitrary project and every your plugin that require compilation flags just works.
Utopia? No, it's cmake_index.nvim.

### Features

* Fully asynchronous
* Easy to use API

### Limitations

* Only C and C++ support now.
* Only neovim support

## Installation

### Requirements

* Neovim with if_python3

  If `:echo has("python3")` returns 1, then you're done.

* Python 3 client for Neovim

  `pip3 install neovim`

* CMake 3.7 or newer (with server mode support).


### pathogen

```
git clone https://github.com/foxcpp/cmake_index.nvim.git ~/.config/nvim/bundle/cmake_index.nvim
```
Don't forget to run `:UpdateRemotePlugins`!

### Vim-Plug

```vim
Plug 'foxcpp/cmake_index.nvim', { 'do': ':UpdateRemotePlugins' }
```


## Configuration variables

### `g:nvim_cmake_autotrigger`

Run `:Cmake init` when C/C++ file openned.

**Default value:** `1` 


### `g:nvim_cmake_log_level`

Log level.
Valid values: `debug`, `info`, `warning`, `error`, `crticial`.

**Default value:** `info`


### `g:nvim_cmake_binary`

Path to CMake binary.

**Default value:** `/usr/bin/cmake`


### `g:nvim_cmake_build_command`

Template of command to run on `:Cmake build`.

**Default value:** `/usr/bin/cmake --build {build_dir} --target {target}`


### `g:nvim_cmake_default_generator`

Generator to use in new build directory.

**Default value:** `Unix Makefiles`


### `g:nvim_cmake_socket_base`

Template path for CMake server socket. Useful if you have tmpfs mounted in different directory.

**Default value:** `/tmp/nvim_cmake_{pid}_{build_dir}`


### `g:nvim_cmake_persistent_server`

Keep the server running after gathering all useful information.

**Default value:** `1`


### `g:nvim_cmake_default_cpp_flags`

Default flags for C++ sources.

**Default value:** `[ '-std=c++14', '-isystem', '/usr/include/c++/v1', '-isystem', '/usr/local/include', '-isystem', '/usr/include']`


### `g:nvim_cmake_default_c_flags`

Default flags for C sources.

**Default value:** `['-isystem', '/usr/local/include', '-isystem', '/usr/include']`


### `g:nvim_cmake_cpp_source_extensions`

Extensions for C++ source files.

**Default value:** `[ '.cpp', '.cc', '.CPP', '.cxx', '.c++', '.cp' ]`


### `g:nvim_cmake_c_source_extensions`

Extensions for C source files.

**Default value:** `[ '.c' ]`


### `g:nvim_cmake_cpp_header_extensions`

Extensions for C++ header files.

**Default value:** `[ '.hpp', '.h', '.HPP', '.hxx', '.hh', '.h++', '.hp', '.ii' ]`


### `g:nvim_cmake_cpp_header_extensions`

Extensions for C source files.

**Default value:** `[ '.h' ]`


### `g:nvim_cmake_build_dir`

Subdirectories of project root to check when searching for existing build directory.
First value used as new build directory name if none exists.

**Default value:** `[ 'build', '.' ]`


### `g:nvim_cmake_root_files`

If any of these files exist in directory - it's a project root.

**Default value:** `[ 'CMakeLists.txt' ]`


### `g:nvim_cmake_build_pager`

How to run build command.

**Default value:** `'10split + term://{command} | wincmd p'`


### `g:nvim_cmake_run_pager`

How to run executables.

**Default value:** `'30split + term://{command}'`


### `g:nvim_cmake_emit_dotclang`

Generatate `.clang` in directory of openned file to be used by [chromatica.nvim](https://github.com/arakashic/chromatica.nvim).

**Default value:** `0`


### `g:nvim_cmake_emit_dotclangcomplete`

Generatate `.clang_complete` in directory of openned file to be used by various clang-based plugins like [ncm-clang](https://github.com/roxma/ncm-clang).

**Default value:** `0`


### `g:nvim_cmake_emit_compilecommandsjson`

Generate `compile_commands.json` in build directory.

**Note:** In addition to translation units it contains headers because it meant to be used by other plugins.
If you need compilation database with TU's only, then you should use CMake's CMAKE_EXPORT_COMPILE_COMMANDS

**Default value:** `0`

### `g:nvim_cmake_compilecommandsjson_in_root`

Place `compile_commands.json` in project root instead of build directory.

**Default value:** `0`

## Functions

**Note:** All functions accept __absolute__ file path.

### `CmakeGetOpt(<option>)`

Returns configuration option value as seen by plugin (`option` parameter is without `nvim_cmake` prefix!).

### `CmakeFindRootDir([filepath])`

Try to find project root directory for a given file. Returns `v:null` if failed.
`[filename]` defaults to current buffer.


### `CmakeFindBuildDir([filepath])`

Try to find project build directory for a given file. Returns `v:null` if failed.
`[filename]` defaults to current buffer.


### `CmakeQueryFile([build directory], <filepath>)`

Returns pretty complex dictonary with file information as seen by plugin or `v:null` if file is unknown.
This strange params order is for backwards compatability with previous form where build directory was required.


### `CmakeQueryTarget(<build directory>, <target name>)`

Returns pretty complex dictonary with target information as seen by plugin or `v:null` if target is unknown.


### `CmakeQueryTreeInfo(<build directory>)`

Returns pretty complex dictonary with build tree information as seen by plugin or `v:null` if project is unknown.


### `CmakeQueryCache(<build directory>, <variable name>)`

Returns value of specified cache variable or `v:null` if variable doesn't exists.


### `CmakeBuildCommand(<build directory>, <target name>)`

Return build command for specified target.


### `CmakeBlockingInit([root directory], [build directory])`

Initialize project, same as `:Cmake init` command but blocks until initialization completed.


## Commands

### `:Cmake init [root dir] [build dir] [cache variables]`

Initialize project index. Optional arguments override guessed values.
Cache variables is in form `NAME=VALUE`


### `:Cmake reinit [root dir] [build dir] [cache variables]`

Reinitialize project index. Optional arguments override guessed values.
Cache variables is in form `NAME=VALUE`


### `:Cmake run [target] [args]`

Run executable if specified target have one as an artifact. 
Defaults to target of current file.


### `:Cmake build [target]`

Run build command specified target. Defaults to target of current file.


### `:Cmake clear`

Wipe out index and shutdown servers.


## Buffer variables set by plugin

### `b:cmake_tree_build_dir`

Absolute path to build directory. `v:null` if not configured.

### `b:cmake_tree_root_dir`

Absolute path to root directory. `v:null` if not configured.

### `b:cmake_compile_flags`

Compilation flags for file. `g:nvim_cmake_default_flags` if not configured.

### `b:cmake_configured`

Whether plugin obitained information about this file.


## Autocommands

### `CmakeIndexUpdate`

Executed after index update once for each loaded buffer.

Following global variables set before calling doautocmd and unset after:

`g:__cmake_configured` is `v:true` if file information obitained successfully.

Following variables is `v:null` if above is `v:false`:

* `g:__cmake_buffer_number` set to buffer number of updated buffer.
* `g:__cmake_abs_file_path` set to absolute path to updated file.
* `g:__cmake_build_dir` set to build directory.
* `g:__cmake_compile_flags` set to (new) compilation flags for updated file (it's a list, not string!).


### `CmakeBuilding`

Executed when `:Cmake build` called (after terminal buffer openned).
Can be used to customize build log buffer size/position.


## How to configure cmake_index.nvim to work with...  

### [YouCompleteMe](https://github.com/Valloric/YouCompleteMe)

Set `g:ycm_global_ycm_extra_conf` to path to `ycm_extra_conf.py`
in plugin directory.

```vim
let g:ycm_global_ycm_extra_conf = '~/.config/nvim/bundle/cmake_index.nvim/ycm_extra_conf.py'
```


### [clang_complete](https://github.com/Rip-Rip/clang_complete)

Use [`CmakeIndexUpdate`](#cmakeindexupdate) autocommand.

```vim
autocmd User CmakeIndexUpdate setbufvar(g:__cmake_buffer_number, 'clang_user_options', join(g:__cmake_compile_flags))
```

### [Asynchronous Lint Engine](https://github.com/w0rp/ale)

Use [`CmakeIndexUpdate`](#cmakeindexupdate) autocommand.

**Note:** It's important to set flags before enabling ALE because it reads them only once!

I use this in my init.vim:
```vim
let g:ale_enabled = 0
autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'ale_c_build_dir', g:__cmake_build_dir)
autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'ale_c_clang_options', join(g:__cmake_compile_flags))
autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'ale_cpp_clang_options', join(g:__cmake_compile_flags))
autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'ale_enabled', 1) | ALEEnable
autocmd BufReadPre *.py,CMakeLists.txt,*.cmake,*.css,*.json,*.md call setbufvar(str2nr(expand("<abuf>")), 'ale_enabled', 1) | ALEEnable
```


### [Syntastic](https://github.com/vim-syntastic/syntastic)

Use [`CmakeIndexUpdate`](#cmakeindexupdate) autocommand.

Ctr-C & Ctrl-V'able snippet for your init.vim is...
```vim
let g:syntastic_cpp_checkers = [ 'clang_check' ]
let g:syntastic_c_checkers = [ 'clang_check' ]

" Avoid checking without flags.
autocmd BufReadPre *.cpp,*.c call setbufvar(str2nr(expand("<abuf>")), 'syntastic_mode', 'passive')

autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'syntastic_c_clang_check_post_args', ' -- ' . join(g:__cmake_compile_flags))
autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'syntastic_cpp_clang_check_post_args', ' -- ' . join(g:__cmake_compile_flags))
autocmd User CmakeIndexUpdate call setbufvar(g:__cmake_buffer_number, 'syntastic_mode', 'active') | 
```


### [chromatica.nvim](https://github.com/arakashic/chromatica.nvim)

See [`g:nvim_cmake_emit_dotclang`](#gnvim_cmake_emit_dotclang).


### [nvim-completion-manager](https://github.com/roxma/nvim-completion-manager) ([ncm-clang](https://github.com/roxma/ncm-clang))

See [`g:nvim_cmake_emit_dotclangcomplete`](#gnvim_cmake_emit_dotclangcomplete).


### Add include path to path option

Here you go:
```vim
fun! AppendToPath()
    let previous_path = getbufvar(g:__cmake_buffer_number, '&path', '')
    let info = CmakeQueryFile(g:__cmake_build_dir, g:__cmake_abs_file_path)
    if string(info) == string(v:null)
        return
    endif

    let includes_path = join(l:info.includes, ',')
    call setbufvar(g:__cmake_buffer_number, '&path', l:previous_path . l:includes_path)
endfun

autocmd User CmakeIndexUpdate call AppendToPath()
```


# Contributing

Bug reports, questions, code are welcome.

# License

See [LICENSE](LICENSE).
