# Copyright (c) 2019 Oracle and/or its affiliates.
# This software is made available to you under the terms of the GPL 3.0 license or the Apache 2.0 license.
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
# Apache License v2.0
# See LICENSE.TXT for details.

from __future__ import absolute_import, division, print_function

__metaclass__ = type

from ansible.module_utils.oracle import (
    oci_config_utils,
    oci_common_utils,
    oci_wait_utils,
)
from ansible.module_utils import six
import sys
import re
from ansible.module_utils.oracle import resourcehelpers, facthelpers, actionhelpers
import pkgutil
import inspect

try:
    from oci.exceptions import ServiceError, MaximumWaitTimeExceeded
    from oci.util import to_dict

    HAS_OCI_PY_SDK = True
except ImportError:
    HAS_OCI_PY_SDK = False

DeprecationWarning = """The new OCI Ansible collection (https://github.com/oracle/oci-ansible-collection),
replaces these legacy modules. Please migrate to the new OCI Ansible collection for improved features and support.
The legacy modules will be available only in the maintenance mode and only critical bugs will be fixed.
They will be deprecated in mid-2021."""


class OCIResourceFactsHelperBase:
    def __init__(self, module, resource_type, service_client_class, namespace):
        self.module = module
        self.resource_type = resource_type
        self.service_client_class = service_client_class
        self.client = oci_config_utils.create_service_client(
            self.module, self.service_client_class
        )
        self.namespace = namespace
        self.module.warn(DeprecationWarning)

    def get_required_params_for_get(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError("get not supported by {0}".format(self.resource_type))

    def get_required_params_for_list(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "list not supported by {0}".format(self.resource_type)
        )

    def get_resource(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError("get not supported by {0}".format(self.resource_type))

    def list_resources(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "list not supported by {0}".format(self.resource_type)
        )

    def is_get(self):
        try:
            if all(
                [
                    self.module.params.get(get_param) is not None
                    for get_param in self.get_required_params_for_get()
                ]
            ):
                return True
        except NotImplementedError:
            return False
        return False

    def is_list(self):
        try:
            if all(
                [
                    self.module.params.get(list_param) is not None
                    for list_param in self.get_required_params_for_list()
                ]
            ):
                return True
        except NotImplementedError:
            return False
        return False

    def fail(self):
        self.module.fail_json(
            msg="Specify {0} to get all resources or {1} to get a specific resource.".format(
                self.get_required_params_for_list(), self.get_required_params_for_get()
            )
        )

    def get(self):
        resource = self.get_resource().data
        return to_dict(resource)

    def list(self):
        resources = self.list_resources()
        return to_dict(resources)


class OCIActionsHelperBase:
    def __init__(self, module, resource_type, service_client_class, namespace):
        self.module = module
        self.resource_type = resource_type
        self.service_client_class = service_client_class
        self.client = oci_config_utils.create_service_client(
            self.module, self.service_client_class
        )
        self.namespace = namespace
        self.check_mode = self.module.check_mode
        self.module.warn(DeprecationWarning)

    def get_module_resource_id_param(self):
        """Expected to be generated inside the module."""
        pass

    def get_module_resource_id(self):
        """Expected to be generated inside the module."""
        pass

    def get_get_fn(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError("get not supported by {0}".format(self.resource_type))

    def get_resource(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError("get not supported by {0}".format(self.resource_type))

    def get_action_fn(self, action):
        action_fn = getattr(self, action, None)
        if not (action_fn and callable(action_fn)):
            return None
        return action_fn

    def is_action_necessary(self, action):
        if action.upper() in oci_common_utils.ALWAYS_PERFORM_ACTIONS:
            return True
        resource = self.get_resource().data
        if hasattr(
            resource, "lifecycle_state"
        ) and resource.lifecycle_state in self.get_action_idempotent_states(action):
            return False
        return True

    def get_action_idempotent_states(self, action):
        return oci_common_utils.ACTION_IDEMPOTENT_STATES.get(action.upper(), [])

    def get_action_desired_states(self, action):
        return oci_common_utils.ACTION_DESIRED_STATES.get(
            action.upper(), oci_common_utils.DEFAULT_READY_STATES
        )

    def perform_action(self, action):

        action_fn = self.get_action_fn(action)
        if not action_fn:
            self.module.fail_json(msg="{0} not supported by the module.".format(action))

        try:
            get_response = self.get_resource()
        except ServiceError as se:
            self.module.fail_json(
                msg="Getting resource failed with exception: {0}".format(se.message)
            )
        else:
            resource = to_dict(get_response.data)

        is_action_necessary = self.is_action_necessary(action)
        if not is_action_necessary:
            return oci_common_utils.get_result(
                changed=False, resource_type=self.resource_type, resource=resource
            )

        if self.check_mode:
            return oci_common_utils.get_result(
                changed=True, resource_type=self.resource_type, resource=resource
            )

        try:
            actioned_resource = action_fn()
        except MaximumWaitTimeExceeded as mwtex:
            self.module.fail_json(msg=str(mwtex))
        except ServiceError as se:
            self.module.fail_json(
                msg="Performing action failed with exception: {0}".format(se.message)
            )
        else:
            return oci_common_utils.get_result(
                changed=True,
                resource_type=self.resource_type,
                resource=to_dict(actioned_resource),
            )


class OCIResourceHelperBase:
    def __init__(self, module, resource_type, service_client_class, namespace):
        self.module = module
        self.resource_type = resource_type
        self.service_client_class = service_client_class
        self.client = oci_config_utils.create_service_client(
            self.module, self.service_client_class
        )
        self.namespace = namespace
        self.check_mode = self.module.check_mode
        self.module.warn(DeprecationWarning)

    def get_module_resource_id_param(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "{0} does not have a resource id.".format(self.resource_type)
        )

    def get_module_resource_id(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "{0} does not have a resource id.".format(self.resource_type)
        )

    def get_get_fn(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError("get not supported by {0}".format(self.resource_type))

    def get_resource(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError("get not supported by {0}".format(self.resource_type))

    def list_resources(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "list not supported by {0}".format(self.resource_type)
        )

    def create_resource(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "create not supported by {0}".format(self.resource_type)
        )

    def update_resource(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "update not supported by {0}".format(self.resource_type)
        )

    def delete_resource(self):
        """Expected to be generated inside the module."""
        raise NotImplementedError(
            "delete not supported by {0}".format(self.resource_type)
        )

    def get_create_model_class(self):
        """Expected to be generated inside the module."""
        pass

    def get_update_model_class(self):
        """Expected to be generated inside the module."""
        pass

    def is_delete(self):
        if not self.module.params.get("state") == "absent":
            return False
        return True

    def is_update(self):
        if not self.module.params.get("state") == "present":
            return False
        if not self.get_module_resource_id():
            return False
        return True

    def is_create(self):
        if not self.module.params.get("state") == "present":
            return False
        if self.get_module_resource_id():
            return False
        return True

    def _is_resource_active(self, resource):
        if "lifecycle_state" not in resource.attribute_map:
            return True
        return resource.lifecycle_state not in oci_common_utils.DEAD_STATES

    def get_exclude_attributes(self):
        return ["freeform_tags", "node_count"]

    def get_attributes_to_consider(self, create_model):
        if self.module.params.get("key_by") is not None:
            return self.module.params["key_by"]
        return [
            attr
            for attr in create_model.attribute_map
            if attr not in self.get_exclude_attributes()
        ]

    def get_create_model(self):
        return convert_input_data_to_model_class(
            self.module.params, self.get_create_model_class()
        )

    def get_update_model(self):
        return convert_input_data_to_model_class(
            self.module.params, self.get_update_model_class()
        )

    def get_user_provided_value(self, attr):
        return self.module.params.get(attr)

    def get_matching_resource(self):
        create_model = self.get_create_model()
        attributes_to_consider = self.get_attributes_to_consider(create_model)
        for resource in self.list_resources():
            if not self._is_resource_active(resource):
                continue
            resource_dict = to_dict(resource)
            if oci_common_utils.is_dict_subset(
                source_dict=to_dict(create_model),
                target_dict=resource_dict,
                attrs=attributes_to_consider,
            ):
                return resource
        return None

    def get_compartment_id(self, resource_id_name, resource_get):
        compartment_id = self.module.params.get("compartment_id")
        resource_id = self.module.params.get(resource_id_name)
        if not compartment_id and resource_id:
            try:
                return oci_common_utils.call_with_backoff(
                    resource_get, resource_id
                ).data.compartment_id
            except Exception:
                return None
        return compartment_id

    def create(self):

        if self.module.params.get("force_create"):
            if self.check_mode:
                return oci_common_utils.get_result(
                    changed=True, resource_type=self.resource_type, resource=dict()
                )
        else:
            resource_matched = self.get_matching_resource()
            if resource_matched:
                return oci_common_utils.get_result(
                    changed=False,
                    resource_type=self.resource_type,
                    resource=to_dict(resource_matched),
                )

        if self.check_mode:
            return oci_common_utils.get_result(
                changed=True, resource_type=self.resource_type, resource=dict()
            )

        try:
            created_resource = self.create_resource()

        except MaximumWaitTimeExceeded as ex:
            self.module.fail_json(msg=str(ex))
        except ServiceError as se:
            self.module.fail_json(msg=se.message)
        else:
            return oci_common_utils.get_result(
                changed=True,
                resource_type=self.resource_type,
                resource=to_dict(created_resource),
            )

    def get_waiter_type(self, operation):
        return oci_wait_utils.LIFECYCLE_STATE_WAITER_KEY

    def update(self):

        try:
            get_response = self.get_resource()
        except ServiceError as se:
            self.module.fail_json(
                msg="Getting resource failed with exception: {0}".format(se.message)
            )
        else:
            resource = to_dict(get_response.data)

        is_update_necessary = self.is_update_necessary()
        if not is_update_necessary:
            return oci_common_utils.get_result(
                changed=False, resource_type=self.resource_type, resource=resource
            )

        if self.check_mode:
            return oci_common_utils.get_result(
                changed=True, resource_type=self.resource_type, resource=resource
            )

        try:
            updated_resource = self.update_resource()
        except MaximumWaitTimeExceeded as mwtex:
            self.module.fail_json(msg=str(mwtex))
        except ServiceError as se:
            self.module.fail_json(
                msg="Updating resource failed with exception: {0}".format(se.message)
            )
        else:
            return oci_common_utils.get_result(
                changed=True,
                resource_type=self.resource_type,
                resource=to_dict(updated_resource),
            )

    def delete(self):

        try:

            if not self.get_module_resource_id():
                self.module.fail_json(
                    msg="Specify {0} with state as 'absent' to delete a {1}.".format(
                        self.get_module_resource_id_param(), self.resource_type.upper()
                    )
                )

        except NotImplementedError:
            # a few resources have no resource identifier (because they don't follow the
            # normal path convention: DELETE /resources/{resourceId} (e.g. AppCatalogSubscription)
            # so there can be a delete without a resourceId
            pass

        try:
            get_response = self.get_resource()
        except ServiceError as se:
            if se.status == 404:
                return oci_common_utils.get_result(
                    changed=False, resource_type=self.resource_type, resource=dict()
                )
            self.module.fail_json(
                msg="Getting resource failed with exception: {0}".format(se.message)
            )
        else:
            resource = to_dict(get_response.data)
            if "lifecycle_state" in resource and resource["lifecycle_state"] in [
                "DETACHING",
                "DETACHED",
                "DELETING",
                "DELETED",
                "TERMINATING",
                "TERMINATED",
            ]:
                return oci_common_utils.get_result(
                    changed=False, resource_type=self.resource_type, resource=resource
                )

        if self.check_mode:
            return oci_common_utils.get_result(
                changed=True,
                resource_type=self.resource_type,
                resource=oci_common_utils.get_resource_with_state(resource, "DELETED"),
            )

        try:
            deleted_resource = self.delete_resource()
        except MaximumWaitTimeExceeded as mwtex:
            self.module.fail_json(msg=str(mwtex))
        except ServiceError as se:
            if se.status == 404:
                return oci_common_utils.get_result(
                    changed=True,
                    resource_type=self.resource_type,
                    resource=oci_common_utils.get_resource_with_state(
                        resource, "DELETED"
                    ),
                )
            self.module.fail_json(
                msg="Deleting resource failed with exception: {0}".format(se.message)
            )
        else:
            if deleted_resource:
                resource = to_dict(deleted_resource)
            return oci_common_utils.get_result(
                changed=True, resource_type=self.resource_type, resource=resource
            )

    def is_update_necessary(self):
        current_resource_dict = to_dict(self.get_resource().data)
        update_model = self.get_update_model()
        update_model_dict = to_dict(update_model)
        return not oci_common_utils.are_dicts_equal(
            update_model_dict, current_resource_dict, update_model.attribute_map
        )

    def get_resource_from_work_request_response(self, work_request_response):
        self.module.fail_json(
            msg="Could not get the resource from work request response {0}".format(
                work_request_response
            )
        )


custom_helper_mapping = {}


# convert dictionary to a Python SDK model class
# for example:
#   data: {
#        'hostname_label': 'mytestinstance',
#        'subnet_id': 'ocid1.subnet.oc1.iad.xxxxxEXAMPLExxxxx',
#        'display_name': 'my_vnic'
#   }
#
# model_class: <class 'oci.core.models.create_vnic_details.CreateVnicDetails'>
#
# will create a CreateVnicDetails instance with the relevant fields populated
# based on 'data'
def convert_input_data_to_model_class(data, model_class):
    # e.g. oci.core.models.create_vnic_details.LaunchInstanceDetails -> oci.core.models
    namespace = ".".join(model_class.__module__.split(".")[0:-1])

    # e.g. 'oci.core.models' -> <module 'oci.core.models'>
    module = sys.modules[namespace]

    # if the type is polymoprhic, data might be a subtype of model_class
    # and thus we need to parse it as the correct subtype based on the discriminator
    # if we parse based on the declared (base) type, we will skip all fields that are
    # only defined on the subtype
    model_instance = model_class()
    if hasattr(model_instance, "get_subtype"):
        # get_subtype expects the camelCase version of the data (i.e. if discriminator field
        # name is source_type in python it expects sourceType)
        camelized_top_level_keys = dict(
            (camelize(key), value) for key, value in six.iteritems(data)
        )
        subtype_name = model_instance.get_subtype(camelized_top_level_keys)
        model_class = getattr(module, subtype_name)
        model_instance = model_class()

    for attr in model_instance.attribute_map:
        if data.get(attr) is None:
            continue

        value = data[attr]

        # e.g. LaunchInstanceDetails.swagger_types.get('create_vnic_details') -> 'CreateVnicDetails'
        swagger_type = model_instance.swagger_types.get(attr)
        # if data is complex, we need to convert nested values
        if hasattr(module, swagger_type):
            value = convert_input_data_to_model_class(
                value, getattr(module, swagger_type)
            )
        elif swagger_type.find("list[") == 0:
            # convert individual items in the list to complex type
            element_swagger_type = re.match(r"list\[(.*)\]", swagger_type).group(1)
            if hasattr(module, element_swagger_type):
                converted_values = []
                for element in value:
                    converted_values.append(
                        convert_input_data_to_model_class(
                            element, getattr(module, element_swagger_type)
                        )
                    )
                value = converted_values
        elif swagger_type.find("dict(") == 0:
            # convert individual values in dict to complex type
            match = re.match(r"dict\(([^,]*), (.*)\)", swagger_type)
            entry_value_swagger_type = match.group(2)

            if hasattr(module, entry_value_swagger_type):
                converted_values = {}
                for key in value:
                    converted_values[key] = convert_input_data_to_model_class(
                        value[key], getattr(module, entry_value_swagger_type)
                    )

                value = converted_values

        setattr(model_instance, attr, value)
    return model_instance


# Converts an argument to camel case with a lower case first character. For example
# "my_param" would turn into "myParam" and "this_other_param" would be "thisOtherParam"
#
# Supports both UpperCaseCamel and lowerCaseCamel, though lower case is considered the default
def camelize(to_camelize, uppercase_first_letter=False):
    if not to_camelize:
        return ""

    if uppercase_first_letter:
        return re.sub(r"(?:^|[_-])(.)", lambda m: m.group(1).upper(), to_camelize)
    else:
        return (
            to_camelize[0].lower()
            + camelize(to_camelize, uppercase_first_letter=True)[1:]
        )


def import_module(pkg, module_name):
    full_module_name = pkg.__name__ + "." + module_name
    toplevel_module = __import__(full_module_name)
    module = toplevel_module
    for attr in full_module_name.split(".")[1:]:
        module = getattr(module, attr)
    return module


def get_custom_class_mapping(pkgs):
    custom_class_mapping = {}
    for pkg in pkgs:
        for dummy, name, ispkg in pkgutil.walk_packages(path=pkg.__path__):
            if ispkg:
                continue
            module = import_module(pkg, name)
            for obj_name in dir(module):
                if not obj_name.endswith("Custom"):
                    continue
                obj = getattr(module, obj_name)
                if inspect.isclass(obj):
                    custom_class_mapping[obj_name] = obj
    return custom_class_mapping


custom_helper_mapping = get_custom_class_mapping(
    [resourcehelpers, facthelpers, actionhelpers]
)


class DefaultHelperCustom:
    pass


def get_custom_class(resource_type):
    custom_class = custom_helper_mapping.get(resource_type)
    if not custom_class:
        return DefaultHelperCustom
    return custom_class
