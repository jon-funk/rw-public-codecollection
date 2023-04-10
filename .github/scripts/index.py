import argparse, yaml, subprocess, os, logging
from robot.api import TestSuite
# pip install robotframework

logger = logging.getLogger(__name__)

def clone_repos(repo_urls: list[str]) -> list[str]:
    tmp_dir_list: list[str] = []
    for tmp_dir_name, repo_url in repo_urls.items():
        clone_directory = f"/tmp/{tmp_dir_name}"
        tmp_dir_list.append(clone_directory)
        if os.path.exists(clone_directory):
            print(f"Directory {clone_directory} already exists, skipping and assuming it's been cloned already!")
            continue
        git_command = ['git', 'clone', repo_url, clone_directory]
        return_code = subprocess.call(git_command)
        if return_code == 0:
            print('Git clone succeeded!')
        else:
            print('Git clone failed with exit code:', return_code)
    return tmp_dir_list

def get_codebundle_paths(root_repo_filepaths: list[str], search_patterns: dict) -> dict[str,str]:
    """
    Returns a list of absolute filepaths for all files in the specified
    directory (and its subdirectories) that match the specified pattern.
    """
    matching_filepaths = {}
    for search_dir, filename_pattern in search_patterns.items():
        for repo_path in root_repo_filepaths:
            if repo_path not in matching_filepaths:
                matching_filepaths[repo_path] = []
            for root, dirs, files in os.walk(repo_path):
                for filename in files:
                    if filename.endswith(filename_pattern) and "robot_tests" not in root:
                        filepath = os.path.join(root, filename)
                        matching_filepaths[repo_path].append(os.path.abspath(filepath))
    return matching_filepaths

def parse_codebundle(codebundle_path: str) -> dict:
    parse_result = {}
    test_suite = TestSuite.from_file_system(codebundle_path)
    parse_result["keywords"] = []
    for user_keyword in test_suite.resource.keywords:
        for keyword in user_keyword.body:
            parse_result["keywords"].append(keyword)
    parse_result["tasks"] = []
    for test in test_suite.tests:
        parse_result["tasks"].append({"name": test.name, "tags": str(test.tags), "doc": test.doc})
    parse_result["metadata"] = dict(test_suite.metadata)
    parse_result["doc"] = test_suite.doc
    return parse_result

def parse_codebundles(codebundle_filepaths: list[str]) -> dict:
    parse_data = {}
    for cb_path in codebundle_filepaths:
        try:
            parse_data[cb_path] = parse_codebundle(cb_path)
        except Exception as e:
            logger.warning(f"Unable to parse codebundle due to: {e}")
    return parse_data

def organize_results(repo_mapping: dict, codebundle_paths: list[str], parse_results: dict) -> list:
    organized_results = []
    branch = "main"
    for cb_name, cb_data in parse_results.items():
        path_parts = cb_name.split("/")
        repo_name = path_parts[2]
        repo_url = repo_mapping[repo_name]
        cb_path = "/".join(path_parts[-3:])
        name = path_parts[-2]
        supports = ", ".join([f"`{name.split('-')[0]}`"]) # eg: gets ['k8s'] for k8s codebundles
        metadata = cb_data["metadata"]
        if "Canonical Name" in metadata:
            name = metadata["Canonical Name"]
        if "Supports" in metadata:
            supports = ", ".join([f"`{support_val.strip()}`" for support_val in metadata["Supports"].split(",")])
        repo_file_url = f"{repo_url.removesuffix('.git')}/blob/{branch}/{cb_path}"
        linked_name = f"[{name}]({repo_file_url})"
        current_result = [linked_name, supports,cb_data["doc"]]
        organized_results.append(current_result)
    return organized_results

if __name__ == '__main__':
    # Create the parser
    parser = argparse.ArgumentParser(description='Takes a yaml file configuration and produces a table of codebundle details.')

    # Add arguments to the parser
    parser.add_argument('config', help='The yaml config file containing the list of git URLs to clone and parse')
    parser.add_argument('--readme_header', default="../../readme_header.md", help='The filepath to the header content file to be placed at the top of the readme',)
    parser.add_argument('--readme', default="../../README.md", help='The readme filepath to write the resulting content to')

    # Parse the arguments
    args = parser.parse_args()

    # Open the YAML file
    with open(args.config, 'r') as config_file:
        # Load the file contents as a dictionary
        index_config = yaml.safe_load(config_file)

    # Call the main function with the arguments
    print(f"Configuration set as:")
    print(args.config)
    print(index_config)
    tmp_dir_repos: list[str] = clone_repos(index_config["repos"])
    print(f"List of repo filepaths: {tmp_dir_repos}")
    repo_to_codebundles: dict = {}
    repo_to_codebundles = get_codebundle_paths(tmp_dir_repos, index_config["robot_file_pattern"])
    # list of list of codebundle paths to single list
    codebundle_path_list: list[str] = [cb_path for cb_paths in repo_to_codebundles.values() for cb_path in cb_paths]
    # print(f"Found codebundles: {codebundle_path_list}")
    parse_results: dict = parse_codebundles(codebundle_path_list)
    # print(f"Parse results: {parse_results}")

    readme_header_content: str = ""
    with open(args.readme_header, 'r') as header_file:
        readme_header_content = header_file.read()
    print(f"readme header: {readme_header_content}")

    organized_results: dict = organize_results(index_config["repos"], codebundle_path_list, parse_results)
    print(organized_results)

    # table_content: str = create_codebundle_table(parse_results)

    # readme_content: str = f"{readme_header_content}"
    # with open(args.readme, 'w') as readme_file:
    #     readme_file.write(readme_content)

