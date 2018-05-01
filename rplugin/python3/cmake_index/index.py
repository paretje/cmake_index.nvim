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
import cmake_index.server


class Index(object):
    """
    Store for information acquired from cmake server.
    """

    __slots__ = ('build_directory', 'root_directory', '_projects', '_targets', '_files', '_cache')

    def __init__(self, root_directory: str, build_directory: str) -> None:
        self.build_directory = build_directory
        self.root_directory = root_directory

        # Projects information (key is a project name)
        self._projects: dict
        self._projects = dict()

        # Targets information (key is a target name)
        self._targets: dict
        self._targets = dict()

        # Files information (key is a absolute file path)
        self._files: dict
        self._files = dict()

        # CMake cache variables
        self._cache: dict
        self._cache = dict()

    def initialize(self, server: cmake_index.server.CmakeServer):
        """
        Query server for information required to populate index.
        """

        codemodel = server.codemodel()
        configuration = codemodel['configurations'][0]
        projects = [convert_project_info(project, self.root_directory, self.build_directory)
                    for project in configuration['projects']]

        for project in projects:
            self._projects[project['name']] = project
            for (name, info) in project['targets'].items():
                self._targets[name] = info
            for file in project['files']:
                self._files[file['path']] = file

        self._files.update(run_matching_header_heuristics(self._files))
        self._cache = convert_cache_variables(server.cache()['cache'])

    def query_file(self, abs_path: str, directory_heuristics=True):
        """
        Get file information from index.
        Attempts to guess file information from directory if directory_heuristics=True (default).

        Returns None if file is not known and directory heuristics failed.
        """

        if abs_path in self._files:
            return self._files[abs_path]
        elif directory_heuristics:
            result = get_file_info_for_directory(abs_path, self._targets)
            if result is not None:
                self._files[abs_path] = result
                if result['target_name'] not in self._targets:
                    self._targets[result['target_name']] = dict()
                self._targets[result['target_name']
                              ]['filepaths'].append(result['path'])
                return result
        return None

    def query_target(self, name: str):
        """
        Get target information from index.

        Returns None if target is not known.
        """

        return self._targets.get(name, None)

    def query_project(self, name: str):
        """
        Get project information from index.

        Returns None if project is not known.
        """

        return self._projects.get(name, None)

    def cache_variable(self, name: str):
        """
        Return CMake cache variable value.

        Returns None if there is no variable with such name.
        """

        return self._cache.get(name, None)


def convert_cache_variables(cache_json: list) -> dict:
    """
    Convert list of cache variables returned by server to dictonary without unnecessary information.

    cache_json is 'cache' object from response to 'cache' request.
    """
    return dict((entry['key'], entry['value']) for entry in cache_json)


def include_path_to_flags(include_path_json: dict, parent_target: dict) -> list:
    """
    Convert list of includes flags returned by server to list of flags.

    include_path_json is json list returned by server in file group object.
    """

    result = list()
    for include in include_path_json:
        if include.get('isSystem', False):
            result.append("-isystem")
        else:
            result.append("-I")
        # According to cmake-server(7) paths is either absolute or relative to source directory.
        if os.path.isabs(include['path']):
            result.append(include['path'])
        else:
            result.append(os.path.join(parent_target['source_dir'], include['path']))
    return result


def convert_file_info(group_json: dict, parent_target: dict) -> list:
    """
    Convert file information returned by server to format used by plugin.
    """

    result = list()
    for filename in group_json['sources']:
        converted_info = {
                'target_name':    parent_target['name'],
                'tree_root_dir':  parent_target['tree_root_dir'],
                'tree_build_dir': parent_target['tree_build_dir'],
                'lang':           group_json.get('language', None),
                'heuristics':     False,
                'other_flags':    group_json.get('compileFlags', "").split(),
                'defines':        group_json.get('defines', []),
                'includes':       list(),
                'flags':          group_json.get('compileFlags', "").split() +
                                  ['-D' + str(define) for define in group_json.get('defines', [])] +
                                  include_path_to_flags(group_json.get('includePath', []), parent_target)
        }
        # ^ There will be also either 'header_file' or 'source_file' added by matching header heuristics.

        # According to cmake-server(7) paths is either absolute or relative to source directory.

        for include in group_json.get('includePath', []):
            if os.path.isabs(include['path']):
                converted_info['includes'].append(include['path'])
            else:
                converted_info['includes'].append(os.path.join(parent_target['source_dir'], include['path']))

        if os.path.isabs(filename):
            converted_info['path'] = filename
        else:
            converted_info['path'] = os.path.join(parent_target['source_dir'], filename)

        converted_info['object_file'] = '{target_obj_dir}/{relative_path_in_source_dir}.o'\
            .format(target_obj_dir=parent_target['object_dir'],
                    relative_path_in_source_dir=os.path.relpath(converted_info['path'], parent_target['source_dir']))

        result.append(converted_info)
    return result


def convert_target_info(target_json: dict, parent_project: dict) -> dict:
    """
    Convert target information returned by server to format used by plugin.

    parent_json is incomplete project json as produced by convert_project_info.
    """

    result = {
            'name':              target_json['name'],
            'squashed':          False,
            'type':              target_json['type'],
            'tree_root_dir':     parent_project['tree_root_dir'],
            'tree_build_dir':    parent_project['tree_build_dir'],
            'build_dir':         os.path.abspath(target_json['buildDirectory']),
            'source_dir':        os.path.abspath(target_json['sourceDirectory']),
            'link_lang':         target_json.get('linkerLanguage', None),
            'result_name':       target_json.get('fullName', None),
            'artifacts':         target_json.get('artifacts', list()),
            'filepaths':         list(),
            'all_includes':      list(),
            'all_defines':       list(),
            'all_other_flags':   list(),
            'all_flags':         list()
    }

    result['object_dir'] = os.path.join(result['build_dir'], 'CMakeFiles', result['name'] + '.dir')

    for group in [convert_file_info(group_info, result) for group_info in target_json.get('fileGroups', [])]:
        # All these options is same for all files, so we can just take first file and use info form it.
        result['filepaths'] += list([file['path'] for file in group])
        result['all_includes'] += group[0]['includes']
        result['all_defines'] += group[0]['defines']
        result['all_other_flags'] += group[0]['other_flags']
        result['all_flags'] += group[0]['flags']
    return result


def convert_project_info(json: dict, root_dir: str, build_dir: str) -> dict:
    """
    Convert project information returned by server to format used by plugin.
    """

    result = {
            'name': json['name'],
            'source_dir': json['sourceDirectory'],
            'build_dir': json['buildDirectory'],
            'tree_root_dir': root_dir,
            'tree_build_dir': build_dir
    }

    # Add all targets to list except UTILITY and INTERFACE_LIBRARY.
    # TODO: Is it good idea?
    result['targets'] = dict()
    for target_json in json.get('targets', []):
        if target_json['type'] == 'UTILITY' or target_json['type'] == 'INTERFACE_LIBRARY':
            continue

        result['targets'][target_json['name']] = convert_target_info(target_json, result)

    result['files'] = list()
    for target_json in json.get('targets', []):
        if target_json['type'] == 'UTILITY' or target_json['type'] == 'INTERFACE_LIBRARY':
            continue
        for group_json in target_json.get('fileGroups', []):
            result['files'] += convert_file_info(group_json, result['targets'][target_json['name']])
    return result

    # ^ rewritting these loops as generators will hurt readability A LOT.


def target_directories(target: dict):
    """
    Return list of directories with files from target.
    """

    return set([os.path.dirname(filepath) for filepath in target['filepaths']])


def targets_in_directory(abs_directory: str, targets: dict) -> list:
    """
    Return list of targets for which we have files in directory.
    """

    return [target for (_, target) in targets.items() if abs_directory in target_directories(target)]


def merge_target_info(targets: list):
    """
    Squash together information about multiple targets into single "target".
    """

    # TODO: Handle squashed targets in build command generation!

    if len(targets) == 0:
        return None

    combined_target = {
            'name':              '|'.join([target['name'] for target in targets]),
            'squashed':          True,
            'type':              targets[0]['type'],
            'tree_root_dir':     targets[0]['tree_root_dir'],
            'tree_build_dir':    targets[0]['tree_build_dir'],
            'build_dir':         os.path.abspath(targets[0]['build_dir']),
            'source_dir':        os.path.abspath(targets[0]['source_dir']),
            'link_lang':         targets[0].get('linkerLanguage', None),
            'result_name':       targets[0].get('fullName', None),
            'artifacts':         targets[0].get('artifacts', list()),
            'filepaths':         list(),
            'all_includes':      list(),
            'all_defines':       list(),
            'all_other_flags':   list(),
            'all_flags':         list()
    }

    for target in targets:
        combined_target['all_includes'] += target['all_includes']
        combined_target['all_defines'] += target['all_defines']
        combined_target['all_other_flags'] += target['all_other_flags']
        combined_target['all_flags'] += target['all_flags']

    return combined_target


def get_file_info_for_directory(abs_filepath: str, targets: dict):
    merged_target = merge_target_info(
        targets_in_directory(os.path.dirname(abs_filepath), targets))
    if merged_target is None:
        return None
    return {
            'path': abs_filepath,
            'target_name': merged_target['name'],
            'tree_root_dir': merged_target['tree_root_dir'],
            'tree_build_dir': merged_target['tree_build_dir'],
            'lang': merged_target['link_lang'],
            'heuristics': True,
            'other_flags': merged_target['all_other_flags'],
            'defines': merged_target['all_defines'],
            'includes': merged_target['all_includes'],
            'flags': merged_target['all_flags']
    }


def match_header(file_info: dict):
    """
    Inner function of run_matching_header_heuristics. Don't use it directly.
    """

    # We examine included headers in order to catch cases where corresponding header
    # is not in directory from include path and included like this:
    # #include "utils/stuff.hpp"
    # or
    # #include "../stuff.hpp"
    # (assuming source file is stuff.cpp)

    included_files = []
    with open(file_info['path'], 'r') as source_file:
        for line in source_file:
            stripped = line.lstrip()
            if stripped.startswith('#include'):
                splitten = stripped.split()
                if len(splitten) == 1:
                    continue
                # Take file from <file> or "file".
                try:
                    included_files.append(splitten[1][1:-1])
                except IndexError:
                    pass

    filename = os.path.split(file_info['path'])[1]
    filename_without_ext = os.path.splitext(filename)[0]

    for included_file in included_files:
        included_filename = os.path.split(included_file)[1]
        included_filename_without_ext = os.path.splitext(included_filename)[0]

        if filename_without_ext != included_filename_without_ext:
            continue

        # Search matching header in include path...
        for include_directory in [os.getcwd()] + file_info['includes']:
            if os.path.isfile(os.path.join(include_directory, included_file)):
                result = file_info.copy()
                result['heuristics'] = True
                result['source_file'] = file_info['path']
                result['path'] = os.path.abspath(
                    include_directory + os.sep + included_file)
                return result
        return None


def run_matching_header_heuristics(known_files: dict) -> dict:
    """
    For each source in known_files try to find matching header and return changed items.
    (expected to be applited to original dict like `known_files.update(result)`)
    """

    new_files = dict()
    for file in known_files.values():
        try:
            header = match_header(file)
        except IOError:
            continue
        except UnicodeDecodeError:
            continue

        if header is not None:
            new_files[header['path']] = header
            new_files[file['path']] = file.copy()
            new_files[file['path']]['header_file'] = header['path']

    return new_files
