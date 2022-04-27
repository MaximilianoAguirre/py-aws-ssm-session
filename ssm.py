from PyInquirer import prompt
from os import path, system
from botocore import exceptions

import configparser
import boto3

# DEFAULTS
CREDENTIALS_FILE = "~/.aws/credentials"
CONFIG_FILE = "~/.aws/config"
PROMPT_OPTIONS = {"keyboard_interrupt_msg": "Cancelled"}

# READ CREDENTIALS FILE
credentials = configparser.ConfigParser()
credentials.read(path.expanduser(CREDENTIALS_FILE))

# READ CONFIG FILE
config = configparser.ConfigParser()
config.read(path.expanduser(CONFIG_FILE))

# PROMPT FOR PROFILE
question_profile = {
    "type": "list",
    "name": "profile",
    "message": "Select profile",
    "choices": credentials.sections(),
}


answers = prompt(question_profile, **PROMPT_OPTIONS)

if not answers:
    exit()

# QUERY REGION AVAILABLES FOR THE ACCOUNT
# VALIDATE CREDENTIALS
try:
    session = boto3.Session(profile_name=answers["profile"])
    regionless_ec2_client = session.client("ec2", region_name="us-east-1")

    regions = [
        region["RegionName"]
        for region in regionless_ec2_client.describe_regions()["Regions"]
    ]
except exceptions.ClientError as error:
    if error.response["Error"]["Code"] == "AuthFailure":
        print("Invalid credentials")
        exit()
    raise error


# PROMPT FOR REGION
question_region = {
    "type": "list",
    "name": "region",
    "message": "Select region",
    "choices": regions,
}

# # CHECK FOR DEFAULT REGION SET
# # Uncomment when default supported in PyInquirer lists
# if f"profile {answers['profile']}" in config:
#     if "region" in config[f"profile {answers['profile']}"]:
#         question_region["default"] = config[f"profile {answers['profile']}"]["region"]


answers = prompt(question_region, answers, **PROMPT_OPTIONS)

if not answers:
    exit()

# QUERY EC2 & SSM INSTANCES
ec2_client = session.client("ec2", region_name=answers["region"])
ssm_client = session.client("ssm", region_name=answers["region"])


instances_running = ec2_client.describe_instances(
    Filters=[
        {
            "Name": "instance-state-name",
            "Values": [
                "running",
            ],
        },
    ],
)

instances_managed_by_ssm = [
    i["InstanceId"]
    for i in ssm_client.describe_instance_information()["InstanceInformationList"]
]


# PARSE INSTANCE NAME, VALUE & AVAILABILITY
def parse_instance_choice(instance):
    instanceDetails = instance["Instances"][0]
    instanceId = instanceDetails["InstanceId"]
    instanceName = list(
        filter(lambda tag: tag["Key"] == "Name", instanceDetails["Tags"])
    )
    instanceName = f" - {instanceName[0]['Value']}" if instanceName else ""

    response = {"name": f"{instanceId}{instanceName}", "value": instanceId}

    if instanceId not in instances_managed_by_ssm:
        response["disabled"] = "SSM not connected"

    return response


instances = [
    parse_instance_choice(instance) for instance in instances_running["Reservations"]
]

if not instances:
    print("No instances running. Start your instance and try again.")
    exit()

# PROMPT FOR INSTANCE
questions = [
    {
        "type": "list",
        "name": "instanceId",
        "message": "Select instance",
        "choices": instances,
    },
]

answers = prompt(questions, answers, **PROMPT_OPTIONS)

if not answers:
    exit()

# RUN SSM SESSION
system(
    "aws ssm start-session --target {instanceId} --profile {profile} --region {region}".format(
        **answers
    )
)
