import inspect
import os
import importlib
import json

import addon_utils


OUTPUT_FILE_NAME = "generated.json"
EXCLUDE_MODULE_LIST = {
    "bl_i18n_utils.settings_user",
    "bl_i18n_utils.utils_spell_check",
}


def get_module_name_list():
    # Get modules to import.
    modules_dir = os.path.dirname(addon_utils.__file__)
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


def import_modules(module_name_list):
    imported_modules = []
    for name in module_name_list:
        mod = {}
        mod["module"] = importlib.import_module(name)
        mod["module_name"] = name
        imported_modules.append(mod)
    
    return imported_modules

def analyze_function(function):
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


def analyze_class(class_):
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


def analyze_module(module):
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


def analyze(modules):
    results = {}
    for m in modules:
        results[m["module_name"]] = analyze_module(m["module"])

    return results


def write_to_file(info):
    with open(OUTPUT_FILE_NAME, "w") as f:
        json.dump(info, f, indent=4, sort_keys=True, separators=(",", ": "))


def main():
    # Get modules to import.
    module_name_list = get_module_name_list()

    #module_name_list = ["bl_previews_utils.bl_previews_render"]

    # Import modules.
    imported_modules = import_modules(module_name_list)

    # Analyze modules.
    results = analyze(imported_modules)

    # Write module info to file.
    write_to_file(results)


if __name__ == "__main__":
    main()
