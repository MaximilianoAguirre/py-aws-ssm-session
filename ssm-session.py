import logging

from argparse import ArgumentParser
from boto3 import Session
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.config import Config
from configparser import ConfigParser
from os import path, system, environ
from PyInquirer import prompt
from shutil import which
from sys import exit

from region_names import region_names

VERSION = "v1.5"
PROMPT_OPTIONS = {"keyboard_interrupt_msg": "Cancelled"}
botocore_config = config = Config(retries={"max_attempts": 2, "mode": "standard"})

# Global try to catch EOF
try:

    ###########################################################
    ### PARSE ARGUMENTS AND ENVIRONMENT VARIABLES
    ###########################################################
    parser = ArgumentParser()

    parser.add_argument(
        "--version",
        help="show version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    parser.add_argument(
        "-p", "--profile", help="set profile", default=environ.get("AWS_PROFILE")
    )
    parser.add_argument(
        "-d",
        "--debug",
        help="Set logging to debug, default: warning",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="Set logging to info",
        action="store_const",
        dest="loglevel",
        const=logging.INFO,
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
        "--access-key-id",
        help="set AWS access key ID",
        default=environ.get("AWS_ACCESS_KEY_ID"),
    )
    parser.add_argument(
        "--secret-access-key",
        help="set AWS secret access key",
        default=environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    parser.add_argument(
        "--session-token",
        help="set AWS session token",
        default=environ.get("AWS_SESSION_TOKEN"),
    )

    args = parser.parse_args()

    ###########################################################
    ### SET LOGGING CONFIGURATION
    ###########################################################
    logging.basicConfig(format="%(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    logger.setLevel(args.loglevel)

    ###########################################################
    ### CHECK REQUISITES
    ### AWS CLI AND SSM PLUGIN
    ###########################################################
    logger.debug("Checking for AWS CLI installed")
    if not which("aws"):
        logger.error("AWS CLI can not be found in environment, install it to continue")
        exit(1)
    logger.debug("AWS CLI found")

    # https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html#install-plugin-verify
    logger.debug("Checking for AWS SSM plugin installed")
    if not which("session-manager-plugin"):
        logger.error("AWS SSM Plugin not found in environment, install it to continue")
        exit(1)
    logger.debug("AWS SSM Plugin found")

    ###########################################################
    ### INIT VARS
    ###########################################################
    session = None
    answers = {}
    ec2_client = None
    ssm_client = None

    ###########################################################
    ### CREATE BOTO3 SESSION
    ### CHECK FOR CREDENTIALS SET IN ENV VARS OR USE A PROFILE
    ###########################################################
    logger.debug("Looking for credentials in environment vars or arguments")
    if args.access_key_id and args.secret_access_key:

        logger.info("Creating session using credentials from env vars or arguments")
        session = Session(
            aws_access_key_id=args.access_key_id,
            aws_secret_access_key=args.secret_access_key,
            aws_session_token=args.session_token,
        )

    else:
        logger.debug("Credentials not found in env vars neither set in arguments")
        logger.debug("Looking for profile set in env vars or arguments")

        if args.profile:
            logger.info(f"Using profile: {args.profile}")
            answers = {"profile": args.profile}

        else:
            logger.debug("Profile not set in env vars or arguments")
            logger.debug(f"Reading credentials file in: {args.credentials_file}")

            credentials = ConfigParser()
            credentials.read(path.expanduser(args.credentials_file))

            # Error if no profile file found
            if not len(credentials.sections()):
                logger.error(
                    f"Profile file not found or empty: {path.expanduser(args.credentials_file)}"
                )
                exit(1)

            logger.debug("Credentials file found and read correctly")
            logger.debug("Prompting to select a profile")

            answers = prompt(
                {
                    "type": "list",
                    "name": "profile",
                    "message": "Select profile",
                    "choices": credentials.sections(),
                },
                **PROMPT_OPTIONS,
            )

            if not answers:
                logger.debug("User cancelled selection, exiting...")
                exit(1)

            logger.debug(f"Selected profile: {answers['profile']}")

        logger.debug(f"Creating session with profile: {answers['profile']}")
        session = Session(profile_name=answers["profile"])

    ###########################################################
    ### SELECT REGION TO USE AND INITIALIZE BOTO3 CLIENTS
    ### CHECK FOR REGION SET IN ENV VARS OR PROMPT FOR IT
    ###########################################################
    logger.debug("Looking for region set in env vars or arguments")
    if not args.region:

        logger.debug("Query available regions for the specified session")
        try:
            regionless_ec2_client = session.client("ec2", region_name="us-east-1")

            regions = [
                region["RegionName"]
                for region in regionless_ec2_client.describe_regions()["Regions"]
            ]
        except ClientError as error:
            if error.response["Error"]["Code"] == "AuthFailure":
                logger.error("Invalid/expired credentials or profile")
                exit(1)
            raise error

        def parse_region(region):
            return {"name": f"{region} - {region_names[region]}", "value": region}

        logger.debug("Prompting to select a region")
        answers = prompt(
            {
                "type": "list",
                "name": "region",
                "message": "Select region",
                "choices": list(map(parse_region, regions)),
            },
            answers,
            **PROMPT_OPTIONS,
        )

        if not answers:
            logger.debug("User cancelled selection, exiting...")
            exit(1)

        logger.debug(f"Selected region: {answers['region']}")
        logger.debug("Creating boto3 clients with selected region")

        ec2_client = session.client(
            "ec2", region_name=answers["region"], config=botocore_config
        )
        ssm_client = session.client(
            "ssm", region_name=answers["region"], config=botocore_config
        )

    else:
        logger.debug("Creating boto3 clients with environment region")
        logger.info(f"Using region: {args.region}")

        logger.debug("Checking region availability")
        if args.region not in session.get_available_regions("ec2"):
            logger.error(f"Region not available: {args.region}")
            exit(1)

        ec2_client = session.client(
            "ec2", region_name=args.region, config=botocore_config
        )
        ssm_client = session.client(
            "ssm", region_name=args.region, config=botocore_config
        )

    ###########################################################
    ### QUERY INSTANCES AND STATE
    ### PROMPT FOR INSTANCE TO CONNECT TO
    ###########################################################
    logger.debug("Querying instances with state running")
    try:
        instances_running = ec2_client.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "AuthFailure":
            logger.error("Invalid/expired credentials or profile")
            exit(1)
        raise error

    logger.debug("Querying instances connected to SSM")
    instances_managed_by_ssm = [
        i["InstanceId"]
        for i in ssm_client.describe_instance_information()["InstanceInformationList"]
    ]

    def parse_instance_choice(instance):
        """Parse option for instance prompt
        Args:
            instance (dict)
        Returns:
            dict: option dict usable with list prompt
        """
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

    logger.debug("Parse instances information")
    instances = [
        parse_instance_choice(instance)
        for instance in instances_running["Reservations"]
    ]

    logger.debug("Check if there are instances running and connected to SSM")
    enabled_instances = [
        instance for instance in instances if "disabled" not in instance
    ]

    if not instances:
        logger.error("No instances running. Start your instance and try again.")
        exit(1)

    if not enabled_instances:
        logger.error("No instances connected to SSM. Check SSM prerequisites.")
        exit(1)

    logger.debug("Prompting to select an instance")
    answers = prompt(
        [
            {
                "type": "list",
                "name": "instanceId",
                "message": "Select instance",
                "choices": instances,
            }
        ],
        answers,
        **PROMPT_OPTIONS,
    )

    if not answers:
        logger.debug("User cancelled selection, exiting...")
        exit(1)

    logger.debug(f"Selected instance with id: {answers['instanceId']}")

    ###########################################################
    ### PARSE COMMAND AND EXECUTE IT
    ###########################################################
    command = f"aws ssm start-session --target {answers['instanceId']}"

    if "profile" in answers:
        command += f" --profile {answers['profile']}"

    if "region" in answers:
        command += f" --region {answers['region']}"

    # Run SSM session
    logger.debug(f"Running command: {command}")
    system(command)

except EOFError:
    logger.debug("Finished with EOF")
    print("")
    print("Cancelled")
    print("")

except EndpointConnectionError:
    logger.error("Error connecting to AWS endpoints")
    exit(1)
