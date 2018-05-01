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

import os
import time
import neovim

# Here we exploit that fact that ycmd runs as child process of nvim
# and nvim sets NVIM_LISTEN_ADDRESS to path for IPC. We attach and
# interact with plugin using API functions.


def FlagsForFile(filename, **kwargs):
    nvim = neovim.attach('socket', path=os.getenv('NVIM_LISTEN_ADDRESS'))

    enable_log = nvim.call('CmakeGetOpt', 'log_level') == 'debug'

    def log(message: str):
        if enable_log:
            nvim.out_write('cmake_index.nvim [ycmd]: ' + message + '\n')

    log('Waiting for information from CMake...')

    buffers = list()
    for buffer in nvim.buffers:
        if buffer.valid and buffer.name == filename:
            buffers.append(buffer)

    tree_build_dir = None
    while tree_build_dir is None:
        for buffer in buffers:
            if 'cmake_configured' in buffer.vars:
                if buffer.vars['cmake_configured']:
                    tree_build_dir = buffer.vars['cmake_tree_build_dir']
                else:
                    log('Not in cmake project. Returning default flags.')
                    return {'flags': buffer.vars['cmake_compile_flags']}
        time.sleep(1)

    file_info = nvim.call('CmakeQueryFile', tree_build_dir, filename)

    if file_info is None:
        nvim.err_write('cmake_index.nvim [ycmd]: [BUG] Missing file info but cmake_configured is True.\n')
        return {'flags': []}

    if len(file_info['flags']) == 0:
        nvim.err_write('cmake_index.nvim [ycmd] No compile flags.\n')
        return {'flags': []}

    log('Returning flags: ' + ' '.join(file_info['flags']))
    return {'flags': file_info['flags']}
