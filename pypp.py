#!/usr/bin/env python3
# Copyright (c) 2012 Andrew Carter
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met: 
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer. 
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution. 
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies, 
# either expressed or implied, of the FreeBSD Project.
'''This module provides a text preprocessor for python.
'''
from ast import literal_eval
from datetime import datetime
from os import path
from re import compile as regex

# regex for matching various directives
directives = (
  regex(r'''(?P<indent>\s*)[#](?P<directive>include|inside)(?:\s+(?P<name>".*"))?\s*$'''),
  regex(r'''(?P<indent>\s*)[#](?P<directive>define|local)\s+(?:(?P<level>\d+)\s+)?(?P<name>\w+)\s+(?P<value>".*")?\s*$'''),
  regex(r'''(?P<indent>\s*)[#](?P<directive>(?:el)?ifn?(?:def)?)(?:\s+(?P<name>\w+))?\s*$'''),
  regex(r'''(?P<indent>\s*)[#](?P<directive>[#])(?P<value>.*)$'''),
  regex(r'''(?P<indent>\s*)[#](?P<directive>for)\s+(?:(?P<name>\w+)\s+)?(?P<value>(?:".*"|\w+))\s*$'''),
  regex(r'''(?P<indent>\s*)[#](?P<directive>end|else)\s*$'''),
  regex(r'''(?P<indent>\s*)[#](?P<directive>\s)(?P<value>.*)$'''),
# catch malformed directives
  regex(r'''(?P<directive>)(?P<valid>\s*[#](?:include|inside)(\s+".*"?)?\s*)'''),
  regex(r'''(?P<directive>)(?P<valid>\s*[#](?:define|local)(\s+(?:\d+\s+)?(?:\w+\s+(?:".*")?)?)?\s*)'''),
  regex(r'''(?P<directive>)(?P<valid>\s*[#](?:(?:el)?ifn?(?:def)?)(?:\s+\w+)?\s*)'''),
  regex(r'''(?P<directive>)(?P<valid>\s*[#](?:for)(?:\s+(?:\w+\s+)?(?:".*"|\w+))?\s*)'''),
  regex(r'''(?P<directive>)(?P<valid>\s*[#](?:end|else)\s*)'''),
# catch directive-like objects, probably an error
  regex(r'''(?P<directive>)(?P<valid>\s*[#]).*$'''),
)

# provide __DATE__/__TIME__ for file generation timestamps
today = datetime.today()

# set of default values
defaults = {
  None : '',
  '' : '',
  '__INDENT__' : '',
  '__DATE__' : today.strftime('%b %d %Y'),
  '__TIME__' : today.strftime('%H:%M:%S'),
  '__LEVEL__' : 0,
}

class copy_file(object):
  '''A file wrapper that holds the state of the file on creation.
  
  DESCRIPTION:
    This wrapper is designed to allow the file to be read from externally,
    and then access the file via this wrapper to read the file
    as if it hadn't been read from.
    
    Reading from this file modifies the original placement, and reading from
    the file externally after the wrapper has been read from once modifies
    what the file will read when read through the wrapper.
  
  FIELDS:
    file   : The file this function is handling.
    name   : The name the file has been opened with.
    closed : Whether this wrapper is closed, does not indicate whether the original file is closed.
    offset : The offset on creation, None if the wrapper has been read from.
  '''
  def __init__(self, file):
    '''Creates a copy of file
    
    Argument:
      file : The file to copy
    '''
    self.file = file
    self.name = file.name
    self.closed = file.closed
    self.offset = file.tell()
  def readline(self):
    if self.closed:
      raise ValueError("I/O operation on closed file.")
    if self.offset is not None:
      self.seek(self.offset)
      self.offset = None
    return self.file.readline()
  def close(self):
    self.closed = True
  def tell(self):
    if self.closed:
      raise ValueError("I/O operation on closed file.")
    return self.file.tell() if self.offset is None else self.offset
  def seek(self, offset):
    if self.closed:
      raise ValueError("I/O operation on closed file.")
    self.file.seek(offset)
  
def preprocess(name, values={}, output=print):
  global directives, defaults
  if not output:
    output = lambda a : a
  current = open(name, 'r')
  inner, outer = [], []
  
  stack  = [dict(defaults)]
  stack[-1].update(values)
  stack.append(dict(stack[-1]))
  stack[-1]['__FILE__'] = path.abspath(name)
  stack[-1]['__LINE__'] = 0
  stack[-1]['__LEVEL__'] = 1
  match  = None
  
  ignoring = 0
  
  def push(file_stack=outer, next_file=None, values=None):
    nonlocal stack, match, current
    if not values:
      values = stack[-1]
    stack.append(dict(values))
    stack[-1]['__INDENT__'] += match.group('indent')
    if next_file:
      stack[-1]['__FILE__'] = path.abspath(next_file.name)
      stack[-1]['__LINE__'] = 0
      stack[-1]['__LEVEL__'] = len(stack) - 1
    file_stack.append(current)
    current = next_file if next_file else copy_file(current)
  def pop():
    nonlocal stack, current
    stack.pop()
    current.close()
    try:
      current = outer.pop()
    except IndexError:
      current = None
  while current:
    line = current.readline()
    stack[-1]['__LINE__'] = int(stack[-1]['__LINE__']) + 1
    if not line:
      pop()
    else:
      line = line.rstrip()
      while line:
        try:
          match = next(match for match in (directive.match(line) for directive in directives) if match)
        except StopIteration:
          match = None
        # Giant if statement of death, yay parsing
        if not line:
          pass
        elif ignoring and not match:
          pass
        elif not match:
          output(stack[-1]['__INDENT__'] + line % stack[-1])
        elif not match.group('directive'):
          stack[-1]['__DIRECTIVE__'] = line
          raise SyntaxError("""Invalid directive""", (stack[-1]['__FILE__'], stack[-1]['__LINE__'], len(match.group('valid')), line))
        elif match.group('directive') == 'end':
          if ignoring:
            ignoring -= 1
          if not ignoring:
            pop()
        elif ignoring and match.group('directive') in ['if','ifn','ifdef','ifndef','for']:
          ignoring += 1
        elif ignoring <= 1 and match.group('directive') == 'else':
          ignoring = not ignoring
        elif ignoring <= 1 and match.group('directive') in ['elif','elifn','elifdef','elifndef']:
          ignoring = not ignoring or \
                      (('n' in match.group('directive')) ==
                        bool((match.group('name') in stack[-1])
                          if match.group('directive').endswith('def')
                          else stack[-1][match.group('name')]))
        elif ignoring:
          pass
        elif match.group('directive') == '#':
          line = match.group('value') % stack[-1]
          continue
        elif match.group('directive') in ['include','inside']:
          side = outer if match.group('directive') == 'include' else inner
          if match.group('name'):
            loc = path.dirname(current.name)
            rel = match.group('name')[1:-1]
            new_file = open(path.join(loc, rel), 'r')
          else:
            new_file = inner.pop()
          push(file_stack=side, next_file=new_file)
        elif match.group('directive') in ['define','local']:
          level = int(match.group('level') if match.group('level') else 0)
          if match.group('directive') == 'define':
            level = len(stack) - level - 2
          for i, values in enumerate(reversed(stack)):
            if level < i:
              break
            if match.group('name'):
              values[match.group('name')] = match.group('value')[1:-1] % values
            else:
              del values[match.group('name')]
        elif match.group('directive') == 'for':
          value = match.group('value')
          if value[0] == '"':
            value = value[1:-1]
          else:
            value = stack[-1][match.group('value')]
          if isinstance(value,str):
            value = literal_eval(value)
          if not len(value):
            ignoring = 1
            push()
          else:
            values = stack[-1]
            original = current
            for v in reversed(value):
              push(next_file=copy_file(original),values=values)
              if match.group('name'):
                stack[-1][match.group('name')] = v
              else:
                stack[-1].update(v)
        elif match.group('directive') in ['if','ifn','ifdef','ifndef']:
          ignoring = (('n' in match.group('directive')) ==
                      bool((match.group('name') in stack[-1])
                        if match.group('directive').endswith('def')
                        else stack[-1][match.group('name')]))
          push()
        #elif comment directive
        #  pass
        break
  return stack[0]

# command line utility
if __name__ == '__main__':
  from sys import argv
  values = {}
  for filename in argv[1:]:
    values = preprocess(filename, values)
