import xml.etree.ElementTree as et
import re
from typing import List
import json

from .common import (
    IntermidiateDataType,
    Info,
    ParameterDetailInfo,
    ReturnInfo,
    VariableInfo,
    FunctionInfo,
    ClassInfo,
    SectionInfo,
)
from .utils import (
    output_log,
    LOG_LEVEL_NOTICE,
    LOG_LEVEL_WARN,
    LOG_LEVEL_ERR
)


def textify(elm) -> str:
    s = []
    if elm.text:
        s.append(elm.text)
    for child in elm.getchildren():
        s.extend(textify(child))
    if elm.tail:
        s.append(elm.tail)

    return ''.join(s)


class VariableAnalyzer:
    def __init__(self, filename: str, type_: str):
        self.filename: str = filename
        self.info: 'VariableInfo' = VariableInfo(type_)

    def _parse_field(self, elm, result):
        field_type = ""
        for child in list(elm):
            if child.tag == "field_name":
                field_type = child.text
            elif child.tag == "field_body":
                if field_type == "Type":
                    result["data_dtype"] = re.sub(r'\s+', ' ', textify(child))

    def _parse_field_list(self, elm, result):
        for child in list(elm):
            if child.tag == "field":
                self._parse_field(child, result)

    def _parse_desc_content(self, elm, result):
        for child in list(elm):
            if child.tag == "paragraph":
                result["desc"] = re.sub(r'\s+', ' ', textify(child))
            elif child.tag == "field_list":
                self._parse_field_list(child, result)

    def analyze(self, elm) -> 'VariableInfo':
        signature_analyzed = False
        for child in list(elm):
            if child.tag == "desc_signature":
                if signature_analyzed:
                    msg = "desc_content must be parsed after parsing " \
                          "desc_signature"
                    output_log(LOG_LEVEL_ERR, msg)
                    raise RuntimeError(msg)

                # get name data
                name = child.get("fullname")
                if name is None:
                    name = child.find("desc_name").text   # for constant data
                class_ = child.get("class")
                if (class_ is not None) and (class_ != ""):
                    idx = name.rfind(class_)    # for class attribute
                    if idx != -1:
                        name = name[idx + len(class_) + 1:]
                self.info.set_name(name)

                # get module/class data
                self.info.set_class(class_)
                self.info.set_module(child.get("module"))

                signature_analyzed = True

            elif child.tag == "desc_content":
                if not signature_analyzed:
                    msg = "desc_signature must be parsed before parsing " \
                          "desc_content"
                    output_log(LOG_LEVEL_ERR, msg)
                    raise RuntimeError(msg)

                result = {}
                self._parse_desc_content(child, result)

                # get description/dtype data
                if "desc" in result:
                    self.info.set_description(result["desc"])
                if "data_dtype" in result:
                    self.info.set_data_type(IntermidiateDataType(result["data_dtype"]))

        if not signature_analyzed:
            msg = "The data data is not parsed"
            output_log(LOG_LEVEL_ERR, msg)
            raise RuntimeError(msg)

        return self.info


class FunctionAnalyzer:
    def __init__(self, filename, type_):
        self.filename: str = filename
        self.info: 'FunctionInfo' = FunctionInfo(type_)

    def _get_return_type_paragraph(self, elm):
        all_str = textify(elm)
        s = re.sub(r'\s+', ' ', all_str)
        return s

    def _get_return_type(self, elm):
        for child in list(elm):
            if child.tag == "paragraph":
                return self._get_return_type_paragraph(child)

        output_log(
            LOG_LEVEL_WARN,
            "<paragraph> is not found (filename={0})".format(self.filename)
        )
        return ""

    def _get_param_paragraph(self, elm):
        """
        parse

          <paragraph>
            <literal_strong>
              [name]
            </literal_strong>
            <literal_emphasis>
              [type]
            </literal_emphasis>
            [desc]
          </paragraph>

        or

          <paragraph>
            <strong>
              [name]
            </strong>
            <literal_emphasis>
              [type]
            </literal_emphasis>
            [desc]
          </paragraph>
        """

        name = None
        for l in list(elm):
            if (l.tag == "literal_strong") or (l.tag == "strong"):
                name = l.text
        str_ = textify(elm)
        if name is None:
            output_log(
                LOG_LEVEL_WARN,
                "<literal_strong> or <strong> is not found. "
                "(filename={0})".format(self.filename)
            )
            return None

        str_ = re.sub(r'\s+', ' ',  str_)
        str_ = re.sub(r'\(\s+', '(', str_)
        r = re.compile("([a-zA-Z0-9_]+) \((.+)\) – (.+)")
        result = r.findall(str_)
        if result:
            info = ParameterDetailInfo()
            info.set_name(result[0][0])
            info.set_description(result[0][2])
            info.set_data_type(IntermidiateDataType(result[0][1]))
            return info

        r = re.compile("([a-zA-Z0-9_]+) – (.+)")
        result = r.findall(str_)
        if result:
            info = ParameterDetailInfo()
            info.set_name(result[0][0])
            info.set_description(result[0][1])
            return info

        r = re.compile("([a-zA-Z0-9_]+) \((.+)\) – ")
        result = r.findall(str_)
        if result:
            info = ParameterDetailInfo()
            info.set_name(result[0][0])
            info.set_data_type(IntermidiateDataType(result[0][1]))
            return info

        output_log(
            LOG_LEVEL_WARN,
            "Does not match any paramter pattern. "
            "(filename={}, str={})".format(self.filename, str_)
        )

        return None

    def _analyze_list_item(self, elm):
        paragraph = None
        for child in list(elm):
            if child.tag == "paragraph":
                paragraph = child
                break

        if not paragraph:
            output_log(
                LOG_LEVEL_WARN,
                "<paragraph> is not found (filename={0})".format(self.filename)
            )
            return None

        return self._get_param_paragraph(paragraph)

    def _parse_bullet_list(self, elm):
        items = []
        for child in list(elm):
            if child.tag == "list_item":
                item = self._analyze_list_item(child)
                if item is not None:
                    items.append(item)
        return items

    def _analyze_param_list(self, elm, result):
        params = []
        for child in list(elm):
            if child.tag == "bullet_list":
                params = self._parse_bullet_list(child)
            elif child.tag == "paragraph":
                p = self._get_param_paragraph(child)
                if p:
                    params = [p]

        result["params_detail"] = params

    def _parse_field(self, elm, result):
        field_type = ""
        for child in list(elm):
            if child.tag == "field_name":
                field_type = child.text
            elif child.tag == "field_body":
                if field_type == "Parameters":
                    self._analyze_param_list(child, result)
                elif field_type == "Return type":
                    result["return_dtype"] = self._get_return_type(child)
                elif field_type == "Returns":
                    result["return_desc"] = re.sub(r'\s+', ' ', textify(child))

    def _parse_field_list(self, elm, result):
        for child in list(elm):
            if child.tag == "field":
                self._parse_field(child, result)

    def _parse_desc_content(self, elm, result):
        for child in list(elm):
            if child.tag == "paragraph":
                result["desc"] = re.sub(r'\s+', ' ', textify(child))
            elif child.tag == "field_list":
                self._parse_field_list(child, result)

    def _parse_parameter_body_text(self, text):
        sp = [re.sub(" ", "", p) for p in text.split(",")]

        params = []
        parenthese_level = 0
        next_param = ""
        for p in sp:
            parenthese_level += p.count("(") - p.count(")")
            if parenthese_level < 0:
                raise ValueError("Parenthese Level must be >= 0, but {}. (text: {}, filename: {})"
                                 .format(parenthese_level, text, self.filename))

            next_param += p + ","
            if parenthese_level == 0:
                params.append(next_param[:-1])  # strip last ","
                next_param = ""
        
        if parenthese_level != 0:
            raise ValueError("Parenthese Level must be == 0, but {}. (text: {}, filename: {})"
                             .format(parenthese_level, text, self.filename))

        return params

    def _get_parameters(self, elm):
        result = []
        param_bodies = []
        for child in list(elm):
            if child.tag == "desc_parameter":
                param_bodies.append(child.text)
        result.extend(self._parse_parameter_body_text(",".join(param_bodies)))
        return result

    def analyze(self, elm) -> 'FunctionInfo':
        signature_analyzed = False
        for child in list(elm):
            if child.tag == "desc_signature":
                if signature_analyzed:
                    continue

                fullname = child.get("fullname")
                text = child.find("desc_name").text
                lp = text.find("(")
                rp = text.rfind(")")
                if (lp == -1) or (rp == -1):
                    output_log(
                        LOG_LEVEL_NOTICE,
                        "'(' or ')' are not found (text={}, filename={})".format(text, self.filename)
                    )

                    # get name data
                    name = text

                    # TODO: freestyle.shader.SmoothingShader.__init__() matches this case.
                    parenthese_index = name.find("(")
                    if parenthese_index != -1:
                        name = name[:parenthese_index]
                        output_log(
                            LOG_LEVEL_WARN,
                            "Function name has parenthesis. But this should be fixed at Blender itself. (name: {}, filename: {})"
                            .format(name, self.filename)
                        )

                    # get parameters
                    params = []
                    c = child.find("desc_parameterlist")
                    if c is not None:
                        params = self._get_parameters(c)
                else:
                    if lp == -1:
                        raise ValueError("( is not found. (text: {}, filename: {})"
                                         .format(text, self.filename))
                    if rp == -1:
                        raise ValueError(") is not found. (text: {}, filename: {})"
                                         .format(text, self.filename))

                    # get name data
                    name = text[0:lp]

                    # get parameters
                    params = self._parse_parameter_body_text(text[lp + 1:rp])

                self.info.set_name(name)
                self.info.add_parameters(params)

                # validate name data
                if not self.info.equal_to_fullname(fullname):
                    if fullname is not None:
                        output_log(
                            LOG_LEVEL_NOTICE,
                            "fullname does not match text "
                            "(fullname={}, text={}, filename={})"
                            .format(fullname, name, self.filename)
                        )

                # get module/class data
                self.info.set_module(child.get("module"))
                self.info.set_class(child.get("class"))

                signature_analyzed = True

            elif child.tag == "desc_content":
                if not signature_analyzed:
                    msg = "desc_signature must be parsed before parsing " \
                          "desc_content"
                    output_log(LOG_LEVEL_ERR, msg)
                    raise RuntimeError(msg)

                result = {}
                self._parse_desc_content(child, result)

                # get description data
                if "desc" in result.keys():
                    self.info.set_description(result["desc"])

                # get return data
                return_builder = ReturnInfo()
                if "return_dtype" in result.keys():
                    return_builder.set_data_type(IntermidiateDataType(result["return_dtype"]))
                if "return_desc" in result.keys():
                    return_builder.set_description(result["return_desc"])
                self.info.set_return(return_builder)

                # get params_detail data
                if "params_detail" in result.keys():
                    self.info.add_parameter_details(result["params_detail"])
                break

        if not signature_analyzed:
            msg = "The function data is not parsed"
            output_log(LOG_LEVEL_ERR, msg)
            raise RuntimeError(msg)

        return self.info


class ClassAnalyzer:
    def __init__(self, filename):
        self.filename: str = filename
        self.info: 'ClassInfo' = ClassInfo()

    def _parse_desc(self, desc, result):
        attr = desc.get("desctype")
        if attr == "function" or attr == "method":
            if "method" not in result:
                result["method"] = []
            analyzer = FunctionAnalyzer(self.filename, "method")
            m = analyzer.analyze(desc)
            result["method"].append(m)
        elif attr == "attribute" or attr == "data":
            if "attribute" not in result:
                result["attribute"] = []
            analyzer = VariableAnalyzer(self.filename, "attribute")
            a = analyzer.analyze(desc)
            result["attribute"].append(a)

    def _parse_desc_content(self, elm, result):
        for child in list(elm):
            if child.tag == "paragraph":
                result["desc"] = re.sub(r'\s+', ' ', textify(child))
            elif child.tag == "desc":
                self._parse_desc(child, result)

    def analyze(self, elm) -> 'ClassInfo':
        signature_analyzed = False
        for child in list(elm):
            if child.tag == "desc_signature":
                if signature_analyzed:
                    continue        # ignore

                # get name data
                self.info.set_name(child.get("fullname"))

                # get module data
                self.info.set_module(child.get("module"))

                signature_analyzed = True

            elif child.tag == "desc_content":
                if not signature_analyzed:
                    msg = "desc_signature must be parsed before parsing " \
                          "desc_content"
                    output_log(LOG_LEVEL_ERR, msg)
                    raise RuntimeError(msg)

                # get description data
                result = {}
                self._parse_desc_content(child, result)
                if "desc" in result.keys():
                    self.info.set_description(result["desc"])
                if "method" in result.keys():
                    self.info.add_methods(result["method"])
                if "attribute" in result.keys():
                    self.info.add_attributes(result["attribute"])

        if not signature_analyzed:
            msg = "The class data is not parsed"
            output_log(LOG_LEVEL_ERR, msg)
            raise RuntimeError(msg)

        return self.info


class AnalysisResult:
    def __init__(self):
        self.section_info: List['SectionInfo'] = []


class BaseAnalyzer:
    def __init__(self):
        self.filenames: List[str] = []

    def _analyze_desc(self, filename: str, desc) -> 'Info':
        result = None
        attr = desc.get("desctype")
        if attr == "function" or attr == "method":
            analyzer = FunctionAnalyzer(filename, "function")
            result = analyzer.analyze(desc)
        elif attr == "data":
            analyzer = VariableAnalyzer(filename, "constant")
            result = analyzer.analyze(desc)
        elif attr == "class":
            analyzer = ClassAnalyzer(filename)
            result = analyzer.analyze(desc)

        return result

    def _analyze_desc_with_base_classes(self, filename: str, desc, base_classes: List['DataType']) -> 'Info':
        result = None
        attr = desc.get("desctype")
        if attr == "class":
            analyzer = ClassAnalyzer(filename)
            result = analyzer.analyze(desc)
            result.add_base_classes(base_classes)
        else:
            raise ValueError("desctype must be 'class' when base_classes are exist")

        return result

    def _analyze_base_classes(self, filename: str, elm) -> List['DataType']:
        base_classes = []
        for child in elm.iter("reference"):
            data_type = IntermidiateDataType(child.attrib["reftitle"])
            base_classes.append(data_type)

        return base_classes

    def _analyze_section(self, filename: str, elm, result: 'SectionInfo'):
        base_classes = []
        for child in list(elm):
            if child.tag == "paragraph":    # <paragraph>base classes — </paragraph>
                # This is a special case to get base classes.
                if child.text and \
                        (child.text.startswith("base classes — ") or
                         child.text.startswith("base class — ")):
                    base_classes = self._analyze_base_classes(filename, child)
            elif child.tag == "desc":     # <desc>
                if not base_classes:
                    r = self._analyze_desc(filename, child)
                    if r:
                        result.info_list.append(r)
                else:
                    r = self._analyze_desc_with_base_classes(filename, child, base_classes)
                    if r:
                        result.info_list.append(r)
            elif child.tag == "section":    # <section>
                self._analyze_section(filename, child, result)

    def _modify(self, result: 'AnalysisResult'):
        pass

    def _analyze_by_file(self, filename: str) -> 'AnalysisResult':
        self.filenames.append(filename)

        tree = et.parse(filename)
        root = tree.getroot()       # <document>
        result = AnalysisResult()
        for child in list(root):
            if child.tag == "section":    # <section>
                r: 'SectionInfo' = SectionInfo()
                self._analyze_section(filename, child, r)
                result.section_info.append(r)

        return result

    def analyze(self, filenames: List[str]) -> 'AnalysisResult':
        result = AnalysisResult()
        for f in filenames:
            r = self._analyze_by_file(f)
            result.section_info.extend(r.section_info)

        self._modify(result)

        return result


class AnalyzerWithModFile(BaseAnalyzer):
    def __init__(self, mod_files: List[str]):
        super(AnalyzerWithModFile, self).__init__()
        self._mod_files: List[str] = mod_files

    def _modify_with_mod_files(self, result: 'AnalysisResult'):
        for mod_file in self._mod_files:
            self._modify_with_mod_file(mod_file, result)

    def _modify_with_mod_file(self, mod_file: str, result: 'AnalysisResult'):
        with open(mod_file, encoding="utf-8") as f:
            data = json.load(f)

            # Process "remove" field
            #   - Remove item if the same item exists in AnalysisResult.
            if "remove" in data.keys():
                for item in data["remove"]:
                    for section in result.section_info:
                        remove_list = []
                        for info in section.info_list:
                            if ("type" not in item) or (info.type() != item["type"]):
                                continue
                            if ("name" not in item) or (info.name() != item["name"]):
                                continue
                            if (("module" in item) and (info.module() != item["module"])) or\
                               (("module" not in item) and (info.module() is None)):
                                remove_list.append(info)
                        for rm in remove_list:
                            section.info_list.remove(rm)
                            output_log(LOG_LEVEL_WARN,
                                       "{} (type={}) is removed"
                                       .format(rm.name(), rm.type()))

            # Process "new" field
            #   - Add item if the same item doesn't exist in AnalysisResult.
            if "new" in data.keys():
                new_section = SectionInfo()
                for item in data["new"]:

                    # check if entry is already registered
                    has_entry = False
                    for section in result.section_info:
                        for info in section.info_list:
                            if ("type" not in item) or (info.type() != item["type"]):
                                continue
                            if ("name" not in item) or (info.name() != item["name"]):
                                continue
                            if ("module" not in item) or (info.module() != item["module"]):
                                continue
                            has_entry = True
                            break
                        if has_entry:
                            break

                    if not has_entry:
                        if item["type"] == "constant":
                            new_v = VariableInfo("constant")
                            new_v.from_dict(item, 'NEW')
                            new_section.info_list.append(new_v)
                        elif item["type"] == "function":
                            new_f = FunctionInfo("function")
                            new_f.from_dict(item, 'NEW')
                            new_section.info_list.append(new_f)
                        elif item["type"] == "class":
                            new_c = ClassInfo()
                            new_c.from_dict(item, 'NEW')
                            new_section.info_list.append(new_c)
                        else:
                            raise RuntimeError("Unsupported Type: {}"
                                               .format(item["type"]))
                    else:
                        output_log(LOG_LEVEL_WARN,
                                   "{} is already registered"
                                   .format(item["name"]))

                result.section_info.append(new_section)

            # Process "append" field
            #   - Add item's field if the same exists in AnalysisResult.
            #   - Value of item's field must be None.
            if "append" in data.keys():
                for item in data["append"]:
                    for section in result.section_info:
                        for info in section.info_list:
                            if ("type" not in item) or (info.type() != item["type"]):
                                continue
                            if ("name" not in item) or (info.name() != item["name"]):
                                continue
                            if ("module" not in item) or (info.module() != item["module"]):
                                continue
                            info.from_dict(item, 'APPEND')

            # Process "update" field
            #   - Update item's field if the same exists in AnalysisResult.
            #   - Value of item's field can be None or some values.
            if "update" in data.keys():
                for item in data["update"]:
                    for section in result.section_info:
                        for info in section.info_list:
                            if ("type" not in item) or (info.type() != item["type"]):
                                continue
                            if ("name" not in item) or (info.name() != item["name"]):
                                continue
                            if ("module" not in item) or (info.module() != item["module"]):
                                continue
                            info.from_dict(item, 'UPDATE')

    def _modify_post_process(self, result: 'AnalysisResult'):
        pass

    def _modify(self, result: 'AnalysisResult'):
        self._modify_with_mod_files(result)
        self._modify_post_process(result)
