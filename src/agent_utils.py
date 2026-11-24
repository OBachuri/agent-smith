import json
from typing import Any
import ast
import re
import xml.etree.ElementTree as ET


def check_str_is_json_dict(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False

    text = raw.strip()
    # Standard JSON parsing.
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(result, dict)


def normalize_json_arguments(raw: Any) -> dict[str, Any]:
    """Convert model tool arguments into a Python dictionary."""

    # Some providers return a dictionary instead of a JSON string.
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        raise ValueError(
            "Arguments must be a string(json), "
            f"got {type(raw).__name__}"
        )

    text = raw.strip()

    # Remove Markdown code fences at the beginning and the end
    text = re.sub(
        r"^```(?:json|python)?\s*|\s*```$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    if not text:
        # raise ValueError("Empty tool arguments")
        return {}

    result: dict[str, Any] = {}
    error: str = ""

    # Standard JSON parsing.
    try:
        result = json.loads(text)
    except json.JSONDecodeError as ex:
        error += f'{ex}\n'

    if not result:
        # try to find {}
        start = text.find("{")
        if start == -1:
            error += ("Error convert json to dict -"
                      'Not fond "{"\n'
                      f'json={text[:500]}')
            raise ValueError(error)

        depth, end = 0, 0
        in_str = False
        for i, ch in enumerate(text[start:], start):
            if ch == '"' and text[i-1] != '\\':
                in_str = not in_str
            elif not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
        if end == 0:
            # error += ("Error convert json to dict -"
            #           'Not fond "}"\n'
            #           f'json={text[:500]}')
            # raise ValueError(error)
            text += "}"*(depth)
            end = len(text)
        text = text[start:end]
        # print("edit_text:",text)

    # Second try as standard JSON parsing.
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        pass

    if not result:
        # Safe fallback for Python dictionary literals:
        # single quotes, True, False, None, etc.
        try:
            result = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            pass

    if not isinstance(result, dict):
        raise ValueError("Tool arguments must be a JSON object")

    return result


def mpc_arguments_to_python(arg_json: Any) -> str:
    """ Convert list of function argument from json in Python style """

    if not arg_json:
        return ""

    try:
        data = normalize_json_arguments(arg_json)
    except Exception as ex:
        print("Error parse arguments as json:", ex, "\n", arg_json)
        return ""

    arg_str: str = ""

    if data:
        for d_key in data.keys():
            if arg_str:
                arg_str += ", "
            d = data.get(d_key, None)
            if d is None:
                arg_str += d_key + "=None"
            else:
                arg_str += d_key + "=" + json.dumps(d)

    return arg_str


def it_is_python_code(txt: str) -> bool:
    """ Check if in text Python code"""

    if not txt or txt.strip() == '':
        return False
    try:
        # ast.parse throws a SyntaxError if the string is not valid Python
        ast.parse(txt)

        # Additional safety check: empty strings or plain single words
        # (like "Python") are technically valid single-expression ASTs,
        # but they aren't "programs". We check if there's actual structure.
        return True
    except SyntaxError:
        return False


def it_is_tool_call(code_txt: str, func_lst: list[str]) -> list[str]:

    """ Check if in text Python code with tool call"""

    # First try to find with text search

    pattern = r'\b(' + '|'.join(map(re.escape, func_lst)) + r')\s*\('
    lst_ = re.findall(pattern, code_txt)
    if not lst_:
        return []

    # Check if that it was in code, not in some comments
    res_: list[str] = []

    try:
        tree = ast.parse(code_txt)
    except Exception:
        # can`t parce this text as Python code
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name in lst_:
                    res_.append(name)
    return res_


def repair_xml(xml: str) -> str:
    # Escape ampersands that are not already valid XML entities
    return re.sub(
        r"&(?!#\d+;|#x[0-9a-fA-F]+;|[a-zA-Z][a-zA-Z0-9._-]*;)",
        "&amp;",
        xml
    )


def extract_xml_block(
    text: str,
    root_tag: str = "tool_call"
) -> tuple[str, int]:
    """
    Extract the first balanced XML block.
    Returns (xml_block_text, end_of_block_pos).
    root_tag: str = "ernie:tool_call"
    """

    start_pattern = re.compile(
        r"<" + re.escape(root_tag) + r"(?=[\s>/])"
    )

    match = start_pattern.search(text)

    if not match:
        return "", 0

    start = match.start()
    pos = match.end()
    depth = 1

    while pos < len(text):
        tag_start = text.find("<", pos)

        if tag_start == -1:
            break

        # Comments
        if text.startswith("<!--", tag_start):
            end = text.find("-->", tag_start + 4)
            if end == -1:
                break
            pos = end + 3
            continue

        # CDATA
        if text.startswith("<![CDATA[", tag_start):
            end = text.find("]]>", tag_start + 9)
            if end == -1:
                break
            pos = end + 3
            continue

        # Processing instructions
        if text.startswith("<?", tag_start):
            end = text.find("?>", tag_start + 2)
            if end == -1:
                break
            pos = end + 2
            continue

        # Find the end of the tag, ignoring quoted >
        quote = None
        tag_end = tag_start + 1

        while tag_end < len(text):
            char = text[tag_end]

            if quote:
                if char == quote:
                    quote = None
            elif char in ('"', "'"):
                quote = char
            elif char == ">":
                break

            tag_end += 1

        if tag_end >= len(text):
            break

        tag = text[tag_start:tag_end + 1].strip()

        closing = tag.startswith("</")
        self_closing = tag.endswith("/>")

        if closing:
            depth -= 1
        elif not tag.startswith("<!") and not self_closing:
            depth += 1

        if depth == 0:
            end = tag_end + 1
            return text[start:end], end

        pos = tag_end + 1

    return "", 0


def parse_function_tool_calls(response: str) -> list[dict]:
    """
    Parse liquid/lfm-3-1.7b tool call. Example:

    <tool_call>
        <function=read_file>
            <parameter=path>/usr/local/lib/python3.6/site-packages/sympy/physics/vector/vector.py</parameter>
        </function>
    </tool_call>
    """

    calls = []

    function_pattern = re.compile(
        r"<function=([a-zA-Z_][\w.-]*)\s*>(.*?)</function\s*>",
        re.DOTALL
    )

    parameter_pattern = re.compile(
        r"<parameter=([a-zA-Z_][\w.-]*)\s*>(.*?)</parameter\s*>",
        re.DOTALL
    )

    for function_match in function_pattern.finditer(response):
        name = function_match.group(1)
        body = function_match.group(2)

        arguments = {}

        for param_match in parameter_pattern.finditer(body):
            param_name = param_match.group(1)
            param_value = param_match.group(2).strip()

            if param_name in arguments:
                raise ValueError(f"Duplicate parameter: {param_name}")

            arguments[param_name] = param_value

        calls.append({
            "name": name,
            "arguments": arguments
        })

    return calls


def parse_ernie_tool_calls(raw_response: str) -> tuple[list[dict], str]:
    """
    Parse XML tool calls - Anthropic-style <invoke
    name="..."><parameter>...</parameter></invoke>

    return:
        res: list[dict] - list of dict, dict =
                {"name":str, arguments:{name:str, value:any}}
        Error: str - Errors text
    """

    t_str = raw_response.replace(
        "<ernie:", "<").replace(
            "</ernie:", "</")
    calls = []
    errors_ = ""
    start = t_str.find("<tool_call")
    while start >= 0:
        end = t_str.rfind("<tool_call", start)
        xml = ""
        if start == end:  # only one <tool_call
            end = t_str.rfind("</tool_call", start)
            if end >= 0:
                end = t_str.find(">", end) + 1
        else:
            xml, end = extract_xml_block(t_str[start:])
            if end > 0:
                end += start + 1
        if end > start:  # something found
            if not xml:
                xml = t_str[start:end]
            start = t_str.find("<tool_call", start + 10)
            #  print("---", xml, "---")
            root = None
            try:
                root = ET.fromstring(xml)
            except Exception as ex:
                error_ = (
                    "Error parsing tool call in Anthropic-style:"
                    f"\n{ex}\n"
                    "Source text that can't be parse as xml:\n"
                    f"```{xml}```\n")
                if xml.find("&") > 0:
                    error_ += "May be '&' must be escaped like that '&amp;'\n"
                errors_ += error_
                print(error_)

            if root is None:
                xml_e = repair_xml(xml)
                try:
                    root = ET.fromstring(xml_e)
                except Exception:
                    pass

            if root is None:
                try:
                    c_ = parse_function_tool_calls(xml)
                    if c_:
                        calls.extend(c_)
                except Exception:
                    pass
                continue

            if root.tag != "tool_call":
                continue

            for invoke in root.findall("invoke"):
                name = invoke.get("name", "")
                if not name:
                    continue

                arguments = {}

                for param in invoke.findall("parameter"):
                    key = param.get("name", "")
                    if not key:
                        continue

                    value = param.text or ""

                    # Attempt JSON decoding for non-string values
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        pass

                    arguments[key] = value

                calls.append({
                    "name": name,
                    "arguments": arguments
                })
        else:
            start = t_str.find("<tool_call", start + 10)

    return calls, errors_


def mpc_result_to_txt(r_str: str | list[str]) -> str | list[str]:
    # Return "result" from MCP response

    if isinstance(r_str, str) and "result" in r_str:
        try:
            # Parse as JSON into an object
            json_ = json.loads(r_str)
            return str(json_.get("result", r_str))
        except Exception:
            pass
        try:
            # Parse outer string to dict using AST
            data_dict = ast.literal_eval(r_str)
            return str(data_dict.get("result", r_str))
        except Exception:
            return r_str
    return r_str


def has_function_def(txt_code: str, function_definition: str) -> bool:
    try:
        # 1. Parse the target definition
        # (add 'pass' so it becomes valid syntax)
        target_tree = ast.parse(function_definition.strip() + "\n    pass")
        target_func = target_tree.body[0]

        # Ensure the provided definition is actually a function
        if not isinstance(target_func, ast.FunctionDef):
            return False

        # 2. Parse the code you want to check (verifies it is valid Python)
        code_tree = ast.parse(txt_code)
    except SyntaxError:
        # Returns False if txt_code or function_definition is invalid Python
        return False

    # Extract target name and parameter names
    target_name = target_func.name
    target_args = [arg.arg for arg in target_func.args.args]

    # 3. Walk through the code's AST to find a matching function definition
    for node in ast.walk(code_tree):
        if (isinstance(node, ast.FunctionDef)
           or isinstance(node, ast.AsyncFunctionDef)):
            node_args = [arg.arg for arg in node.args.args]
            if node.name == target_name and node_args == target_args:
                return True

    return False


def extract_function_code(txt_code: str, function_definition: str) -> str:
    try:
        # 1. Parse the target definition
        target_tree = ast.parse(function_definition.strip() + "\n    pass")
        target_func = target_tree.body[0]

        if not isinstance(target_func, ast.FunctionDef):
            return ""

        # 2. Parse the full code string
        code_tree = ast.parse(txt_code)
    except SyntaxError:
        return ""

    target_name = target_func.name
    target_args = [arg.arg for arg in target_func.args.args]

    # 3. Find the matching function and extract its exact source text
    for node in ast.walk(code_tree):
        if (isinstance(node, ast.FunctionDef)
           or isinstance(node, ast.AsyncFunctionDef)):
            node_args = [arg.arg for arg in node.args.args]
            if node.name == target_name and node_args == target_args:
                # Extracts the exact code block of the function from txt_code
                extracted = ast.get_source_segment(txt_code, node)
                return extracted if extracted is not None else ""

    return ""
