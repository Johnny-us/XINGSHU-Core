"""当前调用内的结构化宿主桥；只发请求，不自行取得外部工具权限。"""
import json
import os
import select
import sys
import time
from xingshu_collaboration.binding import CandidateError
from xingshu_collaboration.state import strict_json

class StdioHostCall:
    def __init__(self, input_stream=None, output_stream=None):
        self.input = sys.stdin if input_stream is None else input_stream
        self.output = sys.stdout if output_stream is None else output_stream
        self.sequence = 0

    def __call__(self, method, params):
        self.sequence += 1
        request_id = self.sequence  # 仅本进程请求关联；不是另一个消息序列或持久账本。
        params = dict(params)
        timeout_ms = params.pop('timeout_ms', 5000)
        if type(timeout_ms) is not int or not 0 < timeout_ms <= 120000:
            raise CandidateError('HOST_TIMEOUT_BOUND_INVALID')
        print(json.dumps({'jsonrpc':'2.0', 'id':request_id, 'method':method, 'params':params,
                          'timeout_ms':timeout_ms},ensure_ascii=False),
              file=self.output,flush=True)
        fd, deadline, raw = self.input.fileno(), time.monotonic() + timeout_ms/1000, bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd],[],[],max(0,remaining))[0]:
                raise CandidateError('HOST_RESPONSE_TIMEOUT')
            part = os.read(fd, min(65536, 1048577-len(raw)))
            if not part:
                raise CandidateError('HOST_RESPONSE_EOF')
            raw.extend(part)
            if len(raw)>1048576:
                raise CandidateError('HOST_RESPONSE_BOUND_STOP')
            if b'\n' in raw:
                line, tail = bytes(raw).split(b'\n',1)
                if tail:
                    raise CandidateError('HOST_UNSOLICITED_RESPONSE_STOP')
                break
        reply = strict_json(line)
        if (type(reply) is not dict or set(reply) != {'jsonrpc','id','result'}
                or reply.get('jsonrpc') != '2.0' or type(reply.get('id')) is not int
                or reply['id'] != request_id):
            raise CandidateError('HOST_RESPONSE_CORRELATION_CONFLICT')
        return reply['result']
