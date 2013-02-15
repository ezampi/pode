# coding: utf-8

import sys
import dis
from time import time
from copy import copy
from pprint import pprint
from datetime import datetime

# Event types
EVENT_FUNC_CALL = 1
EVENT_FUNC_RET = 2
EVENT_VAR_ATTR = 3


class Dejavu(object):

    def __init__(self, metadebug=False):
        self.metadebug = metadebug
        self.events = {}
        # variable names whose values need to be captured asap
        self.pending_captures = []

    def trace_dispatch(self, frame, event, arg):
        if event == 'line':
            return self.dispatch_line(frame)
        elif event == 'call':
            return self.dispatch_call(frame, arg)
        elif event == 'return':
            return self.dispatch_return(frame, arg)
        return self.trace_dispatch

    def emit(self, event_type, objname, value):
        t = datetime.now()
        record = (t, event_type, objname, value)
        self.events[t] = record
        if self.metadebug:
            print("Event", record)

    def dispatch_line(self, frame):
        # generate events for pending variables from previous lines
        while self.pending_captures:
            varname = self.pending_captures.pop(0)
            try:
                value = frame.f_locals[varname]
                self.emit(EVENT_VAR_ATTR, varname, value)
            except KeyError:
                if self.metadebug:
                    print "Ignoring", varname
                    # value not available yet
                break

        new_code = self.cut_asm(frame.f_lasti, frame.f_code)
        self.schedule_capture(frame.f_lasti, frame, new_code)

        if self.metadebug:
            record = (frame.f_lineno,
                      "line",
                      frame.f_code.co_filename,
                      frame.f_code.co_name)
            pprint(record)

        return self.trace_dispatch

    def dispatch_call(self, frame, arg):
        # Arg names are mixed with local variables,
        #  but come first in the list co_varnames
        arg_names = frame.f_code.co_varnames[:frame.f_code.co_argcount]
        call_params = {name: frame.f_locals[name] for name in arg_names} \
            if (frame.f_code.co_name != '<module>') \
            else ''

        record = (frame.f_lineno,
                  frame.f_code.co_filename,
                  frame.f_code.co_name,
                  call_params,
                  copy(arg))
        self.emit(EVENT_FUNC_CALL, frame.f_code.co_name, record)
        self.cut_asm(frame.f_lasti, frame.f_code)

        if self.metadebug:
            pprint(record)
        return self.trace_dispatch

    def dispatch_return(self, frame, arg):
        t = time()
        record = (frame.f_lineno,
                  frame.f_code.co_filename,
                  copy(arg))
        self.emit(EVENT_FUNC_RET, frame.f_code.co_name, record)

        if self.metadebug:
            pprint(record)

        return self.trace_dispatch

    def cut_asm(self, line, code):
        if line >= 0:
            codesize = len(code.co_code)
            lines = list(dis.findlinestarts(code))
            for pos, (asm_line, src_line) in enumerate(lines):
                if line != asm_line:
                    continue
                else:
                    if asm_line == lines[-1][0]:
                        first, last = (asm_line, codesize)
                    else:
                        first, last = (asm_line, lines[pos+1][0])
                    break

            codestr = code.co_code[first:last]
        else:
            codestr = code.co_code

        # Rebuild code object
        new_code = type(code)(code.co_argcount,
                              code.co_nlocals,
                              code.co_stacksize,
                              code.co_flags,
                              codestr,
                              code.co_consts,
                              code.co_names,
                              code.co_varnames,
                              code.co_filename,
                              code.co_name,
                              code.co_firstlineno,
                              code.co_lnotab,
                              code.co_freevars,
                              code.co_cellvars)

        if self.metadebug:
            dis.disassemble(new_code)

        return new_code

    def schedule_capture(self, line, frame, co):
        # co param may be different from frame.f_code
        store_codes = [dis.opmap[i] for i in ('STORE_FAST',  'STORE_NAME')]
        # TODO: support 'STORE_GLOBAL', 'STORE_MAP','STORE_ATTR'
        code = co.co_code
        n = len(code)
        linestarts = dict(dis.findlinestarts(co))
        i = 0
        while i < n:
            c = code[i]
            op = ord(c)
            i = i + 1
            if op >= dis.HAVE_ARGUMENT:
                i = i + 2
                if op in store_codes:
                    arg = ord(code[i-2]) | (ord(code[i-1]) << 8)
                if op == dis.opmap['STORE_FAST']:
                    varname = co.co_varnames[arg]
                    self.pending_captures.append(varname)
                elif op == dis.opmap['STORE_NAME']:
                    varname = co.co_names[arg]
                    self.pending_captures.append(varname)


def main(py_file):
    dejavu = Dejavu()
    #dejavu = Dejavu(metadebug=True)
    sys.settrace(dejavu.trace_dispatch)
    try:
        exec py_file
    finally:
        sys.settrace(None)
        del dejavu

if __name__ == "__main__":
    module_name = sys.argv[1]
    py_file = open(module_name)
    main(py_file)
    py_file.close()
    # useful for interactive mode -i
    from pprint import pprint as pp

# python -i dejavu.py teste1.py
# >> pp(dejavu.calls)
