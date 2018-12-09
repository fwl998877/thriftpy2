# -*- coding: utf-8 -*-

"""
    thriftpy.parser
    ~~~~~~~~~~~~~~~

    Thrift parser using ply
"""

from __future__ import absolute_import

import os
import sys
import types

from .parser import parse, parse_fp, incomplete_type, _cast
from .exc import ThriftParserError
from ..thrift import TPayloadMeta


def load(path, module_name=None, include_dirs=None, include_dir=None):
    """Load thrift file as a module.

    The module loaded and objects inside may only be pickled if module_name
    was provided.

    Note: `include_dir` will be depreacated in the future, use `include_dirs`
    instead. If `include_dir` was provided (not None), it will be appended to
    `include_dirs`.
    """
    real_module = bool(module_name)
    thrift = parse(path, module_name, include_dirs=include_dirs,
                   include_dir=include_dir)
    if incomplete_type:
        fill_incomplete_ttype(thrift, thrift)
    if real_module:
        sys.modules[module_name] = thrift
    return thrift


def fill_incomplete_ttype(tmodule, definition):
    # fill incomplete ttype
    if isinstance(definition, tuple):
        # fill const value
        if definition[0] == 'UNKNOWN_CONST':
            ttype = get_definition(tmodule, incomplete_type[definition[1]][0], definition[3])
            return _cast(ttype)(definition[2])
        # fill an incomplete alias ttype
        if definition[1] in incomplete_type:
            return (definition[0], get_definition(tmodule, *incomplete_type[definition[1]]))
        # fill service method which has incomplete arg, return ttype
        elif definition[0] in incomplete_type:
            real_type = get_definition(
                tmodule, *incomplete_type[definition[0]])
            return (real_type[0], definition[1], real_type[1], definition[2])
        # fill incomplete compound ttype
        elif isinstance(definition[1], tuple):
            return (definition[0], fill_incomplete_ttype(tmodule, definition[1]))
    # handle thrift module
    elif isinstance(definition, types.ModuleType):
        for name, attr in definition.__dict__.items():
            if name.startswith('__'):  # skip inner attribute
                continue
            setattr(definition, name, fill_incomplete_ttype(tmodule, attr))
    # handle struct ttype
    elif isinstance(definition, TPayloadMeta):
        for index, value in definition.thrift_spec.items():
            # if the ttype of field is incomplete
            if value[0] in incomplete_type:
                real_type = fill_incomplete_ttype(
                    tmodule, get_definition(
                        tmodule, *incomplete_type[value[0]]))
                # if deletion ttype is a compound type
                if isinstance(real_type, tuple):
                    definition.thrift_spec[index] = (
                        real_type[0],
                        value[1],
                        real_type[1],
                        value[2]
                        )
                # if deletion ttype is a built-in ttype
                else:
                    definition.thrift_spec[index] = (
                        fill_incomplete_ttype(
                            tmodule, get_definition(
                                tmodule, *incomplete_type[value[0]]
                            )
                        ),
                    ) + tuple(value[1:])
            # if the ttype which field's ttype contains is incomplete
            elif isinstance(value[2], tuple):
                definition.thrift_spec[index] = (
                    value[0],
                    value[1],
                    fill_incomplete_ttype(tmodule, value[2]),
                    value[3])
    # handle service method
    elif hasattr(definition, "thrift_services"):
        for name, attr in definition.__dict__.items():
            if not hasattr(attr, "thrift_spec"):
                continue
            for index, value in attr.thrift_spec.items():
                attr.thrift_spec[index] = fill_incomplete_ttype(tmodule, value)
    return definition


def get_definition(thrift, name, lineno):
    ref_type = thrift
    for n in name.split('.'):
        ref_type = getattr(thrift, n, None)
        if ref_type is None:
            raise ThriftParserError('No type found: %r, at line %d' %
                                    (name, lineno))
        if isinstance(ref_type, int) and ref_type < 0:
            raise ThriftParserError('No type found: %r, at line %d' %
                                    incomplete_type[ref_type])
        if hasattr(ref_type, '_ttype'):
            return (getattr(ref_type, '_ttype'), ref_type)
        else:
            return ref_type


def load_fp(source, module_name):
    """Load thrift file like object as a module.
    """
    thrift = parse_fp(source, module_name)
    sys.modules[module_name] = thrift
    return thrift


def _import_module(import_name):
    if '.' in import_name:
        module, obj = import_name.rsplit('.', 1)
        return getattr(__import__(module, None, None, [obj]), obj)
    else:
        return __import__(import_name)


def load_module(fullname):
    """Load thrift_file by fullname, fullname should have '_thrift' as
    suffix.
    The loader will replace the '_thrift' with '.thrift' and use it as
    filename to locate the real thrift file.
    """
    if not fullname.endswith("_thrift"):
        raise ImportError(
            "ThriftPy can only load module with '_thrift' suffix")

    if fullname in sys.modules:
        return sys.modules[fullname]

    if '.' in fullname:
        module_name, thrift_module_name = fullname.rsplit('.', 1)
        module = _import_module(module_name)
        path_prefix = os.path.dirname(os.path.abspath(module.__file__))
        path = os.path.join(path_prefix, thrift_module_name)
    else:
        path = fullname
    thrift_file = "{}.thrift".format(path[:-7])

    module = load(thrift_file, module_name=fullname)
    sys.modules[fullname] = module
    return sys.modules[fullname]
