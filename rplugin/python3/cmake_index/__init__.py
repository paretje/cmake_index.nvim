#
# Copyright © 2017 Maks Mazurov (fox.cpp)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os.path
import logging
import json
import traceback
import typing
import neovim

from cmake_index.index import Index
from cmake_index.server import CmakeServer


DEFAULT_VALUES = {
    'autotrigger': 1,
    'log_level': 'info',

    'binary': '/usr/bin/cmake',
    'build_command': '/usr/bin/cmake --build {build_dir} --target {target}',
    'default_generator': 'Unix Makefiles',
    'socket_base': '/tmp/nvim_cmake_{pid}_{build_dir}',
    'persistent_server': 1,

    'default_cpp_flags': ['-std=c++14',
                          '-isystem', '/usr/include/c++/v1',
                          '-isystem', '/usr/local/include',
                          '-isystem', '/usr/include'],
    'default_c_flags': ['-isystem', '/usr/local/include', '-isystem', '/usr/include'],
    'cpp_source_extensions': {'.cpp', '.cc', '.CPP', '.cxx', '.c++', '.cp'},
    'c_source_extensions': {'.c'},
    'cpp_header_extensions': {'.hpp', '.h', '.HPP', '.hxx', '.hh', '.h++', '.hp', '.ii'},
    'c_header_extensions': {'.h'},

    'build_dirs': ['build', '.'],
    'root_files': ['CMakeLists.txt'],

    'build_pager': '10split + term://{command} | wincmd p',
    'run_pager': '30split + term://{command}',

    'emit_dotclang': 0,
    'emit_dotclangcomplete': 0,
    'emit_compilecommandsjson': 0,
    'compilecommandsjson_in_root': 1
}

CPP_HEADER = 1
CPP_SOURCE = 2
C_HEADER = 3
C_SOURCE = 4


class InvalidArgument(Exception):
    pass


class VimMessagesHandler(logging.Handler):
    def __init__(self, vim: neovim.Nvim) -> None:
        super(VimMessagesHandler, self).__init__()
        self.vim = vim

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        if record.levelno > logging.INFO:
            self.vim.err_write('cmake_index.nvim: ' + message + '\n')
        else:
            self.vim.out_write('cmake_index.nvim: ' + message + '\n')


@neovim.plugin
class Plugin(object):
    def __init__(self, vim: neovim.Nvim) -> None:
        self.vim = vim
        self.subcommands = ['init', 'run',
                            'reconf', 'reinit', 'clear', 'build']

        self.logger = logging.getLogger('cmake_index.nvim')
        self.logger.addHandler(VimMessagesHandler(vim))

        # Maps build directory to server instance.
        self.servers: dict = dict()

        # Maps build directory to index.
        self.index: dict = dict()

        # Config variables cache (IPC is really slow).
        self.config: dict = dict()

        # Map project root directories to last used build directories.
        self.used_build_dirs: dict = dict()

        self.logger.setLevel(self.get_opt('log_level').upper())

    def get_opt(self, key: str):
        if key not in self.config:
            remote_var = self.vim.vars.get(
                'nvim_cmake_' + key, DEFAULT_VALUES[key])
            self.config[key] = remote_var
            return remote_var
        return self.config[key]

    def file_type(self, filepath: str) -> int:
        splitten_name = os.path.splitext(filepath)
        if len(splitten_name) == 1:
            return False
        if splitten_name[1] in self.get_opt('cpp_source_extensions'):
            return CPP_SOURCE
        if splitten_name[1] in self.get_opt('cpp_header_extensions'):
            return CPP_HEADER
        if splitten_name[1] in self.get_opt('c_source_extensions'):
            return C_SOURCE
        if splitten_name[1] in self.get_opt('c_header_extensions'):
            return C_HEADER
        return None

    def build_dir(self, filename: str):
        root = self.project_root(filename)
        if root is None:
            return None
        for subdir in self.get_opt('build_dirs'):
            if os.path.isfile(root + os.sep + subdir + os.sep + 'CMakeCache.txt'):
                return root + os.sep + subdir
        return None

    def project_root(self, filename: str):
        prevcwd = os.getcwd()
        os.chdir(os.path.dirname(os.path.abspath(filename)))
        candidates = list()
        while os.path.dirname(os.getcwd()) != os.getcwd():
            if not set(self.get_opt('root_files')).isdisjoint(os.listdir()):
                matchdir = os.getcwd()
                candidates.append(matchdir)
            os.chdir('..')
        os.chdir(prevcwd)
        if len(candidates) == 0:
            return None
        return candidates[-1]

    def get_buffers_by_name(self, filename: str) -> list:
        result = list()
        for buffer in self.vim.buffers:
            if buffer.valid and buffer.name == filename:
                result.append(buffer)
        return result

    def build_command(self, build_dir: str, target_name: str) -> str:
        return self.get_opt('build_command').format(build_dir=build_dir, target=target_name)

    def build_target(self, build_dir: str, target_name: str) -> None:
        self.vim.command(self.get_opt('build_pager').format(
            command=self.build_command(build_dir, target_name)))
        self.vim.command('doautocmd User CmakeBuilding')

    @neovim.function('CmakeFileType', sync=True)
    def func_file_type(self, args: list):
        if len(args) != 1:
            raise InvalidArgument('CmakeGetOpt requires one argument: file type.')
        return self.file_type(args[0])

    @neovim.function('CmakeGetOpt', sync=True)
    def func_get_opt(self, args: list):
        if len(args) != 1:
            raise InvalidArgument('CmakeGetOpt requires one argument: option name.')
        return self.get_opt(args[0])

    @neovim.function('CmakeFindRootDir', sync=True)
    def func_search_root_directory(self, args: list):
        if len(args) == 1:
            return self.project_root(args[0])
        if self.vim.current.buffer.valid and self.vim.current.buffer.name != '':
            return self.project_root(self.vim.current.buffer.name)
        return self.project_root(os.getcwd() + '/noname')

    @neovim.function('CmakeFindBuildDir', sync=True)
    def func_search_build_directory(self, args: list):
        if len(args) == 1:
            return self.build_dir(args[0])
        if self.vim.current.buffer.valid and self.vim.current.buffer.name != '':
            return self.build_dir(self.vim.current.buffer.name)
        return self.build_dir(os.getcwd() + '/noname')

    @neovim.function('CmakeQueryFile', sync=True)
    def func_query_file(self, args: list):
        if len(args) == 1:
            return self.get_file_info(args[0])
        elif len(args) == 2:
            return self.get_file_info(args[1], build_dir=args[0])
        else:
            raise InvalidArgument('usage: CmakeQueryFile([build directory], <file name>)')

    @neovim.function('CmakeQueryTarget', sync=True)
    def func_query_target(self, args: list):
        if len(args) != 2:
            raise InvalidArgument('CmakeQueryTarget requires two arguments: root build directory and target name.')
        return self.get_target_info(args[0], args[1])

    @neovim.function('CmakeQueryCache', sync=True)
    def func_query_cache(self, args: list):
        if len(args) != 2:
            raise InvalidArgument('CmakeQueryCache requires two arguments: root build directory and cache variable name')
        return self.index[args[0]].cache_variable(args[1])

    @neovim.function('CmakeQueryTreeInfo', sync=True)
    def func_query_tree_info(self, args: list):
        if len(args) != 1:
            raise InvalidArgument('CmakeQueryTreeInfo requires one argument: build directory.')
        return self.index[args[0]]

    @neovim.function('CmakeBuildCommand', sync=True)
    def func_build_command(self, args: list) -> str:
        if len(args) != 2:
            raise InvalidArgument('CmakeBuildCommand requires two arguments: root build directory and target name.')
        return self.build_command(args[0], args[1])

    @neovim.function('CmakeBlockingInit', sync=True)
    def func_blocking_init(self, args: list) -> None:
        root_dir = (args[0] if len(args) == 1 else None)
        build_dir = (args[1] if len(args) == 2 else None)
        self.init_project_info(self.vim.current.buffer.name, root_dir, build_dir)

    @neovim.command('Cmake', nargs='*', sync=False)
    def root_command(self, args, range=None) -> None:
        if len(args) == 0 or args[0] not in self.subcommands:
            self.vim.out_write('Possible subcommands: ' +
                               ' '.join(self.subcommands) + '\n')
            return
        command_handler = getattr(self, 'command_' + args[0])
        res = command_handler(args[1:])
        if res is not None:
            self.vim.out_write(str(res) + '\n')

    def command_init(self, args: list) -> str:
        if 'cmake_root_dir' not in self.vim.current.buffer.vars:
            root_dir = (args[0] if len(args) >= 1 else None)
            build_dir = (args[1] if len(args) >= 2 else None)
            cache_variables = (args[2:] if len(args) > 2 else [])
            try:
                self.init_project_info(self.vim.current.buffer.name,
                                       root_dir, build_dir, cache_variables)
            except Exception as exception:
                self.update_buffer_variables()
                return type(exception).__qualname__ + ': ' + exception.args[0]
            return 'Initialized.'
        return 'Already initialized. Probably you want to run :Cmake reconf or :Cmake reinit.'

    def command_reinit(self, args: list) -> str:
        root_dir = (args[0] if len(args) >= 1 else None)
        build_dir = (args[1] if len(args) >= 2 else None)
        cache_variables = (args[2:] if len(args) > 2 else [])
        try:
            self.init_project_info(self.vim.current.buffer.name,
                                   root_dir, build_dir, cache_variables)
        except Exception as exception:
            self.update_buffer_variables()

            return type(exception).__qualname__ + ': ' + exception.args[0]
        return 'Reinitialized.'

    def command_run(self, args: list) -> str:
        if 'cmake_tree_build_dir' not in self.vim.current.buffer.vars:
            return 'Not in cmake project.'

        if len(args) == 0:
            file_info = self.get_file_info(self.vim.current.buffer.name, build_dir=self.vim.current.buffer.vars['cmake_tree_build_dir'])
            target_info = self.get_target_info(self.vim.current.buffer.vars['cmake_tree_build_dir'], file_info['target_name'])
            cmd_args = args
        else:
            target_info = self.index[self.vim.current.buffer.vars['cmake_tree_build_dir']].query_target(args[0])
            cmd_args = args[1:]

        if len(target_info['artifacts']) == 0:
            return 'No artifacts.'
        if target_info['type'] != 'EXECUTABLE':
            return 'Not executable.'

        self.build_target(
            self.vim.current.buffer.vars['cmake_tree_build_dir'], target_info['name'])
        command = target_info['artifacts'][0] + ' ' + ' '.join(cmd_args)
        self.vim.command(self.get_opt('run_pager').format(command=command))
        return 'Running ' + command + '...'

    def command_build(self, args: list):
        if 'cmake_tree_build_dir' not in self.vim.current.buffer.vars:
            return 'Not in cmake project.'

        if len(args) == 0:
            file_info = self.get_file_info(
                self.vim.current.buffer.name, build_dir=self.vim.current.buffer.vars['cmake_tree_build_dir'])
            target_info = self.get_target_info(
                self.vim.current.buffer.vars['cmake_tree_build_dir'], file_info['target_name'])
        else:
            target_info = self.get_target_info(self.vim.current.buffer.vars['cmake_tree_build_dir'], args[0])

        self.build_target(self.vim.current.buffer.vars['cmake_tree_build_dir'], target_info['name'])

    def command_clear(self, args: list) -> str:
        self.index = dict()
        for buffer in self.vim.buffers:
            if 'cmake_tree_build_dir' in buffer.vars:
                del buffer.vars['cmake_tree_build_dir']
        self.servers = dict()
        return 'Cache cleared. Server terminated.'

    def get_file_info(self, filename: str, build_dir: typing.Optional[str]=None) -> dict:
        abs_filename = os.path.abspath(filename)

        if build_dir is None:
            for index_entry in self.index.values():
                query_result = index_entry.query_file(abs_filename)
                return query_result

        if build_dir not in self.index:
            return None
        return self.index[build_dir].query_file(abs_filename)

    def get_target_info(self, build_dir: str, target_name: str) -> dict:
        if build_dir in self.index:
            return self.index[build_dir].query_target(target_name)
        return None

    # BufReadPre used to make sure if any BufRead handler affects current directory we will get final consistent value.
    @neovim.autocmd('BufReadPre', eval='expand("<afile>:p")', sync=False)
    def autoinit_project_info(self, filename: str) -> None:
        """ Start and configure cmake-server if needed. Set project info in buffer variables """
        if self.file_type(filename) is None or self.get_opt('autotrigger') == 0:
            self.update_buffer_variables()
            return

        try:
            self.init_project_info(filename)
        except Exception as exception:
            self.update_buffer_variables()
            self.logger.error('%s: %s', type(exception).__qualname__, exception.args[0])
            self.logger.debug(traceback.format_exc())

    @neovim.autocmd('BufNewFile', eval='expand("<afile>:p")', sync=False)
    def autoinit_project_info_newfile(self, filename: str) -> None:
        """ Start and configure cmake-server if needed. Set project info in buffer variables """
        if self.file_type(filename) is None or self.get_opt('autotrigger') == 0:
            self.update_buffer_variables()
            return

        try:
            self.init_project_info(filename)
        except Exception as exception:
            self.update_buffer_variables()
            self.logger.error('%s: %s', type(exception).__qualname__, exception.args[0])
            self.logger.debug(traceback.format_exc())

    def init_project_info(self, filename: str, root_dir=None, build_dir=None, cache_variables=[]) -> None:
        abs_filename = os.path.abspath(filename)

        always_configure = False

        if root_dir is None:
            root_dir = self.project_root(abs_filename)

        if build_dir is None:
            if root_dir not in self.used_build_dirs:
                build_dir = self.build_dir(abs_filename)
            else:
                build_dir = self.used_build_dirs[root_dir]
        else:
            always_configure = True
            if build_dir not in self.index and root_dir in self.used_build_dirs:
                # Throw away server and index with old build directory.
                del self.servers[self.used_build_dirs[root_dir]]
                del self.index[self.used_build_dirs[root_dir]]

        if root_dir is None:
            self.update_buffer_variables()

            self.logger.warning('No CMake project found.')
            return

        self.logger.info('Project root: ' + root_dir)
        if build_dir is not None:
            self.logger.info('Build directory: ' + build_dir)
            os.makedirs(build_dir, exist_ok=True)
        else:
            self.logger.debug('Missing build directory, dont worry, we will create one for you....')
            build_dir = root_dir + os.sep + self.get_opt('build_dirs')[0]
            os.makedirs(build_dir, exist_ok=True)

        server = self.get_server(root_dir, build_dir)

        cache_dict = dict()
        for cache_var in cache_variables:
            splitten = cache_var.split('=')
            cache_dict[splitten[0]] = splitten[1]

        if always_configure or build_dir not in self.index:
            server.configure(cache_dict)
            server.generate()
            index_ = Index(root_dir, build_dir)
            index_.initialize(server)
            self.index[build_dir] = index_
        else:
            index_ = Index(root_dir, build_dir)

        if self.get_opt('persistent_server') == 0:
            del self.servers[build_dir]

        if self.index[build_dir].query_file(abs_filename) is None:
            self.logger.critical('File not in any target.')

        self.used_build_dirs[root_dir] = build_dir

        if self.get_opt('emit_dotclang') == 1:
            self.logger.info('Generating .clang...')
            self.generate_dotclang(build_dir, abs_filename)
        if self.get_opt('emit_dotclangcomplete') == 1:
            self.logger.info('Generating .clang_complete...')
            self.generate_dotclangcomplete(build_dir, abs_filename)
        if self.get_opt('emit_compilecommandsjson') == 1:
            self.logger.info('Generating compile_commands.json...')
            self.write_compilation_database(root_dir, build_dir)

        self.update_buffer_variables()
        self.logger.info('Success!')

    def get_default_flags(self, abs_filename: str, info: typing.Optional[dict]=None):
        if info is not None and info['lang'] == 'CXX':
            if info['lang'] == 'CXX':
                return self.get_opt('default_cpp_flags')
            if info['lang'] == 'C':
                return self.get_opt('default_c_flags')
            return []
        else:
            type_ = self.file_type(abs_filename)
            if type_ == CPP_HEADER or type_ == CPP_SOURCE:
                return self.get_opt('default_cpp_flags')
            if type == C_HEADER or type_ == C_SOURCE:
                return self.get_opt('default_c_flags')
            return []

    def generate_dotclang(self, build_dir: str, abs_filename: str):
        info = self.index[build_dir].query_file(abs_filename)
        if info is None or len(info['flags']) == 0:
            dotclang_contents = 'flags=' + (' '.join(self.get_default_flags(abs_filename, info)))
        else:
            dotclang_contents = 'flags=' + (' '.join(info['flags']))
        dotclang_path = os.path.join(os.path.dirname(abs_filename), '.clang')
        with open(dotclang_path, 'w') as dotclang_file:
            dotclang_file.write(dotclang_contents + '\n')

    def generate_dotclangcomplete(self, build_dir: str, abs_filename: str):
        info = self.index[build_dir].query_file(abs_filename)
        if info is None or len(info['flags']) == 0:
            dotclangcomplete_contents = ' '.join(self.get_default_flags(abs_filename, info))
        else:
            dotclangcomplete_contents = ' '.join(info['flags'])
        dotclangcomplete_path = os.path.join(os.path.dirname(abs_filename), '.clang_complete')
        with open(dotclangcomplete_path, 'w') as dotclangcomplete_file:
            dotclangcomplete_file.write(dotclangcomplete_contents + '\n')

    def generate_compilation_database(self, index: Index) -> list:
        """
        Generate compilation database (compile_commands.json) for clang tools.
        """

        result = list()
        command_format = '{compiler} {flags} -c {source} -o {object_}'
        # XXX: What about object_ for headers?
        for file in index._files.values():
            compiler_path = index.cache_variable('CMAKE_{}_COMPILER'.format(file['lang']))
            result.append({
                'directory': file['tree_build_dir'],
                'file': file['path'],
                'command': command_format.format(compiler=compiler_path,
                                                 flags=' '.join(file['flags']),
                                                 source=file['path'],
                                                 object_=file['object_file'])
            })
        return result

    def write_compilation_database(self, root_dir: str, build_dir: str):
            if self.get_opt('compilecommandsjson_in_root') == 1:
                output_path = os.path.join(root_dir, 'compile_commands.json')
            else:
                output_path = os.path.join(build_dir, 'compile_commands.json')
                if os.path.exists(output_path):
                    self.logger.warning('Placing compilation database in build directory, it\'s unlikely it will be found by plugins.')

            file = open(output_path, 'w')
            file.write(json.dumps(self.generate_compilation_database(self.index[build_dir]), indent=4))

    def update_buffer_variables(self):
        for buffer in self.vim.buffers:
            if buffer.valid and buffer.name is not None:
                del buffer.vars['cmake_tree_build_dir']
                del buffer.vars['cmake_tree_root_dir']
                del buffer.vars['cmake_compile_flags']
                del buffer.vars['cmake_configured']

                abs_filepath = os.path.abspath(buffer.name)

                configured = False
                for index in self.index.values():
                    if index.query_file(abs_filepath) is not None:
                        buffer.vars['cmake_tree_build_dir'] = index.build_directory
                        buffer.vars['cmake_tree_root_dir'] = index.root_directory
                        buffer.vars['cmake_compile_flags'] = index.query_file(abs_filepath)['flags']
                        buffer.vars['cmake_configured'] = True
                        configured = True

                if not configured:
                    buffer.vars['cmake_tree_build_dir'] = None
                    buffer.vars['cmake_tree_root_dir'] = None
                    buffer.vars['cmake_compile_flags'] = self.get_default_flags(abs_filepath)
                    buffer.vars['cmake_configured'] = False

                self.trigger_update_event(buffer)

    def trigger_update_event(self, buffer: neovim.api.Buffer):
        self.vim.vars['__cmake_configured'] = ('cmake_tree_build_dir' in buffer.vars)
        self.vim.vars['__cmake_buffer_number'] = buffer.number
        self.vim.vars['__cmake_abs_file_path'] = os.path.abspath(buffer.name)
        self.vim.vars['__cmake_build_dir'] = buffer.vars.get('cmake_tree_build_dir', None)
        self.vim.vars['__cmake_compile_flags'] = buffer.vars.get('cmake_compile_flags', None)

        self.vim.command('doautocmd User CmakeIndexUpdate')

        del self.vim.vars['__cmake_configured']
        del self.vim.vars['__cmake_buffer_number']
        del self.vim.vars['__cmake_abs_file_path']
        del self.vim.vars['__cmake_build_dir']
        del self.vim.vars['__cmake_compile_flags']

    def get_server(self, root_dir: str, build_dir: str) -> CmakeServer:
        """ Get server instance for project. Starts new if needed. """
        if build_dir not in self.servers:
            self.servers[build_dir] = CmakeServer()
            server = self.servers[build_dir]
            server.start(self.get_opt('binary'), self.get_opt('socket_base').format(
                pid=str(os.getpid()), build_dir=build_dir.replace('/', '%'), root_dir=root_dir.replace('/', '%')))
            server.handshake(root_dir, build_dir, self.get_opt('default_generator')
                             if not os.path.exists(build_dir + os.sep + 'CMakeCache.txt') else None)
            return server
        return self.servers[build_dir]
