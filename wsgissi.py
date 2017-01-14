import re
import time
import webob

cmd_arg_re = re.compile(r'(\w+)="(.*?)"')
var_re = re.compile(r'(^|[^\\])\$[{]?([_\w]+)[}]?')  # matches $var or ${var}


def parse_command(command):
    parts = command.split(None, 1)
    if len(parts) > 1:
        cmd, tail = parts
        return cmd, dict(cmd_arg_re.findall(tail))
    else:
        return command, {}


def get_chunks(body):
    end = 0
    start = 0
    while True:
        start = body.find('<!--#', end)
        if start < 0:
            yield '__content__', body[end:]
            break
        elif start > end:
            yield '__content__', body[end:start]
        start += 5

        end = body.find('-->', start)
        if end < 0:
            break
        command = body[start:end].strip()
        end += 3
        yield parse_command(command)


def expand_vars(ctx, string):
    def sub(match):
        head, var = match.groups()
        return (head or '') + ctx.get(var, '')

    return var_re.sub(sub, string).replace(r'\$', '$')


def calc_if(ctx, expr):
    parts = expr.split()
    if len(parts) == 1:
        return expand_vars(ctx, expr)

    try:
        var, op, value = parts
    except ValueError:
        var, op = parts
        value = ''

    var = expand_vars(ctx, var)
    if op == '=':
        return var == value
    elif op == '!=':
        return var != value


def process(chunks):
    ctx = {}
    content = []
    virtual = []
    vcnt = 0
    ifcond = True
    for command, params in chunks:
        if command == 'if':
            ifcond = calc_if(ctx, params['expr'])
            continue
        elif command == 'elif' and not ifcond:
            ifcond = calc_if(ctx, params['expr'])
            continue
        elif command == 'else' and not ifcond:
            ifcond = True
            continue
        elif command == 'endif':
            ifcond = True
            continue

        if not ifcond:
            continue

        if command == '__content__':
            content.append(params)
        elif command == 'include':
            content.append(vcnt)
            virtual.append(expand_vars(ctx, params['virtual']))
            vcnt += 1
        elif command == 'set':
            ctx[params['var']] = expand_vars(ctx, params['value'])
        elif command == 'echo':
            content.append(ctx.get(params['var'], ''))

    return content, virtual


def fetch_virtual(env, app, links, log):
    result = []
    environ = {k: v for k, v in env.items() if k.startswith('HTTP_') or k.startswith('SERVER_')}

    def start_response(status, headers, exc_info=None):
        last_status[0] = status

    for l in links:
        if log:
            print 'SSI include', l,
        req = webob.Request.blank(l, environ=environ)

        last_status = [None]
        st = time.time()
        resp = ''.join(app(req.environ, start_response))
        duration = time.time() - st

        if log:
            print last_status[0], round(duration * 1000, 3)

        result.append(resp)

    return result


def join_content(content, virtual):
    for c in content:
        if type(c) == int:
            yield virtual[c]
        else:
            yield c


def wsgissi(app, log=True):
    def inner(env, sr):
        sr_data = []
        def sr_collector(status, headers, exc_info=None):
            sr_data.append((status, headers, exc_info))

        body = ''.join(app(env, sr_collector))
        chunks = get_chunks(body)
        content, virtual = process(chunks)
        vcontent = fetch_virtual(env, inner, virtual, log=log)
        result = ''.join(join_content(content, vcontent))

        status, headers, exc_info = sr_data[0]
        headers = [(h, v) for h, v in headers if h.lower() != 'content-length']
        headers.append(('Content-Length', str(len(result))))

        sr(status, headers, exc_info)
        return result

    return inner
