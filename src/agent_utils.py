import json
from typing import Any
import ast
import re


def mpc_arguments_to_python(arg_json: str) -> str:
    """ Convert list of function argument from json in Python style """

    if not arg_json:
        return ""

    arg_json = arg_json.strip()
    if not arg_json:
        return ""

    arg_str = ""
    data: dict[str, Any] = {}
    try:
        data = json.loads(arg_json)
    except Exception:
        if arg_json[-2:] == "}}":
            arg_json_ = arg_json[:-1]
        elif arg_json[-4:] == "}}\n]":
            arg_json_ = arg_json[:-3]
    if not data:
        try:
            data = json.loads(arg_json_)
        except Exception:
            pass
    if not data:
        start = arg_json.find("{")
        if start == -1:
            print(f"Error convert json to dict: json='{arg_json}'"
                  ', error=Not fond "{" ')
            return ""
        depth, end = 0, 0
        in_str = False
        for i, ch in enumerate(arg_json[start:], start):
            if ch == '"' and arg_json[i-1] != '\\':
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
            print(f"Error convert json to dict: json='{arg_json}'")
            return ""
        try:
            data = json.loads(arg_json[start:end])
        except Exception as ex:
            print(f"Error convert json to dict: json='{arg_json}', error={ex}")
            return ""

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
