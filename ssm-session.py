from boto3 import Session
from botocore import exceptions
from configparser import ConfigParser
from os import path, system, environ
from PyInquirer import prompt
from sys import exit

# READ ENV VARS
AWS_CREDENTIALS_FILE = environ.get("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials")
AWS_REGION = environ.get("AWS_DEFAULT_REGION")
AWS_PROFILE = environ.get("AWS_PROFILE")
AWS_ACCESS_KEY_ID = environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = environ.get("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = environ.get("AWS_SESSION_TOKEN")

PROMPT_OPTIONS = {"keyboard_interrupt_msg": "Cancelled"}

session = None
answers = {}
ec2_client = None
ssm_client = None

###########################################################
### CREATE BOTO3 SESSION
### CHECK FOR CREDENTIALS SET IN ENV VARS OR USE A PROFILE
###########################################################

# Check if credentials are set in the environment
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    print("INFO: Using credentials from environment vars")

    session = Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        aws_session_token=AWS_SESSION_TOKEN,
    )

# Use profile
else:

    # Check of there is a profile set in the env vars
    if AWS_PROFILE:
        print(f"INFO: Using profile set by AWS_PROFILE: {AWS_PROFILE}")
        answers = {"profile": AWS_PROFILE}

    # Ask for profile
    else:

        # Read credentials file
        credentials = ConfigParser()
        credentials.read(path.expanduser(AWS_CREDENTIALS_FILE))

        # Error if no profile file found
        if not len(credentials.sections()):
            print(
                f"ERROR: Profile file not found or empty: {path.expanduser(AWS_CREDENTIALS_FILE)}"
            )
            exit(1)

        # Prompt for profile
        question_profile = {
            "type": "list",
            "name": "profile",
            "message": "Select profile",
            "choices": credentials.sections(),
        }
        answers = prompt(question_profile, **PROMPT_OPTIONS)

        # Check for prompt cancelled
        if not answers:
            exit(1)

    session = Session(profile_name=answers["profile"])


###########################################################
### SELECT REGION TO USE AND INITIALIZE BOTO3 CLIENTS
### CHECK FOR REGION SET IN ENV VARS OR PROMPT FOR IT
###########################################################


if not AWS_REGION:

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
            print("ERROR: Invalid/expired credentials or profile")
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

    # Check for cancelled prompt
    if not answers:
        exit(1)

    ec2_client = session.client("ec2", region_name=answers["region"])
    ssm_client = session.client("ssm", region_name=answers["region"])

else:
    print(f"INFO: Using region set by environment vars: {AWS_REGION}")

    ec2_client = session.client("ec2")
    ssm_client = session.client("ssm")


###########################################################
### QUERY INSTANCES AND STATE
### PROMPT FOR INSTANCE TO CONNECT TO
###########################################################

# Describe instances running
try:
    instances_running = ec2_client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )
except exceptions.ClientError as error:
    if error.response["Error"]["Code"] == "AuthFailure":
        print("ERROR: Invalid/expired credentials or profile")
        exit(1)
    raise error

# Describe instances registered in SSM
instances_managed_by_ssm = [
    i["InstanceId"]
    for i in ssm_client.describe_instance_information()["InstanceInformationList"]
]


# Parse instance name, id and availability into prompt choice
def parse_instance_choice(instance):
    response = {}

    instanceDetails = instance["Instances"][0]
    instanceId = instanceDetails.get("InstanceId")
    instanceName = list(
        filter(lambda tag: tag["Key"] == "Name", instanceDetails.get("Tags", []))
    )
    instanceName = f" | {instanceName[0]['Value']}" if instanceName else ""

    if instanceId not in instances_managed_by_ssm:
        response["disabled"] = "SSM not connected"
    else:
        instanceName = f"  {instanceName}"

    response["name"] = f"{instanceId}{instanceName}"
    response["value"] = instanceId

    return response


instances = [
    parse_instance_choice(instance) for instance in instances_running["Reservations"]
]

enabled_instances = [instance for instance in instances if "disabled" not in instance]

# Check if there are available options
if not instances:
    print("ERROR: No instances running. Start your instance and try again.")
    exit(1)

if not enabled_instances:
    print("ERROR: No instances connected to SSM. Check SSM prerequisites.")
    exit(1)

# Prompt for instance to connect to
questions = [
    {
        "type": "list",
        "name": "instanceId",
        "message": "Select instance",
        "choices": instances,
    }
]

answers = prompt(questions, answers, **PROMPT_OPTIONS)

# Check for cancelled prompt
if not answers:
    exit(1)


###########################################################
### PARSE COMMAND AND EXECUTE IT
###########################################################

command = f"aws ssm start-session --target {answers['instanceId']}"

if "profile" in answers:
    command += f" --profile {answers['profile']}"

if "region" in answers:
    command += f" --region {answers['region']}"


# Run SSM session
system(command)
