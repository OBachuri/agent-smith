import json
from typing import Any
import ast
import re


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
