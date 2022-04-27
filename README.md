# SSM session helper

This tool helps to connect to an AWS instance using SSM sessions by querying local AWS profiles, regions available for that profile and instances running for that account in the specified region. 

A user friendly interface allows to select the options, and the connection is stablished at the end of the process.

## Requirements

This is a python script that uses PyInquirer to render the prompts, Boto3 to query AWS and configparser to parse the credentials stored locally. In addition, the AWS CLI along with the SSM plugin must be installed to execute the SSM session.

Credentials must be stored in ~/.aws/credentials (you can modify this parameter inside the script).

## Usage

```bash
git clone https://github.com/MaximilianoAguirre/py-aws-ssm-session

pip install -r py-aws-ssm-session/requirements.txt
python py-aws-ssm-session/ssm.py
```

### Set alias

Replace `~/py-aws-ssm-session/ssm.py` with the path to the script

```bash
echo "alias ssm-session='python ~/py-aws-ssm-session/ssm.py'" >> ~/.bashrc

ssm-session
```
