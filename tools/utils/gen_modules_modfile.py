################################################################################
#
# gen_module_modfile.py
#
# Description:
#   gen_module_modfile.py generates python classes and functions definition
#   from python modules in blender's 'modules' directory.
#   The definition file is output as a JSON file.
#
# Note:
#   This script needs to run from blender.
#   So, you need to download blender binary from blender's official website.
#
# Usage:
#   blender -noaudio --factory-startup --background --python \
#   gen_module_modfile.py -- [-m <first_import_module_name>] [-o <output_file>]
#
#     first_import_module_name:
#       Module name to import first.
#       This is used for finding blender's 'modules' directory.
#       ex. addon_utils
#
#     output_file:
#       Generated definitions are output to the JSON file whose name is
#       specified by this option.
#       ex. generated.json
#
################################################################################

import inspect
import os
import importlib
import json
import argparse
from typing import List, Dict


EXCLUDE_MODULE_LIST = {
    "bl_i18n_utils.settings_user",
    "bl_i18n_utils.utils_spell_check",
}


class GenerationConfig:
    first_import_module_name = None
    output_file = None


def get_module_name_list(config: 'GenerationConfig') -> List[str]:
    first_module = importlib.import_module(config.first_import_module_name)

    # Get modules to import.
    modules_dir = os.path.dirname(first_module.__file__)
    module_name_list = []
    for cur_dir, _, files in os.walk(modules_dir):
        for f in files:
            if not f.endswith(".py"):
                continue
            module_name = os.path.join(cur_dir, f).replace(modules_dir + "/", "")
            module_name = module_name[:-3].replace("/", ".")
            module_name = module_name.replace(".__init__", "")
            module_name_list.append(module_name)

    return list(set(module_name_list) - EXCLUDE_MODULE_LIST)


def import_modules(module_name_list: List[str]) -> List:
    imported_modules = []
    for name in module_name_list:
        mod = {}
        mod["module"] = importlib.import_module(name)
        mod["module_name"] = name
        imported_modules.append(mod)
    
    return imported_modules

def analyze_function(function) -> Dict:
    function_def = {
        "name": function[0],
        "arguments": [],
        "return": None
    }
    if not inspect.isbuiltin(function[1]):
        try:
            function_def["arguments"] = list(inspect.signature(function[1]).parameters.keys())
        except ValueError:
            function_def["arguments"] = []
    
    return function_def


def analyze_class(class_) -> Dict:
    class_def = {
        "name": class_[0],
        "methods": [],
        "parameters": [],
    }
    for x in [x for x in inspect.getmembers(class_[1])]:
        if x[0].startswith("_"):
            continue        # Skip private methods and parameters.

        # Get all class method definitions.
        if callable(x[1]):
            class_def["methods"].append(analyze_function(x))
        # Get all class parameter definitions.
        else:
            class_def["parameters"].append(x[0])
    
    return class_def


def analyze_module(module) -> Dict:
    result = {
        "classes": [],
        "functions": [],
    }

    # Get all class definitions.
    classes = inspect.getmembers(module, inspect.isclass)
    for c in classes:
        if c[0].startswith("_"):
            continue    # Skip private classes.
        if inspect.isbuiltin(c[1]):
            continue
        if inspect.getmodule(c[1]) != module:
            continue    # Remove indirect classes. (ex. from XXX import ZZZ)
        result["classes"].append(analyze_class(c))

    # Get all function definitions.
    functions = inspect.getmembers(module, inspect.isfunction)
    for f in functions:
        if f[0].startswith("_"):
            continue    # Skip private functions.
        if inspect.getmodule(f[1]) != module:
            continue    # Remove indirect functions. (ex. from XXX import ZZZ)

        result["functions"].append(analyze_function(f))
    
    return result


def analyze(modules: List) -> Dict:
    results = {}
    for m in modules:
        results[m["module_name"]] = analyze_module(m["module"])

    return results


def write_to_file(info: Dict, config: 'GenerationConfig'):
    with open(config.output_file, "w") as f:
        json.dump(info, f, indent=4, sort_keys=True, separators=(",", ": "))


def parse_options() -> 'GenerationConfig':
    usage = """Usage: blender -noaudio --factory-startup --background --python
               {} -- [-m <first_import_module_name>] [-o <output_file>]"""\
        .format(__file__)
    parser = argparse.ArgumentParser(usage)
    parser.add_argument(
        "-m", dest="first_import_module_name", type=str,
        help="""Module name to import first.
        This is used for finding blender's 'modules' directory.
        """
    )
    parser.add_argument(
        "-o", dest="output_file", type=str, help="Output file."
    )
    args = parser.parse_args()

    config = GenerationConfig()
    config.first_import_module_name = args.first_import_module_name
    config.output_file = args.output_file

    return config


def main():
    config = parse_options()

    # Get modules to import.
    module_name_list = get_module_name_list(config)

    # Import modules.
    imported_modules = import_modules(module_name_list)

    # Analyze modules.
    results = analyze(imported_modules)

    # Write module info to file.
    write_to_file(results, config)


if __name__ == "__main__":
    main()
