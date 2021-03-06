import requests
import os
from collections import defaultdict
from urllib.parse import urljoin
from pathlib import Path

def access_commands(arguments, config):
    print('Running ACCESS')
    if arguments.get('link-bams'):
        return run_access_folder_bam_link_command(arguments, config)

    if arguments.get('link'):
        return run_access_folder_link_command(arguments, config)


def get_pipeline(name, config):
    response = requests.get(urljoin(config['beagle_endpoint'],
                                    "{}?name={}".format(config['api']['pipelines'], name)),
                            headers={'Authorization': 'Bearer %s' % config['token']})

    try:
        pipeline = response.json()["results"][0]
    except Exception as e:
        print("Pipeline 'access legacy' does not exist")
        quit()
    return pipeline

def get_group_id(tags, apps, config):
    latest_run_params = {
        "tags": tags,
        "status": "COMPLETED",
        "page_size": 1,
        "apps": apps
    }

    response = requests.get(urljoin(config['beagle_endpoint'], config['api']['run']),
                            headers={'Authorization': 'Bearer %s' % config['token']}, params=latest_run_params)

    latest_runs = response.json()["results"]
    if not latest_runs:
        print("There are no runs for this id")
        quit()

    return latest_runs[0]["job_group"]

def get_arguments(arguments):
    request_id = arguments.get('--request-id')
    sample_id = arguments.get('--sample-id')
    if request_id:
        request_id = request_id[0]
    return request_id, sample_id


def get_runs(tags, apps, config):
    group_id = get_group_id(tags, apps, config)

    run_params = {
        "tags": tags,
        "status": "COMPLETED",
        "page_size": 1000,
        "job_groups": [group_id],
        "apps": apps
    }

    response = requests.get(urljoin(config['beagle_endpoint'], config['api']['run']),
                            headers={'Authorization': 'Bearer %s' % config['token']}, params=run_params)

    return response.json()["results"]

def get_run_by_id(run_id, config):
    response = requests.get(urljoin(config['beagle_endpoint'], config['api']['run'] + run_id),
                            headers={'Authorization': 'Bearer %s' % config['token']})

    return response.json()


def get_files_by_run_id(run_id, config):
    response = requests.get(urljoin(config['beagle_endpoint'], config['api']['run'] + run_id),
                            headers={'Authorization': 'Bearer %s' % config['token']})

    return response.json()["outputs"]

def get_file_path(file):
    return file["location"][7:]

def run_access_folder_link_command(arguments, config):
    request_id, sample_id = get_arguments(arguments)

    pipeline = get_pipeline("access legacy", config)
    version = arguments.get("--dir-version") or pipeline["version"]

    path = Path("./")
    path_without_version = path / ("Project_" + request_id) / "bam_qc"
    path = path_without_version / version
    path.mkdir(parents=True, exist_ok=True, mode=0o755)

    tags = "cmoSampleIds:%s" % sample_id if sample_id else "requestId:%s" % request_id
    apps = [pipeline["id"]]

    runs = get_runs(tags, apps, config)

    files = [] # (sample_id, /path/to/file)
    for run_meta in runs:
        run = get_run_by_id(run_meta["id"], config)
        try:
            os.symlink(run["output_directory"], path / run["id"])
        except Exception as e:
            print("could not create symlink from '{}' to '{}'".format(run["output_directory"], path / run["id"]))

    os.symlink(path.absolute(), path_without_version / "current")
    return "Completed"

def run_access_folder_bam_link_command(arguments, config):
    request_id, sample_id = get_arguments(arguments)

    pipeline = get_pipeline("access legacy", config)
    version = arguments.get("--dir-version") or pipeline["version"]

    path = Path("./")

    tags = "cmoSampleIds:%s" % sample_id if sample_id else "requestId:%s" % request_id
    apps = [pipeline["id"]]

    runs = get_runs(tags, apps, config)

    files = [] # (sample_id, /path/to/file)
    for run in runs:
        for file_group in get_files_by_run_id(run["id"], config):
            files = files + find_files_by_sample(file_group["value"], sample_id=sample_id)

    accepted_file_types = ['.bam', '.bai']
    for (sample_id, file) in files:
        file_path = get_file_path(file)
        _, file_ext = os.path.splitext(file_path)

        if file_ext not in accepted_file_types:
            continue

        file_name = os.path.basename(file_path)

        sample_id, _ = file_name.split("_", 1)
        a, b, _ = sample_id.split("-", 2)
        patient_id = "-".join([a, b])

        sample_path = path / patient_id / sample_id
        sample_version_path = sample_path / version
        sample_version_path.mkdir(parents=True, exist_ok=True, mode=0o755)

        try:
            os.symlink(file_path, sample_version_path / file_name)
        except Exception as e:
            print("could not create symlink from '{}' to '{}'".format(sample_version_path / file_name, file_path))
            continue

        try:
            os.symlink(sample_version_path.absolute(), sample_path / "current")
        except Exception as e:
            pass

    return "Completed"

def find_files_by_sample(file_group, sample_id = None):
    def traverse(file_group):
        files = []
        if type(file_group) == list:
            if len(file_group) > 1:
                return traverse(file_group[0]) + traverse(file_group[1:])
            elif file_group:
                return traverse(file_group[0])
        elif "file" in file_group:
            try:
                file_sample_id = file_group["sampleId"]
                if "File" == file_group["file"]["class"] and (not sample_id or
                                                              file_sample_id ==
                                                              sample_id):
                    print(file_group["file"]["basename"])
                    if file_group["file"]["basename"] == "C-0EU9LX-L015-d_cl_aln_srt_MD_IR_FX_BR__aln_srt_IR_FX.bam":
                        print("Here's our file")
                        print(file_group["file"]["secondaryFiles"])
                    return [(file_sample_id, file_group["file"])] + [(file_sample_id,
                                                                      f) for f in file_group["file"]["secondaryFiles"]]
            except Exception as e:
                print("ERROR:")
                print(e)
                print(file_group)
        elif "class" in file_group:
            if file_group["class"] == "Directory":
                return find_files_by_sample(file_group["listing"], sample_id=file_group["basename"])
            # TODO pull patient id here
            elif file_group["class"] == "File":
                secondary_files = [(sample_id, f) for f in file_group["secondaryFiles"]] if "secondaryFiles" in file_group else []
                return [(sample_id, file_group)] + secondary_files

        return []

    return traverse(file_group)

