import json
import os
import slack
import requests
import base64
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import hashlib
import hmac
from time import time

def verify_slack_signature(slack_post_request, slack_signing_secret, body):
    slack_signing_secret = bytes(slack_signing_secret, 'utf-8')
    slack_signature = slack_post_request['headers']['x-slack-signature']
    slack_request_timestamp = slack_post_request['headers']['x-slack-request-timestamp']
    basestring = f"v0:{slack_request_timestamp}:{body}".encode('utf-8')
    my_signature = 'v0=' + hmac.new(slack_signing_secret, basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(my_signature, slack_signature)

def lambda_handler(event, context):
    
    query_string = str(base64.b64decode(event['body']), encoding='utf-8')
    dict = urllib.parse.parse_qs(query_string)

    # Protect against replay attacks
    if int(time()) - int(event['headers']['x-slack-request-timestamp']) > 60 * 5:
        return {
            "statusCode": 401,
            "statusDescription": "401 Unauthorized",
            "isBase64Encoded": False,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": ""
        }
    
    # Verify the request is coming from Slack
    slack_signing_secret = os.environ['slack_signing_secret']
    if verify_slack_signature(event, slack_signing_secret, query_string):
        print('signature verified')
    else:
        return {
            "statusCode": 401,
            "statusDescription": "401 Unauthorized",
            "isBase64Encoded": False,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": ""
        }
    
    # Update installation configuration
    dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
    table = dynamodb.Table('LichessSlackAppInstallations')
    keys = {
        'team_id': dict['team_id'][0],
        'channel_id': dict['channel_id'][0]
    }
    expression_attribute_values = {
        ':p': dict['text'][0],
        ':l': "2008-01-01 00:00:00",
        ':team_id': dict['team_id'][0],
        ':channel_id': dict['channel_id'][0]      
    }
    try:
        response = table.update_item(
            Key = keys,
            ConditionExpression = 'team_id = :team_id and channel_id = :channel_id',
            UpdateExpression = "set preferred_time = :p, last_executed = :l",
            ExpressionAttributeValues = expression_attribute_values,
            ReturnValues = "UPDATED_NEW"
        )
        slack_response = {
           "response_type": "in_channel",
           "text": "The daily puzzle will be posted daily at " + dict['text'][0] + " UTC"
        }
    except ClientError as e:
        if e.response['Error']['Code'] == "ConditionalCheckFailedException":
            slack_response = {
               "response_type": "in_channel",
               "text": "This app is not installed in this channel.",
               "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "This app is not installed in this channel. <https://lichess-slack-app.org/lambda/lichess-slack-app-direct-install|Click here to install.>"
                        }
                    }
                ]
            }

    return {
        "statusCode": 200,
        "statusDescription": "200 OK",
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(slack_response)
    }