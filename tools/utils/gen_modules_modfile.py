################################################################################
#
# gen_module_modfile.py
#
# Description:
#   gen_module_modfile.py generates python classes and functions definition
#   from python modules in blender's 'modules' directory.
#   The definitions are output as a modfile format (JSON).
#
# Note:
#   This script needs to run from blender.
#   So, you need to download blender binary from blender's official website.
#
# Usage:
#   blender -noaudio --factory-startup --background --python \
#    gen_module_modfile.py -- [-m <first_import_module_name>] [-o <output_dir>]
#
#     first_import_module_name:
#       Module name to import first.
#       This is used for finding blender's 'modules' directory.
#       (ex. addon_utils)
#
#     output_dir:
#       Generated definitions are output to files which will be located to
#       specified directory.
#       (ex. gen_modules_modfile.generated)
#
################################################################################

import sys
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
    output_dir = None


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

def analyze_function(module_name: str, function, is_method=False) -> Dict:
    function_def = {
        "name": function[0],
        "type": "method" if is_method else "function",
        "parameters": [],
    }
    if not is_method:
        function_def["module"] = module_name

    if not inspect.isbuiltin(function[1]):
        try:
            function_def["parameters"] = list(inspect.signature(function[1]).parameters.keys())
        except ValueError:
            function_def["parameters"] = []
    
    return function_def


def analyze_class(module_name: str, class_) -> Dict:
    class_def = {
        "name": class_[0],
        "type": "class",
        "module": module_name,
        "base_classes": [],     # TODO
        "methods": [],
        "attributes": [],
    }
    for x in [x for x in inspect.getmembers(class_[1])]:
        if x[0].startswith("_"):
            continue        # Skip private methods and attributes.

        # Get all class method definitions.
        if callable(x[1]):
            class_def["methods"].append(analyze_function(module_name, x, True))
        # Get all class parameter definitions.
        else:
            class_def["attributes"].append(x[0])
    
    return class_def


def analyze_module(module_name: str, module) -> Dict:
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
        result["classes"].append(analyze_class(module_name, c))

    # Get all function definitions.
    functions = inspect.getmembers(module, inspect.isfunction)
    for f in functions:
        if f[0].startswith("_"):
            continue    # Skip private functions.
        if inspect.getmodule(f[1]) != module:
            continue    # Remove indirect functions. (ex. from XXX import ZZZ)

        result["functions"].append(analyze_function(module_name, f))
    
    return result


def analyze(modules: List) -> Dict:
    results = {}
    for m in modules:
        results[m["module_name"]] = analyze_module(m["module_name"], m["module"])

    return results


def write_to_modfile(info: Dict, config: 'GenerationConfig'):
    data = {}

    for module_name, module_info in info.items():
        package_name = module_name
        index = package_name.find(".")
        if index != -1:
            package_name = package_name[:index]

        if package_name not in data.keys():
            data[package_name] = {
                "new": []
            }
        for class_info in module_info["classes"]:
            data[package_name]["new"].append(class_info)
        for function_info in module_info["functions"]:
            data[package_name]["new"].append(function_info)

    os.makedirs(config.output_dir, exist_ok=True)
    for pkg, d in data.items():
        with open("{}/{}.json".format(config.output_dir, pkg), "w") as f:
            json.dump(d, f, indent=4, sort_keys=True, separators=(",", ": "))


def parse_options() -> 'GenerationConfig':
    # Start after "--" option if we run this script from blender binary.
    argv = sys.argv
    try:
        index = argv.index("--") + 1
    except:
        index = len(argv)
    argv = argv[index:]

    usage = """Usage: blender -noaudio --factory-startup --background --python
               {} -- [-m <first_import_module_name>] [-o <output_dir>]"""\
        .format(__file__)
    parser = argparse.ArgumentParser(usage)
    parser.add_argument(
        "-m", dest="first_import_module_name", type=str,
        help="""Module name to import first.
        This is used for finding blender's 'modules' directory.
        """
    )
    parser.add_argument(
        "-o", dest="output_dir", type=str, help="Output directory."
    )
    args = parser.parse_args(argv)

    config = GenerationConfig()
    config.first_import_module_name = args.first_import_module_name
    config.output_dir = args.output_dir

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
    write_to_modfile(results, config)


if __name__ == "__main__":
    main()
