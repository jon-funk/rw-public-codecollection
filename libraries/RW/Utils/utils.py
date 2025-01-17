"""
rw.utils defines some common functions available to Library/Keyword
authors as python interfaces.  Some of these are also exposed as
Robot Keywords via RW.Utils.
"""
from typing import Iterable, Any, Union, Optional
import os, pprint, functools, time, json, datetime, yaml, logging, re, xml.dom.minidom, urllib.parse
import jmespath, ast
from enum import Enum
from benedict import benedict
from robot.libraries.BuiltIn import BuiltIn

from RW import platform

logger = logging.getLogger(__name__)

# TODO: refresh funcs using outdated dependencies
# TODO: port RWUtils over to here / merge / deduplicate
# TODO: add control structure keywords

SYMBOL_GREEN_CHECKMARK: str = "\u2705"
SYMBOL_RED_X: str = "\u274C"


class Status(Enum):
    NOT_OK = 0
    OK = 1


def is_bytes(val) -> bool:
    return isinstance(val, bytes)


def is_str(val) -> bool:
    return isinstance(val, str)


def is_str_or_bytes(val) -> bool:
    return isinstance(val, (str, bytes))


def is_int(val) -> bool:
    return isinstance(val, int)


def is_float(val) -> bool:
    return isinstance(val, float)


def is_bool(val) -> bool:
    return isinstance(val, bool)


def is_scalar(val) -> bool:
    return isinstance(val, (int, float, str, bytes, bool, type(None)))


def is_list(val) -> bool:
    return isinstance(val, list)


def is_dict(val) -> bool:
    return isinstance(val, dict)


def is_xml(val) -> bool:
    if not val or not is_str_or_bytes(val):
        return False
    try:
        xml.dom.minidom.parseString(val)
    except xml.parsers.expat.ExpatError:
        return False
    return True


def is_yaml(val) -> bool:
    if not val or not is_str_or_bytes(val):
        return False
    try:
        yaml.safe_load(val)
    except yaml.scanner.ScannerError:
        return False
    return True


def is_json(val, strict: bool = False) -> bool:
    if not val or not is_str_or_bytes(val):
        return False
    try:
        json.loads(val, strict=strict)
    except ValueError:
        return False
    return True


def from_json(json_str, strict: bool = False) -> object:
    if is_json(json_str, strict=strict):
        return json.loads(json_str, strict=strict)
    else:
        return json_str


def to_json(data: object) -> str:
    return json.dumps(data)


def string_to_json(data: str) -> str:
    return json.loads(data)


def search_json(data: dict, pattern: str) -> dict:
    result = jmespath.search(pattern, data)
    return result


def json_to_metric(
    data: str = "", search_filter: str = "", calculation_field: str = "", calculation: str = "Count"
) -> float:
    """Takes in a json data result from kubectl and calculation parameters to return a single float metric.
    Assumes that the return is a "list" type and automatically searches through the "items" list, along with
    other search filters provided buy the user (using jmespath search).

    Args:
        :data str: JSON data to search through.
        :search_filter str: A jmespah filter used to help filter search results. See https://jmespath.org/? to test search strings.
        :calculation_field str: The field from the json output that calculation should be performed on/with.
        :calculation_type str:  The type of calculation to perform. count, sum, avg.
        :return: A float that represents the single calculated metric.
    """
    # Fix up single quoted json if necessary
    data = json.dumps(ast.literal_eval(data))

    # Validate json
    if is_json(data) is False:
        raise ValueError(f"Error: Data does not appear to be valid json")
    else:
        payload = json.loads(data)

    if not calculation_field:
        raise ValueError(f"Error: Calculation field must be set for calcluations that are sum or avg.")
    # Perform calculations
    search_pattern_prefix = search_filter

    if calculation == "Count":
        search_results = search_json(data=payload, pattern=search_pattern_prefix)
        return len(search_results)
    if calculation == "Sum":
        metric = search_json(data=payload, pattern="sum(" + search_pattern_prefix + "." + calculation_field + ")")
        return float(metric)
    if calculation == "Avg":
        metric = utils.search_json(data=payload, pattern="avg(" + search_pattern_prefix + "." + calculation_field + ")")
        return float(metric)


def from_yaml(yaml_str) -> object:
    if is_yaml(yaml_str):
        return yaml.load(yaml_str, Loader=yaml.SafeLoader)
    else:
        return yaml_str


def to_yaml(data: object) -> str:
    return yaml.dump(data)


def to_str(v) -> str:
    if is_bytes(v):
        return v.decode("unicode_escape")  # remove double forward slashes
    else:
        return str(v)


def to_bool(v) -> bool:
    """
    Convert the input parameter into a boolean value.
    """
    if is_bool(v):
        return v
    if is_str_or_bytes(v):
        if v.lower() == "true":
            return True
        elif v.lower() == "false":
            return False
    raise platform.TaskError(f"{v!r} is not a boolean value.")


def to_int(v) -> Union[int, list[int]]:
    """
    Convert the input parameter, which may be a scalar or a list, into
    integer value(s).
    """
    if is_scalar(v):
        return int(v)
    elif is_list(v):
        return [int(x) for x in v]
    else:
        raise ValueError(f"Expected a scalar or list value (actual value: {v})")


def to_float(v) -> Union[float, list[float]]:
    """
    Convert the input parameter, which may be a scalar or a list, into
    float value(s).
    """
    if is_scalar(v):
        return float(v)
    elif is_list(v):
        return [float(x) for x in v]
    else:
        raise ValueError(f"Expected a scalar or list value (actual value: {v})")


def prettify(data) -> str:
    return pprint.pformat(data, indent=1, width=80)


def _calc_latency(func):
    """Calculate the runtime of the specified function."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        (default_ndigits, unit) = kwargs.pop("latency_params")
        ndigits = kwargs.get("ndigits", default_ndigits)
        if ndigits is not None:
            ndigits = int(ndigits)
        kwargs.pop("ndigits", None)

        start_time = time.perf_counter()
        val = func(*args, **kwargs)
        end_time = time.perf_counter()
        run_time = end_time - start_time
        platform.debug_log(
            f"Executed in {run_time:.5f} secs",
            console=False,
        )
        if unit not in ["s", "ms"]:
            raise platform.TaskError(f"Latency unit is {unit!r} (should be 's' or 'ms').")
        if unit == "ms":
            run_time *= 1000.0
        return (round(run_time, ndigits), val)

    return wrapper


def latency(func, *args, **kwargs):
    @_calc_latency
    def doit(*args, **kwargs):
        return func(*args, **kwargs)

    return doit(*args, **kwargs)


def parse_url(url: str, verbose: bool = False) -> Union[str, int]:
    parsed_url = urllib.parse.urlparse(url)
    if verbose:
        platform.debug_log(f"URL components: {parsed_url}", console=False)
    return parsed_url


def encode_url(hostname: str, params: dict, verbose: bool = False) -> str:
    query_string = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    encoded_url = hostname + query_string
    if verbose:
        platform.debug_log(f"Encoded URL: {encoded_url}", console=False)
    return encoded_url


def parse_numerical(numeric_str: str):
    return float("".join(i for i in numeric_str if i.isdigit() or i in [".", "-"]))


def parse_timedelta(timestring: str) -> datetime.timedelta:

    timedelta_regex = r"((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?"
    pattern = re.compile(timedelta_regex)

    match = pattern.match(timestring)
    if match:
        parts = {k: int(v) for k, v in match.groupdict().items() if v}
        # TODO: Deal with negative timedelta values?
        return datetime.timedelta(**parts)
    else:
        raise platform.TaskError(f"{timestring!r} is not a valid time duration.")


def stdout_to_list(stdout: str, delimiter: str = ""):
    if delimiter:
        return stdout.split(delimiter)
    return stdout.split()


def stdout_to_grid(stdout):
    stdout_grid = []
    for line in stdout.splitlines():
        stdout_grid.append(line.split())
    return stdout_grid


def get_stdout_grid_column(stdout_grid, index: int):
    """
    Helper function to return a column as a list from the stdout lists of a kubectl command
    """
    result_column = []
    for row in stdout_grid:
        result_column.append(row[index])
    return result_column


def remove_units(
    data_points,
):
    """
    Iterates over list and removes units
    """
    cleaned = []
    for d in data_points:
        numerical = float("".join(i for i in d if i.isdigit() or i in [".", "-"]))
        cleaned.append(numerical)
    return cleaned


def aggregate(method: str, column: list):
    method = method.capitalize()
    if method == "Max":
        return max(column)
    elif method == "Average":
        return sum(column) / len(column)
    elif method == "Minimum":
        return min(column)
    elif method == "Sum":
        return sum(column)
    elif method == "First":
        return column[0]
    elif method == "Last":
        return column[-1]


def yaml_to_dict(yaml_str: str):
    return yaml.safe_load(yaml_str)


def dict_to_yaml(data: Union[dict, benedict]):
    if isinstance(data, benedict):
        return data.to_yaml()
    return yaml.dump(data)


def list_to_string(data_list: list, join_with: str = "\n") -> str:
    return join_with.join(data_list)


def string_if_else(check_boolean: bool, if_str: str, else_str) -> str:
    return if_str if check_boolean else else_str


def remove_spaces(initial_str: str, remove: list[str] = [" ", "\n", "\t"]) -> str:
    result_str = initial_str
    for symbol in remove:
        result_str: str = result_str.replace(symbol, "")
    return result_str


def csv_to_list(csv_str: str, strip_entries: bool = True) -> list:
    csv_list: list = []
    if csv_str == "":
        csv_list = []
    else:
        csv_list = csv_str.split(",")
    if csv_list and strip_entries:
        csv_list = [entry.strip() for entry in csv_list]
    return csv_list


def lists_to_dict(keys: list, values: list) -> dict:
    return dict(zip(keys, values))


def templated_string_list(template_string: str, values: list, key_name="item") -> list:
    str_list: list = []
    for value in values:
        format_map = {key_name: value}
        str_list.append(template_string.format(**format_map))
    return str_list


def create_secrets_list(*args) -> [platform.Secret]:
    secrets_list: [platform.Secrets] = []
    for arg in args:
        if isinstance(arg, platform.Secret):
            secrets_list.append(arg)
    return secrets_list


def get_source_dir() -> str:
    builtin: BuiltIn = BuiltIn()
    src_path = builtin.get_variable_value("${SUITE SOURCE}")
    src_dir = "/".join(src_path.split("/")[:-1])
    return src_dir


def create_secret(key: str, val: Any) -> platform.Secret:
    return platform.Secret(key, val)


def merge_json_secrets(*args) -> platform.Secret:
    secret_data: dict = {}
    for secret in args:
        if not isinstance(secret, platform.Secret):
            break
        secret_value = secret.value
        if not is_json(secret_value):
            break
        secret_value = from_json(secret_value)
        secret_data = {**secret_data, **secret_value}
    secret_data = to_json(secret_data)
    merged_secret: platform.Secret = platform.Secret("json_secrets", secret_data)
    return merged_secret


def secret_to_curl_headers(
    optional_headers: platform.Secret,
    default_headers: str = '{"content-type": "application/json"}',
) -> platform.Secret:
    header_list = []
    headers = json.loads(default_headers)
    headers.update(json.loads(optional_headers.value))
    for k, v in headers.items():
        header_list.append(f'-H "{k}: {v}"')
    sec_val = " ".join(header_list)
    if not sec_val:
        sec_val = ""
    optional_headers: platform.Secret = platform.Secret(key=optional_headers.key, val=sec_val)
    return optional_headers


def create_curl(cmd, optional_headers: platform.Secret = None) -> str:
    """
    Helper method to generate a curl string equivalent to a Requests object (roughly)
    Note that headers are inserted as a $variable to be substituted in the location service by an environment variable.
    This is identified by the secret.key
    """
    secret_headers: str = f"${optional_headers.key}" if optional_headers and optional_headers.value else ""
    # Check for pipes in command
    if "|" in cmd:
        # split command at first pipe
        cmd_segments = cmd.split("|")
        cmd_prefix = cmd_segments[0]
        # handle subsequent pipes
        cmd_suffix = "|".join(cmd_segments[1:])
        # we use eval so that the location service evaluates the secret headers as multiple tokens
        curl = f'eval $(echo "{cmd_prefix} {secret_headers} | {cmd_suffix} ")'
    else:
        # we use eval so that the location service evaluates the secret headers as multiple tokens
        curl = f'eval $(echo "{cmd} {secret_headers} ")'
    return curl


def quote_curl(curl: str) -> str:
    """Simple helper method to escape specific characters in complex curl commands

    Args:
        query (str): the curl string to execute

    Returns:
        str: a curl string with inner " characters escaped to prevent shell eval issues
    """
    curl = curl.replace('"', '\\"')
    return curl


def rate_of_occurence(
    data: list,
    count_value: any,
    default_value: float = None,
    operand: str = "Equals",
) -> float:
    rate: float = default_value
    try:
        if operand == "Greater Than":
            rate = len([val for val in data if val > count_value]) / len(data)
        elif operand == "Less Than":
            rate = len([val for val in data if val < count_value]) / len(data)
        else:  # assume Equals
            # note that count is sensitive to the type, eg: 1000 != 1000.0
            rate = data.count(count_value) / len(data)
    except Exception as e:
        logger.warning(f"Encountered {e} while calculating rate of occurence with {count_value} {operand} {data}")
        if default_value == None:
            logger.error(f"The default value: {default_value} is None raising exception up")
            raise e
    return rate
