from __future__ import print_function

import boto3

print('Loading function')

# -*- coding: utf-8 -*-

# Copyright 2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# SPDX-License-Identifier: LicenseRef-.amazon.com.-AmznSL-1.0
# Licensed under the Amazon Software License (the "License")
# You may not use this file except in
# compliance with the License. A copy of the License is located at http://aws.amazon.com/asl/
#
# This file is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or implied. See the License for the specific
# language governing permissions and limitations under the License.


DEVICE_NAME = 'Test Light'


import json
import math
import random
import uuid
import logging
import datetime
from datetime import datetime, timezone

from decimal import Decimal

from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def lambda_handler(request, context):

    # Dump the request for logging - check the CloudWatch logs.
    print('lambda_handler request  -----')
    print(json.dumps(request))


    if context is not None:
        print('lambda_handler context  -----')
        print(context)

    # Validate the request is an Alexa smart home directive.
    if 'directive' not in request:
        alexa_response = AlexaResponse(
            name='ErrorResponse',
            payload={'type': 'INVALID_DIRECTIVE',
                     'message': 'Missing key: directive, Is the request a valid Alexa Directive?'})
        return send_response(alexa_response.get())

    # Check the payload version.
    payload_version = request['directive']['header']['payloadVersion']
    if payload_version != '3':
        alexa_response = AlexaResponse(
            name='ErrorResponse',
            payload={'type': 'INTERNAL_ERROR',
                     'message': 'This skill only supports Smart Home API version 3'})
        return send_response(alexa_response.get())

    # Crack open the request to see the request.
    name = request['directive']['header']['name']
    namespace = request['directive']['header']['namespace']

    # Handle the incoming request from Alexa based on the namespace.
    if namespace == 'Alexa.Authorization':
        if name == 'AcceptGrant':
            # Note: This example code accepts any grant request.
            # In your implementation, invoke Login With Amazon with the grant code to get access and refresh tokens.
            grant_code = request['directive']['payload']['grant']['code']
            grantee_token = request['directive']['payload']['grantee']['token']
            auth_response = AlexaResponse(namespace='Alexa.Authorization', name='AcceptGrant.Response')
            return send_response(auth_response.get())

    if namespace == 'Alexa.Discovery':
        if name == 'Discover':
            # The request to discover the devices the skill controls.
            discovery_response = AlexaResponse(namespace='Alexa.Discovery', name='Discover.Response')
            # Create the response and add the light bulb capabilities.
            capability_alexa = discovery_response.create_payload_endpoint_capability()
            capability_alexa_powercontroller = discovery_response.create_payload_endpoint_capability(
                interface='Alexa.PowerController',
                supported=[{'name': 'powerState'}])
            capability_alexa_brightnesscontroller = discovery_response.create_payload_endpoint_capability(
                interface='Alexa.BrightnessController',
                supported=[{'name': 'brightness'}])
            capability_alexa_endpointhealth = discovery_response.create_payload_endpoint_capability(
                interface='Alexa.EndpointHealth',
                supported=[{'name': 'connectivity'}])
            discovery_response.add_payload_endpoint(
                friendly_name=DEVICE_NAME,
                endpoint_id='sample-bulb-01',
                capabilities=[capability_alexa, capability_alexa_endpointhealth, capability_alexa_powercontroller, capability_alexa_brightnesscontroller])
            return send_response(discovery_response.get())

    if namespace == 'Alexa.PowerController':
        # The directive to TurnOff or TurnOn the light bulb.
        # Note: This example code always returns a success response.
        endpoint_id = request['directive']['endpoint']['endpointId']

# modif STKofuji
        power_state_value = 0 if name == 'TurnOff' else 1
        correlation_token = request['directive']['header']['correlationToken']

        # Check for an error when setting the state.
        device_set = update_device_state(endpoint_id=endpoint_id, state='powerState', value=power_state_value)
        if not device_set:
            return AlexaResponse(
                name='ErrorResponse',
                payload={'type': 'ENDPOINT_UNREACHABLE', 'message': 'Unable to reach endpoint database.'}).get()

        directive_response = AlexaResponse(correlation_token=correlation_token)
        directive_response.add_context_property(namespace='Alexa.PowerController', name='powerState', value=power_state_value)
        return send_response(directive_response.get())

    if namespace == 'Alexa':
        if name == "ReportState":
            endpoint_id = request['directive']['endpoint']['endpointId']

            correlation_token = request['directive']['header']['correlationToken']

            dynamodb = boto3.resource('dynamodb',region_name='us-east-1')
            table = dynamodb.Table('IoTCatalog')
            response_db = table.query (
                KeyConditionExpression=Key("serialNumber").eq("SN-D7F3C8947867"),
                ScanIndexForward=False,
                Limit=1
                )
            print(response_db['Items'][0])
            item = response_db['Items'][0]
            luminosity = item['payload']['luminosity']
            print("STK", luminosity)

            # directive_response = AlexaResponse(correlation_token=correlation_token)
            # directive_response.add_context_property(namespace='Alexa.BrightnessController', name='brightness', value=luminosity)
            
            response = {
                "context": 
                    {
                        "properties": 	
                            [
                                {
                                    "namespace": "Alexa.BrightnessController",
                                    "name": "brightness",
                                    "value": str(luminosity),
                                    "timeOfSample": get_utc_timestamp(),
                                    "uncertaintyInMilliseconds": 500
                                }
                            ]
                    },
                "event": 
                    {
                        "header": 
                            {
                                "namespace": "Alexa",
                                "name": "StateReport",
                                "payloadVersion": "3",
                                "messageId": str(uuid.uuid4()),
                                "correlationToken": request["directive"]["header"]["correlationToken"]
                            },
                        "endpoint": 
                            {
                                "scope": 
                                    {
                                        "type": "BearerToken",
                                        "token": "access-token-from-Amazon"
                                    },
                                "endpointId": request["directive"]["endpoint"]["endpointId"]
                            },
                        "payload": {}
                    }
            }
            
            return send_response(response)


# Send the response
def send_response(response):
    print('lambda_handler response -----')
    print(json.dumps(response))
    return response

# Make the call to your device cloud for control
def update_device_state(endpoint_id, state, value):
    attribute_key = state + 'Value'

# Modifications by STKofuji 29/April/2024
    client = boto3.client('iot-data', region_name='us-east-1');
    data = {"state" : { "desired" : { "power" : value }}}

    response = client.publish(
        topic='$aws/things/my-esp32/shadow/update',
        qos=1,
        payload=json.dumps(data)
        )
# END Modifications by STK 29/April/2024

    # result = stubControlFunctionToYourCloud(endpointId, token, request);
    return True


# Datetime format for timeOfSample is ISO 8601, `YYYY-MM-DDThh:mm:ssZ`.
def get_utc_timestamp(seconds=None):
    return datetime.now(timezone.utc).isoformat()

class AlexaResponse:

    def __init__(self, **kwargs):

        self.context_properties = []
        self.payload_endpoints = []

        # Set up the response structure.
        self.context = {}
        self.event = {
            'header': {
                'namespace': kwargs.get('namespace', 'Alexa'),
                'name': kwargs.get('name', 'Response'),
                'messageId': str(uuid.uuid4()),
                'payloadVersion': kwargs.get('payload_version', '3')
            },
            'endpoint': {
                "scope": {
                    "type": "BearerToken",
                    "token": kwargs.get('token', 'INVALID')
                },
                "endpointId": kwargs.get('endpoint_id', 'INVALID')
            },
            'payload': kwargs.get('payload', {})
        }

        if 'correlation_token' in kwargs:
            self.event['header']['correlation_token'] = kwargs.get('correlation_token', 'INVALID')

        if 'cookie' in kwargs:
            self.event['endpoint']['cookie'] = kwargs.get('cookie', '{}')

        # No endpoint property in an AcceptGrant or Discover request.
        if self.event['header']['name'] == 'AcceptGrant.Response' or self.event['header']['name'] == 'Discover.Response':
            self.event.pop('endpoint')

    def add_context_property(self, **kwargs):
        self.context_properties.append(self.create_context_property(**kwargs))
        self.context_properties.append(self.create_context_property())


    def add_cookie(self, key, value):

        if "cookies" in self is None:
            self.cookies = {}

        self.cookies[key] = value

    def add_payload_endpoint(self, **kwargs):
        self.payload_endpoints.append(self.create_payload_endpoint(**kwargs))


    def create_context_property(self, **kwargs):
        return {
            'namespace': kwargs.get('namespace', 'Alexa.EndpointHealth'),
            'name': kwargs.get('name', 'connectivity'),
            'value': kwargs.get('value', {'value': 'OK'}),
            'timeOfSample': get_utc_timestamp(),
            'uncertaintyInMilliseconds': kwargs.get('uncertainty_in_milliseconds', 0)
        }

    def create_payload_endpoint(self, **kwargs):
        # Return the proper structure expected for the endpoint.
        # All discovery responses must include the additionAttributes
        additionalAttributes = {
            'manufacturer': kwargs.get('manufacturer', 'Oliver e Maria'),
            'model': kwargs.get('model_name', 'Sample Model'),
            'serialNumber': kwargs.get('serial_number', 'U11112233456'),
            'firmwareVersion': kwargs.get('firmware_version', '1.24.2546'),
            'softwareVersion': kwargs.get('software_version', '1.036'),
            'customIdentifier': kwargs.get('custom_identifier', 'Sample custom ID')
        }

        endpoint = {
            'capabilities': kwargs.get('capabilities', []),
            'description': kwargs.get('description', 'Smart Light for PSI3541'),
            'displayCategories': kwargs.get('display_categories', ['LIGHT']),
            'endpointId': kwargs.get('endpoint_id', 'endpoint_' + "%0.6d" % random.randint(0, 999999)),
            'friendlyName': kwargs.get('friendly_name', 'Smart Light'),
            'manufacturerName': kwargs.get('manufacturer_name', 'Oliver e Maria')
        }

        endpoint['additionalAttributes'] = kwargs.get('additionalAttributes', additionalAttributes)
        if 'cookie' in kwargs:
            endpoint['cookie'] = kwargs.get('cookie', {})

        return endpoint

    def create_payload_endpoint_capability(self, **kwargs):
        # All discovery responses must include the Alexa interface
        capability = {
            'type': kwargs.get('type', 'AlexaInterface'),
            'interface': kwargs.get('interface', 'Alexa'),
            'version': kwargs.get('version', '3')
        }
        supported = kwargs.get('supported', None)
        if supported:
            capability['properties'] = {}
            capability['properties']['supported'] = supported
            capability['properties']['proactivelyReported'] = kwargs.get('proactively_reported', True)
            capability['properties']['retrievable'] = kwargs.get('retrievable', True)
        return capability

    def get(self, remove_empty=True):

        response = {
            'context': self.context,
            'event': self.event
        }

        if len(self.context_properties) > 0:
            response['context']['properties'] = self.context_properties

        if len(self.payload_endpoints) > 0:
            response['event']['payload']['endpoints'] = self.payload_endpoints

        if remove_empty:
            if len(response['context']) < 1:
                response.pop('context')

        return response

    def set_payload(self, payload):
        self.event['payload'] = payload

    def set_payload_endpoint(self, payload_endpoints):
        self.payload_endpoints = payload_endpoints

    def set_payload_endpoints(self, payload_endpoints):
        if 'endpoints' not in self.event['payload']:
            self.event['payload']['endpoints'] = []

        self.event['payload']['endpoints'] = payload_endpoints