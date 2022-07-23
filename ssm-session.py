from argparse import ArgumentParser
from boto3 import Session
from botocore import exceptions
from configparser import ConfigParser
from os import path, system, environ
from PyInquirer import prompt
from sys import exit

VERSION = "1.4"

# Parse arguments and environment variables
parser = ArgumentParser()

parser.add_argument("-v", "--version", help="show version", action="store_true")
parser.add_argument(
    "-p", "--profile", help="set profile", default=environ.get("AWS_PROFILE")
)
parser.add_argument(
    "-r", "--region", help="set region", default=environ.get("AWS_DEFAULT_REGION")
)
parser.add_argument(
    "-c",
    "--credentials-file",
    help="set credentials file path",
    default=environ.get("AWS_SHARED_CREDENTIALS_FILE", "~/.aws/credentials"),
)
parser.add_argument(
    "-aki",
    "--access-key-id",
    help="set AWS access key ID",
    default=environ.get("AWS_ACCESS_KEY_ID"),
)
parser.add_argument(
    "-sak",
    "--secret-access-key",
    help="set AWS secret access key",
    default=environ.get("AWS_SECRET_ACCESS_KEY"),
)
parser.add_argument(
    "-st",
    "--session-token",
    help="set AWS session token",
    default=environ.get("AWS_SESSION_TOKEN"),
)

args = parser.parse_args()

PROMPT_OPTIONS = {"keyboard_interrupt_msg": "Cancelled"}

session = None
answers = {}
ec2_client = None
ssm_client = None

###########################################################
### HANDLE VERSION REQUEST
###########################################################
if args.version:
    print(f"ssm-session v{VERSION}")
    exit(0)

###########################################################
### CREATE BOTO3 SESSION
### CHECK FOR CREDENTIALS SET IN ENV VARS OR USE A PROFILE
###########################################################

# Check if credentials are set in the environment
if args.access_key_id and args.secret_access_key:
    print("INFO: Using credentials from environment")

    session = Session(
        aws_access_key_id=args.access_key_id,
        aws_secret_access_key=args.secret_access_key,
        aws_session_token=args.session_token,
    )

# Use profile
else:

    # Check of there is a profile set in the env vars
    if args.profile:
        print(f"INFO: Using profile: {args.profile}")
        answers = {"profile": args.profile}

    # Ask for profile
    else:

        # Read credentials file
        credentials = ConfigParser()
        credentials.read(path.expanduser(args.credentials_file))

        # Error if no profile file found
        if not len(credentials.sections()):
            print(
                f"ERROR: Profile file not found or empty: {path.expanduser(args.credentials_file)}"
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


if not args.region:

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
    print(f"INFO: Using region: {args.region}")

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
