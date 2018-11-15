# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import argparse

import yaml
from bravado_core.spec import Spec


CLIENT_HEADER = '''# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import logging

from bravado.client import SwaggerClient
from bravado.client import construct_request
from bravado.config import RequestConfig
from bravado.http_client import HttpClient
from bravado.http_future import HttpFuture
from bravado.response import BravadoResponseMetadata
from bravado.warning import warn_for_deprecated_op


log = logging.getLogger(__name__)


class {service_name}Client(SwaggerClient):
'''


def add_parser(subparsers, parents=[]):
    parser = subparsers.add_parser(
        'generate',
        parents=parents,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        help='Generate a SwaggerClient subclass for a given Swagger spec',
    )
    parser.add_argument(
        '--name',
        required=True,
        help='Name of the service',
    )
    parser.add_argument(
        'path',
        help='Absolute or relative path of the swagger spec.',
    )
    parser.set_defaults(func=main)


def generate(path, name):
    spec_dict = _load_spec(path)
    swagger_spec = Spec.from_dict(spec_dict)
    generate_client(swagger_spec, name)


def generate_client(swagger_spec, service_name):
    """Generate a python module with a SwaggerClient subclass tailored to the given Swagger spec."""

    file_lines = []
    file_lines.append(CLIENT_HEADER.format(
        service_name=service_name,
    ))

    # generate resources on client class
    for resource_name in sorted(swagger_spec.resources.keys()):
        file_lines.append(_generate_resource_property(resource_name))

    # generate resource class with operation methods
    for resource_name, resource in sorted(swagger_spec.resources.items()):
        file_lines.extend(_generate_resource_class(resource))

    print('\n'.join(file_lines))


def _load_spec(path):
    with open(path) as fh:
        return yaml.safe_load(fh)


def _generate_resource_property(resource_name):
    '''A resource property of the SwaggerClient class'''
    return '''
    @property
    def {resource_name}(self):
        return {resource_name}_Resource(self.swagger_spec)'''.format(
        resource_name=resource_name,
    )


def _generate_resource_class(resource):
    resource_lines = ['\n\nclass {}_Resource():'.format(resource.name)]

    resource_lines.append('''
    def __init__(self, swagger_spec):
        self._swagger_spec = swagger_spec''')

    for op_name, operation in sorted(resource.operations.items()):
        resource_lines.extend(_generate_operation_signature(op_name, operation))
        resource_lines.extend(_generate_operation_body(operation, resource.name))

    for op_name, operation in sorted(resource.operations.items()):
        response_spec = _get_happy_path_response_spec(
            operation.op_spec.get('responses', {}),
            operation.swagger_spec,
        )
        resource_lines.extend(_generate_operation_http_future(operation, response_spec))

    return resource_lines


def _generate_operation_signature(op_name, operation):
    op_lines = ['']
    params = ['self']
    optional_params = []
    for param_name, param in operation.params.items():
        param_str = param_name
        if param.has_default() or not param.required:
            if param.has_default():
                default = param.default
                param_type = param.param_spec['type']
                if param_type == 'string':
                    default = "'{}'".format(default)

                param_str += '={}'.format(default)
            elif not param.required:
                param_str += '=None'

            optional_params.append(param_str)
        else:
            params.append(param_str)

    optional_params.append('_request_options=None')
    params.extend(optional_params)

    op_lines.append('    def {op_name}({params_str}):'.format(
        op_name=op_name,
        params_str=', '.join(params),
    ))

    return op_lines


def _generate_operation_body(operation, resource_name):
    params = ['{0}={0}'.format(name) for name in operation.params]
    op_lines = ['''        operation = self._swagger_spec.resources['{resource_name}'].{operation_id}
        # TODO: debug logging
        warn_for_deprecated_op(operation)
        # Get per-request config
        request_options = _request_options or {{}}
        request_options['http_future_class'] = {operation_id}HttpFuture
        request_config = RequestConfig(request_options, also_return_response_default=False)

        request_params = construct_request(
            operation, request_options, {params}
        )

        http_client = operation.swagger_spec.http_client

        return http_client.request(
            request_params,
            operation=operation,
            request_config=request_config,
        )'''.format(
        params=', '.join(params),
        operation_id=operation.operation_id,
        resource_name=resource_name,
    )]

    return op_lines


def _generate_operation_http_future(operation, response_spec):
    return [
        '',
        '',
        'class {}HttpFuture(HttpFuture):'.format(operation.operation_id),
        '    pass',
    ]


def _get_happy_path_response_spec(responses_spec, swagger_spec):
    """Find the appropriate spec for the response that bravado will return when you call
    HtttpFuture.result. 99% of the time it's going to be the response for HTTP status code
    200, but sometimes it's a different status code or the 'default' response."""

    deref = swagger_spec.deref
    response_spec = responses_spec.get('200')
    if not response_spec:
        status_codes = sorted(responses_spec.keys())
        if status_codes:
            status_code = status_codes[0]
            if status_code < '300':
                response_spec = deref(responses_spec[status_code])
    if not response_spec:
        response_spec = deref(responses_spec.get('default'))

    return response_spec


def main(args):
    generate(args.path, args.name)
