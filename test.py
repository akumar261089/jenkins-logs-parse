import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from datetime import datetime
import os
import re, json

# Function to sanitize log text
def sanitize_log_text(text):
    return re.sub(r'[^\x00-\x7F]+', '', text)  # Remove non-ASCII characters
# Convert duration from milliseconds to a human-readable format
def format_duration(milliseconds):
    seconds = milliseconds / 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"

# Convert timestamp from milliseconds since epoch to a human-readable format
def format_timestamp(milliseconds):
    return datetime.fromtimestamp(milliseconds / 1000).strftime('%Y-%m-%d %H:%M:%S')

def preprocess_logs(log_lines):
    cleaned_logs = []
    for line in log_lines:
        # Removing timestamps for simplicity in this example
        cleaned_line = re.sub(r'\[.*?\]', ' ', line)
        cleaned_logs.append(cleaned_line)
    return ''.join(cleaned_logs)

# Function to sanitize URLs for use in directory names
def sanitize_for_filesystem(name):
    return re.sub(r'[^\w\-_.]', '_', name)

def extract_features(log_text):
    current_stage = None
    error = None
    repo_url = None
    pom_path = None
    groovy_path = None
    timestamp = None
    error_stage = None
    error_msg = None

    log_lines = log_text.split('\n')

    for line in log_lines:
        # Extract timestamp
        timestamp_match = re.search(r'^\[(.*?)\]', line)
        try:
            if timestamp_match:
                timestamp = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
        except Exception as errT:
            print(f"Error accessing timestamp  {timestamp_match}  in line {line}: {errT}")   
        # Extract stage information
        stage_match = re.search(r'Stage "(.*?)" started', line)
        if stage_match:
            current_stage = stage_match.group(1)

        # Extract error messages
        error_match = re.search(r'ERROR: (.*)', line)
        if error_match:
            error = error_match.group(1)
            error_stage = current_stage
            error_msg = error

        # Extract repository URL
        repo_match = re.search(r'Checking out code from (https://.*?)', line)
        if repo_match:
            repo_url = repo_match.group(1)

        # Extract paths to specific files
        pom_match = re.search(r'Loading POM file from (.*)', line)
        if pom_match:
            pom_path = pom_match.group(1)

        groovy_match = re.search(r'Loading Groovy script from (.*)', line)
        if groovy_match:
            groovy_path = groovy_match.group(1)

    return {
        'timestamp': timestamp,
        'error_stage': error_stage,
        'error_msg': error_msg,
        'repo_url': repo_url,
        'pom_path': pom_path,
        'groovy_path': groovy_path
    }

# Function to download job logs
def download_job_logs(jenkins_url, auth=None):
    try:
        # Get the list of jobs from the Jenkins instance
        jobs_url = f"{jenkins_url}/api/json?tree=jobs[name,url]"
        response = requests.get(jobs_url, auth=auth)
        response.raise_for_status()
        jobs = response.json()['jobs']

        # Create a subfolder for the current Jenkins URL
        sanitized_url = sanitize_for_filesystem(jenkins_url)
        log_dir = os.path.join('logs', sanitized_url)
        os.makedirs(log_dir, exist_ok=True)

        job_features_list = []

        for job in jobs:
            try:
                job_name = job['name']
                job_url = job['url']
                builds_url = f"{job_url}api/json?tree=builds[number]"


                # Get the list of all builds for the job
                response = requests.get(builds_url, auth=auth)
                response.raise_for_status()
                builds = response.json()['builds']




                for build in builds:
                    try:
                        build_number = build['number']
                        build_url = f"{job_url}{build_number}/api/json"
                        response = requests.get(build_url, auth=auth)
                        response.raise_for_status()
                        build_info = response.json()
                        pretty_json = json.dumps(build_info, indent=4)
                        print(pretty_json)
                        cause_action = next((action for action in build_info.get('actions', [])), None)
                        cause = cause_action.get('causes', [{}])[0]
                        console_output_url = f"{job_url}{build_number}/consoleText"
                        job_features = {
                            'job_name': job_name,
                            'job_url': build_info.get('url', 'null'),
                            'description': build_info.get('description', 'null'),
                            'duration': format_duration(build_info.get('duration', '0')),
                            'timestamp': format_timestamp(build_info.get('timestamp', '0')),
                            'repo_url': None,
                            'pom_path': None,
                            'groovy_path': None,
                            'error_stage': None,
                            'error_msg': None,
                            'started_by':cause.get('shortDescription', 'null'),
                            'user_id':cause.get('userId', 'null'),
                            'upstream_Project':cause.get('upstreamProject', 'null'),
                            'build_status': build_info.get('result', 'UNKNOWN')
                            }

                        # Download the console output for each build
                        response = requests.get(console_output_url, auth=auth)
                        response.raise_for_status()
                        log_text = sanitize_log_text(response.text)

                        # Save the log to a text file
                        build_log_dir = os.path.join(log_dir, sanitize_for_filesystem(job_name))
                        os.makedirs(build_log_dir, exist_ok=True)
                        log_file_path = os.path.join(build_log_dir, f"build_{build_number}.txt")
                        with open(log_file_path, 'w') as log_file:
                            log_file.write(log_text)

                        # Extract features
                        features = extract_features(log_text)

                        # Update job-level features
                        if not job_features['repo_url'] and features['repo_url']:
                            job_features['repo_url'] = features['repo_url']
                        if not job_features['pom_path'] and features['pom_path']:
                            job_features['pom_path'] = features['pom_path']
                        if not job_features['groovy_path'] and features['groovy_path']:
                            job_features['groovy_path'] = features['groovy_path']
                        if not job_features['error_stage'] and features['error_stage']:
                            job_features['error_stage'] = features['error_stage']
                        if not job_features['error_msg'] and features['error_msg']:
                            job_features['error_msg'] = features['error_msg']

                        print(f"Downloaded log for {job_name} (build {build_number}) in {build_log_dir}")
                        # Add job features to list
                        job_features_list.append(job_features)
                        print(f"Feature: {job_features}")
                    except Exception as err:
                        print(f"Error accessing {job_name} (build {build_number}) in {build_log_dir}: {err}")
                # Save job-level features to CSV
                if job_features_list:
                    feature_df = pd.DataFrame(job_features_list)
                    feature_csv_path = os.path.join(build_log_dir, 'job_features.csv')
                    feature_df.to_csv(feature_csv_path, index=False)
                    print(f"Saved job-level features to {feature_csv_path}")
                    

            except Exception as err:
                print(f"Error accessing job {job_name}: {err}")

       

    except requests.exceptions.RequestException as e:
        print(f"Error accessing {jenkins_url}: {e}")

# List of Jenkins URLs
jenkins_urls = [
    "https://buildbot.iovisor.org/jenkins/",
    "https://ci.inria.fr/pharo-ci-jenkins2/",
    "https://forge.etsi.org/jenkins/",
    "https://merge-ci.openmicroscopy.org/jenkins/",
    "https://jenkins.d4science.org/",
    "https://ci.dv8tion.net/",
    "https://jenkins.osmocom.org/jenkins/",
    "https://ci.eclipse.org/emf/",
    # Add more URLs as needed
]

# Authentication details (if needed)
username = "your-username"
api_token = "your-api-token"
auth = HTTPBasicAuth(username, api_token) if username and api_token else None

# Download logs for each Jenkins URL
for url in jenkins_urls:
    download_job_logs(url)
