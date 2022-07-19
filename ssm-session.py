import boto3

from PyInquirer import prompt
from os import path, system, environ
from botocore import exceptions
from sys import exit
from configparser import ConfigParser

# CONFIGURATIONS
CREDENTIALS_FILE = environ.get("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials")
REGION = environ.get("AWS_REGION", environ.get("AWS_DEFAULT_REGION"))
PROFILE = environ.get("AWS_PROFILE")

PROMPT_OPTIONS = {"keyboard_interrupt_msg": "Cancelled"}

if not PROFILE:

    # READ CREDENTIALS FILE
    credentials = ConfigParser()
    credentials.read(path.expanduser(CREDENTIALS_FILE))

    # ERROR IF NO PROFILE FILE FOUND
    if not len(credentials.sections()):
        print(f"Profile file not found or empty: {path.expanduser(CREDENTIALS_FILE)}")
        exit(1)

    # PROMPT FOR PROFILE
    question_profile = {
        "type": "list",
        "name": "profile",
        "message": "Select profile",
        "choices": credentials.sections(),
    }

    answers = prompt(question_profile, **PROMPT_OPTIONS)

else:
    print(f"Using profile set by AWS_PROFILE: {PROFILE}")

    answers = {"profile": PROFILE}

if not answers:
    exit(1)

session = boto3.Session(profile_name=answers["profile"])

if not REGION:

    # QUERY REGION AVAILABLES FOR THE ACCOUNT
    # VALIDATE CREDENTIALS
    try:
        regionless_ec2_client = session.client("ec2", region_name="us-east-1")

        regions = [
            region["RegionName"]
            for region in regionless_ec2_client.describe_regions()["Regions"]
        ]
    except exceptions.ClientError as error:
        if error.response["Error"]["Code"] == "AuthFailure":
            print("Invalid credentials or profile")
            exit(1)
        raise error

    # PROMPT FOR REGION
    question_region = {
        "type": "list",
        "name": "region",
        "message": "Select region",
        "choices": regions,
    }

    answers = prompt(question_region, answers, **PROMPT_OPTIONS)

else:
    print(f"Using region set by environment vars: {REGION}")

    answers["region"] = REGION

if not answers:
    exit(1)

# QUERY EC2 & SSM INSTANCES
ec2_client = session.client("ec2", region_name=answers["region"])
ssm_client = session.client("ssm", region_name=answers["region"])


instances_running = ec2_client.describe_instances(
    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
)

instances_managed_by_ssm = [
    i["InstanceId"]
    for i in ssm_client.describe_instance_information()["InstanceInformationList"]
]


# PARSE INSTANCE NAME, VALUE & AVAILABILITY
def parse_instance_choice(instance):
    instanceDetails = instance["Instances"][0]
    instanceId = instanceDetails.get("InstanceId")
    instanceName = list(
        filter(lambda tag: tag["Key"] == "Name", instanceDetails.get("Tags", []))
    )
    instanceName = f" - {instanceName[0]['Value']}" if instanceName else ""

    response = {"name": f"{instanceId}{instanceName}", "value": instanceId}

    if instanceId not in instances_managed_by_ssm:
        response["disabled"] = "SSM not connected"

    return response


instances = [
    parse_instance_choice(instance) for instance in instances_running["Reservations"]
]

enabled_instances = [instance for instance in instances if "disabled" not in instance]

if not instances:
    print("No instances running. Start your instance and try again.")
    exit(1)

if not enabled_instances:
    print("No instances connected to SSM. Check SSM prerequisites.")
    exit(1)

# PROMPT FOR INSTANCE
questions = [
    {
        "type": "list",
        "name": "instanceId",
        "message": "Select instance",
        "choices": instances,
    }
]

answers = prompt(questions, answers, **PROMPT_OPTIONS)

if not answers:
    exit(1)

# RUN SSM SESSION
system(
    "aws ssm start-session --target {instanceId} --profile {profile} --region {region}".format(
        **answers
    )
)
