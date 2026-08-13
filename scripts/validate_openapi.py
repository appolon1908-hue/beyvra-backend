#!/usr/bin/env python3
"""Parse OpenAPI YAML while rejecting duplicate mapping keys."""

import sys

import yaml


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping,
)


def main(paths):
    for path in paths:
        with open(path, encoding="utf-8") as source:
            document = yaml.load(source, Loader=UniqueKeyLoader)
        if document.get("openapi") is None or document.get("paths") is None:
            raise ValueError(f"not an OpenAPI document: {path}")
        print(f"OPENAPI_VALID={path}")


if __name__ == "__main__":
    main(sys.argv[1:])
