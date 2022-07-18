# SSM session helper

This tool helps to connect to an AWS instance using SSM sessions by querying local AWS profiles, regions available for that profile and instances running for that account in the specified region. 

A user friendly interface allows to select the options, and the connection is stablished at the end of the process.

## Requirements

This is a python script that uses PyInquirer to render the prompts, Boto3 to query AWS and configparser to parse the credentials stored locally. In addition, the [AWS CLI](https://aws.amazon.com/cli/) along with the [SSM plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html) must be installed to execute the SSM session.

Credentials must be stored in `~/.aws/credentials`.

## Install

1. Download binary from release
2. Move binary to a folder in your `$PATH`
3. Enjoy

## Run in development

```bash
git clone https://github.com/MaximilianoAguirre/py-aws-ssm-session

pip install -r py-aws-ssm-session/requirements.txt
python py-aws-ssm-session/ssm.py
```

## Build

```bash
git clone https://github.com/MaximilianoAguirre/py-aws-ssm-session

pip install -r py-aws-ssm-session/requirements.txt
pyinstaller -F ssm-session.py
```
